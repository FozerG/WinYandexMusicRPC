import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Event
from weakref import WeakMethod

from .models import MediaSnapshot, PlaybackStatus

logger = logging.getLogger(__name__)
RETRY_DELAYS = (2, 5, 15, 30)
SESSION_INTERVAL = 10
METADATA_INTERVAL = 5
PLAYBACK_INTERVAL = 1


class MediaUnavailable(RuntimeError):
    """The media service failed, or a previous request is still outstanding."""


def _dirty_event():
    event = Event()
    event.set()
    return event


@dataclass(eq=False)
class _Session:
    handle: object
    source: str
    subscriptions: list = field(default_factory=list)
    metadata_dirty: Event = field(default_factory=_dirty_event)
    playback_dirty: Event = field(default_factory=_dirty_event)
    timeline_dirty: Event = field(default_factory=_dirty_event)
    metadata: tuple[str, str, str] = ("", "", "")
    status: PlaybackStatus = PlaybackStatus.UNKNOWN
    timeline: tuple = (0, 0, None)
    metadata_at: float = 0
    playback_at: float = 0
    timeline_at: float = 0
    failures: int = 0
    retry_at: float = 0
    error: Exception | None = None

    def invalidate_metadata(self, *_):
        # WinRT can call handlers on another thread. Only touch thread-safe flags.
        self.metadata_dirty.set()
        self.invalidate_playback()

    def invalidate_playback(self, *_):
        self.playback_dirty.set()
        self.timeline_dirty.set()

    def invalidate_timeline(self, *_):
        self.timeline_dirty.set()


class WindowsMediaSource:
    """Cached GSMTC reader. Synchronous COM calls still require a responsive OS."""

    def __init__(self, *, clock=time.monotonic, request_manager=None):
        self._clock = clock
        self._request_manager = request_manager
        self._manager = None
        self._subscriptions = []
        self._sessions: list[_Session] = []
        self._sessions_dirty = _dirty_event()
        self._current_dirty = _dirty_event()
        self._sessions_at = 0
        self._current_at = 0
        self._current_source = None
        self._last_source: str | None = None
        self._pending = None
        self._reading = False
        self._discard_pending = False
        self._closed = False
        self._failures = 0
        self._retry_at = 0
        self._operation = "initialization"
        self._operation_at = 0
        self._last_slow_log = float("-inf")
        self.session_ids: tuple[str, ...] = ()

    async def read(self, selected: str, *, timeout: float = 5) -> MediaSnapshot | None:
        snapshots = await self._read_bounded(selected, timeout)
        return snapshots[0] if snapshots else None

    async def read_all(self, *, timeout: float = 2) -> tuple[MediaSnapshot, ...]:
        """Read active sessions once, sharing the same cache and request budget."""
        return await self._read_bounded(None, timeout)

    async def _read_bounded(self, selected, timeout):
        if self._reading:
            raise MediaUnavailable("Another Windows media read is in progress")
        self._reading = True
        try:
            return await self._read_once(selected, timeout)
        finally:
            self._reading = False

    async def _read_once(self, selected, timeout):
        if self._closed:
            raise MediaUnavailable("Windows media source is closed")
        if self._pending is not None:
            if not self._pending.done():
                raise MediaUnavailable("Previous Windows media request is still pending")
            # A timed-out request may complete later. Never publish its old result.
            with contextlib.suppress(Exception, asyncio.CancelledError):
                self._pending.result()
            self._pending = None
            if self._discard_pending:
                self._reset()
        if self._clock() < self._retry_at:
            raise MediaUnavailable("Windows media recovery backoff is active")
        self._discard_pending = False
        started = self._clock()
        task = self._pending = asyncio.create_task(self._read(selected))
        try:
            # wait_for() waits for cancellation to finish in PyWinRT. Keep ownership
            # of the request instead: a timeout must never start overlapping work.
            done, _ = await asyncio.wait((task,), timeout=timeout)
        except asyncio.CancelledError:
            self._discard_pending = True
            self._failed(TimeoutError("Windows media read was interrupted"))
            raise
        if not done:
            self._discard_pending = True
            self._failed(TimeoutError(f"Windows media read exceeded {timeout:g}s"))
            raise MediaUnavailable("Windows media request timed out")
        self._pending = None
        try:
            result = task.result()
        except (OSError, RuntimeError, TimeoutError) as error:
            self._failed(error)
            self._reset()
            raise MediaUnavailable(str(error)) from error
        if self._failures:
            logger.info("Windows media recovered after %d failed reads", self._failures)
        self._failures = 0
        self._retry_at = 0
        self._log_slow("read", self._clock() - started)
        return result

    def _begin(self, operation):
        self._operation = operation
        self._operation_at = self._clock()

    def _failed(self, error, session=None):
        if session is not None:
            session.failures += 1
            failures = session.failures
            session.error = error
            session.invalidate_metadata()
        else:
            self._failures += 1
            failures = self._failures
        delay = RETRY_DELAYS[min(failures - 1, len(RETRY_DELAYS) - 1)]
        if session is not None:
            session.retry_at = self._clock() + delay
        else:
            self._retry_at = self._clock() + delay
        code = getattr(error, "winerror", None)
        hresult = f"0x{code & 0xFFFFFFFF:08X}" if isinstance(code, int) else "n/a"
        logger.warning(
            "Windows media failed: operation=%s; source=%r; elapsed=%.2fs; "
            "HRESULT=%s; error=%s: %s; retry_in=%ss",
            self._operation,
            session.source if session else "manager",
            self._clock() - self._operation_at,
            hresult,
            type(error).__name__,
            error,
            delay,
        )

    async def _await_operation(self, operation):
        # Own the completion callback instead of PyWinRT's cancellation wrapper.
        # On a read timeout this future stays alive; close() can detach the Python
        # task without waiting for native cancellation. Late callbacks are harmless.
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def finish(op):
            if future.done():
                return
            try:
                future.set_result(op.get_results())
            except Exception as error:
                future.set_exception(error)

        def completed(op, _status):
            with contextlib.suppress(RuntimeError):  # loop may already be closed
                loop.call_soon_threadsafe(finish, op)

        operation.completed = completed
        result = await future
        if self._discard_pending:
            raise MediaUnavailable("Discarded a late Windows media result")
        self._log_slow(self._operation, self._clock() - self._operation_at)
        return result

    def _log_slow(self, operation, elapsed):
        if elapsed >= 1.5 and self._clock() - self._last_slow_log >= 30:
            logger.warning("Windows media slow: operation=%s; elapsed=%.2fs", operation, elapsed)
            self._last_slow_log = self._clock()

    def _subscribe(self, target, event, handler, subscriptions):
        active = Event()
        active.set()
        weak_handler = WeakMethod(handler)

        def changed(*args):
            callback = weak_handler()
            if active.is_set() and callback is not None:
                callback(*args)

        try:
            token = getattr(target, f"add_{event}")(changed)
            subscriptions.append((target, event, token, active))
        except (OSError, RuntimeError) as error:
            logger.debug("Windows media event %s unavailable; using polling: %s", event, error)

    @staticmethod
    def _unsubscribe(subscriptions):
        for target, event, token, active in subscriptions:
            # Even if the broker rejects revocation, obsolete callbacks must not
            # invalidate a new generation or keep this reader/session alive.
            active.clear()
            try:
                getattr(target, f"remove_{event}")(token)
            except (OSError, RuntimeError):
                logger.debug("Cannot remove Windows media event %s", event, exc_info=True)
        subscriptions.clear()

    def _sessions_changed(self, *_):
        self._sessions_dirty.set()
        self._current_dirty.set()

    def _current_changed(self, *_):
        self._current_dirty.set()

    async def _refresh_sessions(self):
        if self._manager is None:
            request = self._request_manager
            if request is None:
                from winrt.windows.media.control import (
                    GlobalSystemMediaTransportControlsSessionManager,
                )

                request = GlobalSystemMediaTransportControlsSessionManager.request_async
            self._begin("RequestAsync")
            self._manager = await self._await_operation(request())
            if self._manager is None:
                raise MediaUnavailable("Windows returned no media manager")
            self._subscribe(
                self._manager, "sessions_changed", self._sessions_changed, self._subscriptions
            )
            self._subscribe(
                self._manager, "current_session_changed", self._current_changed, self._subscriptions
            )
        if not self._sessions_dirty.is_set() and self._clock() < self._sessions_at:
            return
        self._sessions_dirty.clear()
        self._begin("GetSessions")
        handles = list(self._manager.get_sessions())
        sessions = []
        errors = []
        for handle in handles:
            # Compare session identity, not just app ID: a restarted player can keep
            # its app ID, and several sessions can belong to the same application.
            cached = next((s for s in self._sessions if s.handle == handle), None)
            if cached is None:
                self._begin("SourceAppUserModelId")
                try:
                    source = handle.source_app_user_model_id
                except (OSError, RuntimeError) as error:
                    errors.append(error)
                    logger.warning("Windows media session could not be identified: %s", error)
                    continue
                cached = _Session(handle, source)
                # Own it immediately so a later failure also releases its handlers.
                self._sessions.append(cached)
                for event, handler in (
                    ("media_properties_changed", cached.invalidate_metadata),
                    ("playback_info_changed", cached.invalidate_playback),
                    ("timeline_properties_changed", cached.invalidate_timeline),
                ):
                    self._subscribe(handle, event, handler, cached.subscriptions)
            sessions.append(cached)
        if errors and not sessions:
            raise errors[-1]
        for old in self._sessions:
            if old not in sessions:
                self._unsubscribe(old.subscriptions)
        self._sessions = sessions
        self.session_ids = tuple(dict.fromkeys(s.source for s in sessions))
        self._sessions_at = self._clock() + SESSION_INTERVAL
        self._current_dirty.set()

    def _playback(self, session):
        if session.playback_dirty.is_set() or self._clock() >= session.playback_at:
            session.playback_dirty.clear()
            self._begin("GetPlaybackInfo")
            status = session.handle.get_playback_info().playback_status
            try:
                session.status = PlaybackStatus(status)
            except ValueError:
                session.status = PlaybackStatus.UNKNOWN
            session.playback_at = self._clock() + PLAYBACK_INTERVAL
        return session.status

    async def _read(self, selected):
        await self._refresh_sessions()
        automatic = selected in (None, "Automatic")
        if automatic and (self._current_dirty.is_set() or self._clock() >= self._current_at):
            self._current_dirty.clear()
            self._begin("GetCurrentSession")
            current = self._manager.get_current_session()
            self._current_source = next(
                (s.source for s in self._sessions if s.handle == current), None
            )
            self._current_at = self._clock() + PLAYBACK_INTERVAL
        ranked = []
        errors = []
        for session in self._sessions:
            if selected not in (None, "Automatic", session.source):
                continue
            if self._clock() < session.retry_at:
                errors.append(session.error)
                continue
            try:
                status = self._playback(session)
            except (OSError, RuntimeError) as error:
                self._failed(error, session)
                errors.append(error)
                continue
            if status == PlaybackStatus.PLAYING:
                priority = 0 if session.source == self._current_source else 1
            elif status == PlaybackStatus.PAUSED:
                priority = (
                    2
                    if session.source == self._last_source
                    else 3
                    if session.source == self._current_source
                    else 4
                )
            else:
                continue
            ranked.append((priority if automatic else 0, session))
        snapshots = []
        readable = False
        for _, session in sorted(ranked, key=lambda item: item[0]):
            try:
                media = await self._snapshot(session)
            except (OSError, RuntimeError) as error:
                if self._discard_pending:
                    raise
                self._failed(error, session)
                errors.append(error)
                continue
            readable = True
            if session.failures:
                logger.info("Windows media session recovered: source=%r", session.source)
            session.failures = 0
            session.retry_at = 0
            session.error = None
            if media is not None:
                snapshots.append(media)
                if selected is not None:
                    self._last_source = media.source
                    break
        if errors and not readable:
            raise errors[-1]
        # A session was removed/replaced during the asynchronous metadata read.
        if self._sessions_dirty.is_set() or (automatic and self._current_dirty.is_set()):
            return ()
        return tuple(snapshots)

    async def _snapshot(self, session):
        if session.metadata_dirty.is_set() or self._clock() >= session.metadata_at:
            session.metadata_dirty.clear()
            self._begin("TryGetMediaPropertiesAsync")
            properties = await self._await_operation(
                session.handle.try_get_media_properties_async()
            )
            session.metadata = (
                (
                    (properties.title or "").strip(),
                    (properties.artist or "").strip(),
                    (properties.album_title or "").strip(),
                )
                if properties is not None
                else ("", "", "")
            )
            session.metadata_at = self._clock() + (
                METADATA_INTERVAL if session.metadata[0] else PLAYBACK_INTERVAL
            )
        if session.timeline_dirty.is_set() or self._clock() >= session.timeline_at:
            session.timeline_dirty.clear()
            self._begin("GetTimelineProperties")
            timeline = session.handle.get_timeline_properties()
            start = timeline.start_time.total_seconds()
            session.timeline = (
                max(0, timeline.position.total_seconds() - start),
                max(0, timeline.end_time.total_seconds() - start),
                timeline.last_updated_time,
            )
            session.timeline_at = self._clock() + PLAYBACK_INTERVAL
        # An event arriving during the await invalidates this snapshot. The next
        # read refreshes it, including the worker's check before Discord publishing.
        if session.metadata_dirty.is_set() or session.playback_dirty.is_set():
            return None
        title, artist, album = session.metadata
        if not title:
            return None
        position, duration, updated = session.timeline
        if session.status == PlaybackStatus.PLAYING and updated is not None:
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            elapsed = (datetime.now(UTC) - updated).total_seconds()
            if 0 <= elapsed <= 86400:
                position += elapsed
        if duration:
            position = min(position, duration)
        return MediaSnapshot(
            session.source, title, artist, album, session.status, position, duration
        )

    def _reset(self):
        for session in self._sessions:
            self._unsubscribe(session.subscriptions)
        self._unsubscribe(self._subscriptions)
        self._sessions.clear()
        self._manager = None
        self._current_source = None
        self.session_ids = ()
        self._sessions_changed()

    async def close(self):
        self._closed = True
        if self._pending is not None:
            self._pending.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await self._pending
            self._pending = None
        self._reset()

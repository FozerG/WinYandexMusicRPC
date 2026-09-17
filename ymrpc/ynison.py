import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, replace
from uuid import NAMESPACE_URL, uuid5

from yandex_music import Client
from yandex_music.ynison import YnisonClientAsync

from .config import data_directory
from .matching import compare, normalize
from .models import MediaSnapshot, PlaybackStatus, Track
from .yandex import track_metadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class YnisonSnapshot:
    media: MediaSnapshot | None = None
    track: Track | None = None
    state: str = "connecting"
    device_name: str = ""
    pause_corrected: bool = False


class YnisonSource:
    def __init__(self):
        self._token = None
        self._task = None
        self._snapshot = YnisonSnapshot(state="auth_required")
        self._updated = 0.0
        self._next_poll = 0.0
        self._speed = 1.0
        self._cache = {}
        self._device_id = uuid5(NAMESPACE_URL, str(data_directory()) + "/ynison").hex
        self._last_error = None

    async def read(self, token: str | None) -> YnisonSnapshot:
        if token != self._token:
            await self.close()
            self._token = token
            self._cache.clear()
            self._snapshot = YnisonSnapshot(state="connecting" if token else "auth_required")
        if not token:
            return self._snapshot
        now = time.monotonic()
        if self._task is None and now >= self._next_poll:
            self._task = asyncio.create_task(self._poll(token))
        await asyncio.sleep(0.02)
        if self._task and self._task.done():
            try:
                self._snapshot = self._task.result()
                self._updated = time.monotonic()
                self._last_error = None
            except Exception as error:
                name = type(error).__name__
                if name != self._last_error:
                    logger.warning("Ynison request failed (%s); retrying", name)
                    self._last_error = name
                self._snapshot = YnisonSnapshot(state="unavailable")
            self._task = None
            self._next_poll = time.monotonic() + 3
        snapshot = self._snapshot
        if snapshot.media and snapshot.media.status == PlaybackStatus.PLAYING:
            position = snapshot.media.position + (time.monotonic() - self._updated) * self._speed
            if snapshot.media.duration:
                position = min(position, snapshot.media.duration)
            snapshot = replace(snapshot, media=replace(snapshot.media, position=position))
        return snapshot

    async def _poll(self, token: str) -> YnisonSnapshot:
        client = YnisonClientAsync(token, self._device_id)
        ready = asyncio.Event()
        client.on_state(lambda state: ready.set())
        connection = asyncio.create_task(client.connect())
        try:
            await asyncio.wait_for(ready.wait(), timeout=8)
            state = client.latest_state
        finally:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(client.disconnect(), timeout=2)
            # The SDK owns a separate redirect task before the state connection exists.
            tasks = [connection]
            redirect = getattr(client, "_redirect_task", None)
            if redirect is not None:
                tasks.append(redirect)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        if state is None:
            return YnisonSnapshot(state="idle")
        queue = state.player_state.player_queue
        index = queue.current_playable_index
        if not 0 <= index < len(queue.playable_list):
            return YnisonSnapshot(state="idle")
        playable = queue.playable_list[index]
        if int(playable.playable_type) != 1:
            return YnisonSnapshot(state="unsupported")
        track_id = playable.playable_id
        track = self._cache.get(track_id)
        if track is None:
            logger.info(
                "Ynison metadata: track_id=%s; fetching directly, no catalog search", track_id
            )
            tracks = await asyncio.to_thread(Client(token=token).tracks, [track_id], timeout=4)
            if not tracks:
                return YnisonSnapshot(state="unavailable")
            track = track_metadata(tracks[0])
            if len(self._cache) >= 128:
                self._cache.pop(next(iter(self._cache)))
            self._cache[track_id] = track
        device_id = state.active_device_id_optional or state.player_state.status.version.device_id
        device = next(
            (d.info.title for d in state.devices if d.info.device_id == device_id),
            "PC/WEB",
        )
        device = device or "PC/WEB"
        status = state.player_state.status
        duration = status.duration_ms / 1000 or track.duration
        position = max(0, status.progress_ms / 1000)
        self._speed = status.playback_speed or 1
        elapsed = time.time() - status.version.timestamp_ms / 1000
        if not status.paused and 0 <= elapsed < 86400:
            position += elapsed * self._speed
        if duration:
            position = min(position, duration)
        media = MediaSnapshot(
            source=f"Yandex Ynison · {device}",
            title=track.full_title,
            artist=track.artist,
            album=track.album,
            duration=duration,
            position=position,
            status=PlaybackStatus.PAUSED if status.paused else PlaybackStatus.PLAYING,
        )
        return YnisonSnapshot(media, track, "direct", device_name=device)

    async def close(self):
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        self._token = None
        self._snapshot = YnisonSnapshot(state="auth_required")
        self._cache.clear()
        self._next_poll = 0


async def correct_pause(snapshot: YnisonSnapshot, windows) -> YnisonSnapshot:
    if not snapshot.media or not snapshot.track or snapshot.media.status != PlaybackStatus.PAUSED:
        return snapshot
    try:
        current = await windows.read("Automatic")
        candidates = [current] if current else []
        for session in windows.session_ids:
            if current and session == current.source:
                continue
            media = await windows.read(session)
            if media:
                candidates.append(media)
        track = replace(snapshot.track, duration=snapshot.track.duration or snapshot.media.duration)
        for media in candidates:
            if media.status != PlaybackStatus.PLAYING or media.duration <= 0 or track.duration <= 0:
                continue
            if media.artist.strip() and track.artist.strip():
                matches = compare(media, track)[0]
            else:
                matches = (
                    bool(normalize(media.title))
                    and normalize(media.title) == normalize(track.full_title)
                    and abs(media.duration - track.duration) <= 2
                )
            if matches:
                return replace(
                    snapshot,
                    media=replace(
                        snapshot.media,
                        status=PlaybackStatus.PLAYING,
                        position=min(media.position, snapshot.media.duration)
                        if snapshot.media.duration
                        else media.position,
                    ),
                    pause_corrected=True,
                )
    except (OSError, RuntimeError, TimeoutError) as error:
        logger.debug("Ynison pause correction unavailable (%s)", type(error).__name__)
    return snapshot

import asyncio
from datetime import UTC, datetime

from .models import MediaSnapshot, PlaybackStatus


class WindowsMediaSource:
    def __init__(self):
        self._manager = None
        self._last_source: str | None = None
        self.session_ids: tuple[str, ...] = ()

    async def read(self, selected: str) -> MediaSnapshot | None:
        try:
            return await asyncio.wait_for(self._read(selected), timeout=5)
        except (OSError, RuntimeError, TimeoutError):
            self._manager = None
            self.session_ids = ()
            raise

    async def _read(self, selected: str) -> MediaSnapshot | None:
        if self._manager is None:
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager,
            )

            self._manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        sessions = list(self._manager.get_sessions())
        self.session_ids = tuple(dict.fromkeys(s.source_app_user_model_id for s in sessions))
        if selected != "Automatic":
            candidates = [s for s in sessions if s.source_app_user_model_id == selected]
        else:
            current = self._manager.get_current_session()
            current_source = current.source_app_user_model_id if current else None
            ranked = []
            for session in sessions:
                try:
                    status = session.get_playback_info().playback_status
                except (OSError, RuntimeError):
                    continue
                source = session.source_app_user_model_id
                if status == PlaybackStatus.PLAYING:
                    priority = 0 if source == current_source else 1
                elif status == PlaybackStatus.PAUSED:
                    priority = (
                        2 if source == self._last_source else 3 if source == current_source else 4
                    )
                else:
                    continue
                ranked.append((priority, session))
            candidates = [session for _, session in sorted(ranked, key=lambda item: item[0])]
        for session in candidates:
            try:
                media = await self._snapshot(session)
            except (OSError, RuntimeError):
                continue
            if media is not None:
                self._last_source = media.source
                return media
        return None

    async def _snapshot(self, session) -> MediaSnapshot | None:
        properties = await session.try_get_media_properties_async()
        playback = session.get_playback_info()
        timeline = session.get_timeline_properties()
        try:
            status = PlaybackStatus(playback.playback_status)
        except ValueError:
            status = PlaybackStatus.UNKNOWN
        if not (properties.title or "").strip() or status not in (
            PlaybackStatus.PLAYING,
            PlaybackStatus.PAUSED,
        ):
            return None
        start = timeline.start_time.total_seconds()
        duration = max(0, timeline.end_time.total_seconds() - start)
        position = max(0, timeline.position.total_seconds() - start)
        if status == PlaybackStatus.PLAYING:
            updated = timeline.last_updated_time
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            elapsed = (datetime.now(UTC) - updated).total_seconds()
            if 0 <= elapsed <= 86400:
                position += elapsed
        if duration:
            position = min(position, duration)
        return MediaSnapshot(
            source=session.source_app_user_model_id,
            title=properties.title.strip(),
            artist=(properties.artist or "").strip(),
            album=(properties.album_title or "").strip(),
            status=status,
            position=position,
            duration=duration,
        )

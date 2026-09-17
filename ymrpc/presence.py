from dataclasses import dataclass
from typing import Any

from .constants import ASSETS_URL, CLIENT_ID_EN, CLIENT_ID_RU_LISTENING
from .models import (
    ActivityType,
    Buttons,
    DisplayFormat,
    Language,
    MediaSnapshot,
    PlaybackStatus,
    Settings,
    Track,
)


def client_id(settings: Settings) -> str:
    if settings.language == Language.ENGLISH:
        return CLIENT_ID_EN
    return CLIENT_ID_RU_LISTENING


def discord_text(value: str, fallback: str = "") -> str:
    value = (value.strip() or fallback)[:128]
    return value + "\u200b" if len(value) == 1 else value


def status_name(media: MediaSnapshot, track: Track | None, display: DisplayFormat) -> str:
    title = (track.full_title if track else "") or media.title
    artist = (track.artist if track else "") or media.artist
    return {
        DisplayFormat.APPLICATION: "Яндекс Музыку",
        DisplayFormat.ARTIST: artist or title,
        DisplayFormat.TRACK: title,
        DisplayFormat.ARTIST_TRACK: " — ".join(part for part in (artist, title) if part),
    }[display]


def build_payload(
    media: MediaSnapshot, track: Track, settings: Settings, wall_time: float
) -> dict[str, Any]:
    english = settings.language == Language.ENGLISH
    playing = media.status == PlaybackStatus.PLAYING
    payload: dict[str, Any] = {
        "activity_type": ActivityType.LISTENING.value,
        "details": discord_text(track.full_title, media.title),
        "state": discord_text(track.artist, "Unknown artist" if english else "Неизвестный артист"),
        "small_image": f"{ASSETS_URL}/{'Playing' if playing else 'Paused'}.png",
        "small_text": ("Playing" if english else "Проигрывается")
        if playing
        else ("On pause" if english else "На паузе"),
    }
    if track.cover:
        payload["large_image"] = track.cover
    payload["name"] = discord_text(status_name(media, track, settings.display_format))
    if track.album:
        payload["large_text"] = discord_text(track.album)
    duration = media.duration or track.duration
    position = max(0, min(media.position, duration)) if duration else max(0, media.position)
    if playing:
        payload["start"] = int(wall_time - position)
        if duration > position:
            payload["end"] = int(wall_time - position + duration)
    buttons = []
    if track.url and settings.buttons in (Buttons.YANDEX_MUSIC_WEB, Buttons.BOTH):
        buttons.append(
            {"label": "Open in browser" if english else "Откр. в браузере", "url": track.url}
        )
    if track.app_url and settings.buttons in (Buttons.YANDEX_MUSIC_APP, Buttons.BOTH):
        buttons.append(
            {"label": "Open in app" if english else "Откр. в прилож.", "url": track.app_url}
        )
    if buttons:
        payload["buttons"] = buttons
    return payload


@dataclass
class PlaybackState:
    identity: tuple[str, str, str] | None = None
    paused_at: float | None = None

    def visible(self, media: MediaSnapshot | None, timeout: int, now: float) -> bool:
        if media is None or media.status not in (PlaybackStatus.PLAYING, PlaybackStatus.PAUSED):
            self.identity = None
            self.paused_at = None
            return False
        if self.identity != media.identity:
            self.identity = media.identity
            self.paused_at = None
        if media.status == PlaybackStatus.PLAYING:
            self.paused_at = None
            return True
        if self.paused_at is None:
            self.paused_at = now
        return timeout < 0 or now - self.paused_at < timeout


@dataclass
class PresenceGrace:
    active: bool = False
    missing_since: float | None = None

    def hold(self, has_payload: bool, transient: bool, now: float) -> bool:
        if has_payload or not transient:
            self.active = has_payload
            self.missing_since = None
            return False
        if not self.active:
            return False
        if self.missing_since is None:
            self.missing_since = now
        if now - self.missing_since < 2:
            return True
        self.active = False
        return False

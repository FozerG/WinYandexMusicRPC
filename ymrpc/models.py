from dataclasses import dataclass
from enum import IntEnum, StrEnum


class ActivityType(IntEnum):
    LISTENING = 2


class Buttons(IntEnum):
    YANDEX_MUSIC_WEB = 1
    YANDEX_MUSIC_APP = 2
    BOTH = 3
    NEITHER = 4


class Language(IntEnum):
    ENGLISH = 0
    RUSSIAN = 1


class DisplayFormat(StrEnum):
    APPLICATION = "application"
    ARTIST = "artist"
    ARTIST_TRACK = "artist_track"
    TRACK = "track"


class CaptureMode(StrEnum):
    WINDOWS = "windows"
    YNISON = "ynison"


class PlaybackStatus(IntEnum):
    UNKNOWN = -1
    CLOSED = 0
    OPENED = 1
    CHANGING = 2
    STOPPED = 3
    PLAYING = 4
    PAUSED = 5


@dataclass(frozen=True)
class Settings:
    capture_mode: CaptureMode = CaptureMode.WINDOWS
    fix_ynison_pause: bool = False
    activity_type: ActivityType = ActivityType.LISTENING
    buttons: Buttons = Buttons.BOTH
    language: Language = Language.RUSSIAN
    display_format: DisplayFormat = DisplayFormat.ARTIST_TRACK
    pause_timeout: int = 300
    show_unknown_media: bool = False
    selected_session: str = "Automatic"


@dataclass(frozen=True)
class MediaSnapshot:
    source: str
    title: str
    artist: str
    album: str = ""
    status: PlaybackStatus = PlaybackStatus.PLAYING
    position: float = 0
    duration: float = 0

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.source, self.title, self.artist


@dataclass(frozen=True)
class Track:
    title: str
    artist: str
    album: str = ""
    duration: float = 0
    cover: str | None = None
    url: str | None = None
    app_url: str | None = None
    source: str = ""
    version: str = ""

    @property
    def full_title(self) -> str:
        return f"{self.title} ({self.version})" if self.version else self.title

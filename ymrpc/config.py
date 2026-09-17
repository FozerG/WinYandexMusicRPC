import configparser
import logging
import os
import tempfile
from pathlib import Path
from threading import RLock

from .constants import APP_NAME
from .models import Buttons, CaptureMode, DisplayFormat, Language, Settings

logger = logging.getLogger(__name__)


def data_directory() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / APP_NAME


class ConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else data_directory() / "settings.ini"
        self._lock = RLock()
        self._parser = configparser.ConfigParser(interpolation=None)
        try:
            if self.path.exists():
                self._parser.read_string(self.path.read_text(encoding="utf-8-sig"))
        except (configparser.Error, UnicodeError, OSError):
            logger.warning("Cannot read settings; using defaults")
            self._parser = configparser.ConfigParser(interpolation=None)
        self._settings = self._load()

    @property
    def settings(self) -> Settings:
        with self._lock:
            return self._settings

    def _load(self) -> Settings:
        section = self._parser["UserSettings"] if self._parser.has_section("UserSettings") else {}

        def enum_value(key, enum, default):
            try:
                return enum[section.get(key, default.name)]
            except KeyError:
                return default

        try:
            timeout = int(section.get("pause_timeout", "300"))
            if not -1 <= timeout <= 86400:
                timeout = 300
        except ValueError:
            timeout = 300
        return Settings(
            capture_mode=enum_value("capture_mode", CaptureMode, CaptureMode.WINDOWS),
            fix_ynison_pause=str(section.get("fix_ynison_pause", "False")).lower() == "true",
            buttons=enum_value("buttons_settings", Buttons, Buttons.BOTH),
            language=enum_value("language", Language, Language.RUSSIAN),
            display_format=enum_value("display_format", DisplayFormat, DisplayFormat.ARTIST_TRACK),
            pause_timeout=timeout,
            show_unknown_media=str(section.get("show_unknown_media", "False")).lower() == "true",
            selected_session=section.get("selected_session", "Automatic") or "Automatic",
        )

    def save(self, settings: Settings) -> None:
        if type(settings.pause_timeout) is not int or not -1 <= settings.pause_timeout <= 86400:
            raise ValueError("Pause timeout must be between -1 and 86400 seconds")
        with self._lock:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read_dict(
                {section: dict(self._parser[section]) for section in self._parser.sections()}
            )
            if not parser.has_section("UserSettings"):
                parser.add_section("UserSettings")
            parser.remove_option("UserSettings", "strong_find")
            parser["UserSettings"].update(
                {
                    "capture_mode": settings.capture_mode.name,
                    "fix_ynison_pause": str(settings.fix_ynison_pause),
                    "activity_type": settings.activity_type.name,
                    "buttons_settings": settings.buttons.name,
                    "language": settings.language.name,
                    "display_format": settings.display_format.name,
                    "pause_timeout": str(settings.pause_timeout),
                    "show_unknown_media": str(settings.show_unknown_media),
                    "selected_session": settings.selected_session,
                }
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.path.parent, delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    parser.write(stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(self.path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            self._parser = parser
            self._settings = settings
            logger.info("Settings saved: %s", settings)

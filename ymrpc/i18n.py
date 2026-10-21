"""UI-independent localization shared by the GUI, worker and Discord payloads.

Use stable keys and named placeholders. Workers send Message objects so queued
events and cached state are rendered in the current language by the UI thread.
"""

import ctypes
import locale
import sys
from dataclasses import dataclass, field

from .locales.en import STRINGS as ENGLISH
from .locales.ru import STRINGS as RUSSIAN
from .models import Language

CATALOGS = {Language.ENGLISH: ENGLISH, Language.RUSSIAN: RUSSIAN}
_language = Language.ENGLISH


def system_language() -> Language:
    """Use Windows' UI language, which can differ from its regional format."""
    if sys.platform == "win32":
        try:
            language_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return Language.RUSSIAN if language_id & 0x3FF == 0x19 else Language.ENGLISH
        except (AttributeError, OSError):
            pass
    try:
        name = locale.getlocale()[0] or ""
    except (ValueError, TypeError):
        name = ""
    return (
        Language.RUSSIAN if name.lower().split("_")[0].split("-")[0] == "ru" else Language.ENGLISH
    )


def set_language(language: Language) -> None:
    global _language
    _language = Language(language)


def tr(key: str, *, language: Language | None = None, **values) -> str:
    selected = _language if language is None else language
    template = CATALOGS[selected].get(key, ENGLISH.get(key))
    if template is None:
        raise KeyError(f"Unknown translation key: {key}")
    return template.format(
        **{
            name: value.render(selected) if isinstance(value, Message) else value
            for name, value in values.items()
        }
    )


@dataclass(frozen=True)
class Message:
    key: str
    values: dict = field(default_factory=dict)

    def render(self, language: Language | None = None) -> str:
        return tr(self.key, language=language, **self.values)


def message(key: str, **values) -> Message:
    return Message(key, values)


def render(value: str | Message) -> str:
    return value.render() if isinstance(value, Message) else value

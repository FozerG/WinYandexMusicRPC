from PyQt6.QtGui import QFont, QFontDatabase

from .constants import resource_path

_loaded_font_ids: list[int] = []


def load_fonts() -> None:
    if _loaded_font_ids:
        return

    font_ids = []
    try:
        for style in ("Regular", "SemiBold", "Bold"):
            path = resource_path(f"fonts/Inter-{style}.otf")
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id == -1:
                raise RuntimeError(f"Cannot load bundled font: {path.name}")
            font_ids.append(font_id)
    except Exception:
        for font_id in font_ids:
            QFontDatabase.removeApplicationFont(font_id)
        raise
    _loaded_font_ids.extend(font_ids)


def application_font() -> QFont:
    load_fonts()
    return QFont("Inter", 10)

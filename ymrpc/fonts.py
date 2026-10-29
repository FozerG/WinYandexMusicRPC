import os
import sys

from PyQt6.QtGui import QFont, QFontDatabase

from .constants import resource_path

_loaded_font_ids: list[int] = []


def configure_text_rendering() -> None:
    """Select Qt's grayscale-capable rasterizer before QApplication is created."""
    if sys.platform == "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows:fontengine=freetype")


def load_fonts() -> None:
    if _loaded_font_ids:
        return

    font_ids = []
    try:
        paths = [
            resource_path(f"fonts/Inter-{style}.ttf") for style in ("Regular", "SemiBold", "Bold")
        ]
        for path in paths:
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
    font = QFont("Inter", 10)
    # Grayscale coverage avoids colored fringes on the translucent window.
    # Vertical hinting preserves letter widths instead of snapping both axes.
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.NoSubpixelAntialias
    )
    font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    return font

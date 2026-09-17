from PyQt6.QtGui import QFont, QFontDatabase

from .constants import resource_path


def load_fonts() -> None:
    if "Inter" not in QFontDatabase.families():
        for path in resource_path("fonts").glob("Inter-*.otf"):
            if QFontDatabase.addApplicationFont(str(path)) == -1:
                raise RuntimeError(f"Cannot load bundled font: {path.name}")


def application_font() -> QFont:
    load_fonts()
    return QFont("Inter", 10)

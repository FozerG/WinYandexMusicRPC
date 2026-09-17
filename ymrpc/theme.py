from .constants import resource_path

STYLE = """
QDialog { background: #101011; color: #ededee; }
QWidget { color: #ededee; font-family: 'Inter'; font-size: 13px; }
QFrame#sidebar { background: #1c1c1f; border-right: 1px solid #323236; }
QLabel#brand { font-size: 18px; font-weight: 700; }
QLabel#heading { font-size: 27px; font-weight: 600; }
QLabel#trackTitle { font-size: 16px; font-weight: 600; }
QLabel#playbackHeading { font-size: 12px; font-weight: 600; color: #d6d6dc; }
QLabel#timecode { font-size: 11px; color: #c7c7d0; }
QProgressBar#playbackProgress { background: #424249; border: none; border-radius: 2px; }
QProgressBar#playbackProgress::chunk { background: #f5ca66; border-radius: 2px; }
QLabel#muted { color: #9898a3; }
QLabel#warning { background: #30291c; color: #efd497; border: 1px solid #554629;
                  border-radius: 8px; padding: 12px; }
QLabel#saved { color: #f5ca66; }
QFrame#card { background: #1a1a1d; border: 1px solid #333338; border-radius: 12px; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { padding: 13px 15px; margin: 3px 0; border-radius: 7px; }
QListWidget::item:selected { background: #343027; color: #f5ca66; }
QListWidget::item:hover { background: #2b2b2f; }
QPushButton, QComboBox, QSpinBox { background: #242427; border: 1px solid #414147;
    border-radius: 7px; padding: 9px 12px; min-height: 18px; }
QPushButton:hover, QComboBox:hover { background: #303035; border-color: #62626b; }
QPushButton:pressed { background: #39393f; }
QPushButton#primary { background: #f5ca66; border-color: #f5ca66; color: #17140d; font-weight: 600; }
QPushButton#primary:hover { background: #ffda85; border-color: #ffda85; }
QPushButton:focus, QComboBox:focus, QSpinBox:focus { border-color: #f5ca66; }
QPushButton:disabled, QSpinBox:disabled { color: #777780; background: #1c1c1f; }
QComboBox::drop-down { border: none; width: 25px; }
QCheckBox { spacing: 10px; padding: 5px 0; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #74747d; border-radius: 4px; background: #222225; }
QCheckBox::indicator:checked { background: #f5ca66; border: 2px solid #f5ca66; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: #101011; }
QScrollBar:vertical { background: #101011; width: 8px; margin: 4px 0; border: none; }
QScrollBar::handle:vertical { background: #45454b; min-height: 25px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; background: #101011; border: none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: #101011; }
QAbstractScrollArea::corner { background: #101011; border: none; }
QPushButton#info { padding: 0; border: none; background: transparent; min-height: 0; }
QPushButton#info:hover { background: #414147; }
QFrame#divider { background: #303034; max-height: 1px; }
"""


STYLE += f"""
QComboBox::down-arrow, QSpinBox::down-arrow {{
    image: url('{resource_path("chevron-down.svg").as_posix()}'); width: 12px; height: 8px;
}}
QSpinBox::up-arrow {{
    image: url('{resource_path("chevron-up.svg").as_posix()}'); width: 12px; height: 8px;
}}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; width: 22px; }}
"""

from .constants import resource_path

STYLE = """
QWidget { color: #f5f5f5; font-family: 'Inter'; font-size: 14px; font-weight: 400; }
QDialog { background: #1f1f1f; }
QDialog#settingsWindow { background: transparent; }
QFrame#sidebar { background: transparent; border: none; }
QLabel { background: transparent; }
QLabel#popupTitle { font-size: 22px; font-weight: 600; }
QLabel#popupBody { font-size: 15px; color: #bfc0c8; }
QLabel#heading { font-size: 30px; font-weight: 700; }
QLabel#brand { font-size: 20px; font-weight: 600; }
QLabel#appBrand { font-size: 14px; font-weight: 400; color: #c6c6cc; padding-left: 6px; }
QLabel#rowTitle { font-size: 17px; font-weight: 600; }
QLabel#trackTitle { font-size: 21px; font-weight: 700; }
QLabel#trackArtist { font-size: 14px; color: #b3b3bc; }
QLabel#subtitle { font-size: 14px; color: #b3b3bc; }
QLabel#muted { color: #b3b3bc; font-size: 14px; }
QLabel#resultTitle { font-size: 14px; font-weight: 400; }
QLabel#connectionName { font-size: 15px; font-weight: 600; }
QLabel#profileUsername { font-size: 13px; color: #b3b3bc; }
QLabel#timecode { font-size: 14px; color: #b3b3bc; }
QLabel#status { font-size: 13px; color: #c1c1c9; }
QLabel#version { font-size: 13px; color: #9e9ea6; padding-left: 10px; }
QLabel#serviceIcon { background: #303030; border-radius: 14px; }
QLabel#warning { background: #30291c; color: #efd497; border: none; border-radius: 12px; padding: 14px; }
QLabel#errorNotice { background: #351e22; color: #ffb4ba; border: none; border-radius: 12px; padding: 14px; }
QFrame#card { background: #272727; border: none; border-radius: 16px; }
QListWidget { background: transparent; border: none; outline: none; }
QPushButton, QComboBox, QSpinBox { background: #303030; border: none; border-radius: 9px;
    padding: 8px 14px; min-height: 22px; font-size: 14px; }
QPushButton:hover, QComboBox:hover, QSpinBox:hover { background: #383838; }
QPushButton:pressed { background: #414141; }
QPushButton#primary { background: #fafafa; color: #202020; font-weight: 400; }
QPushButton#primary:hover { background: #e7e7e7; }
QPushButton#primary:pressed { background: #d4d4d4; }
QPushButton:disabled, QPushButton#primary:disabled, QSpinBox:disabled { color: #85858a; background: #303030; }
QPushButton::menu-indicator { image: none; width: 0; }
QComboBox::drop-down { border: none; width: 36px; }
QComboBox { padding-right: 4px; border: none;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #363636, stop:1 #303030); }
QPushButton#captionButton, QPushButton#captionClose { background: transparent; border: none; border-radius: 0;
    padding: 0; min-height: 40px; max-height: 40px; }
QPushButton#captionButton:hover { background: transparent; }
QPushButton#captionClose:hover { background: transparent; }
QProgressBar#playbackProgress { background: #505050; border: none; border-radius: 3px; }
QProgressBar#playbackProgress::chunk { background: #f5f5f5; border-radius: 3px; }
QScrollArea, QScrollArea > QWidget > QWidget, QScrollArea > QWidget { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 2px 0; border: none; }
QScrollBar::handle:vertical { background: #454545; min-height: 30px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QAbstractScrollArea::corner { background: transparent; border: none; }
QPushButton#info { padding: 0; border: none; background: transparent; min-height: 0; }
QPushButton#info:hover { background: #414141; }
QFrame#divider { background: #303030; max-height: 1px; }
QMenu { background: #303030; border: none; padding: 8px; }
QMenu::item { padding: 12px 20px; }
QMenu::item:selected { background: #444444; border-radius: 6px; }
QMenu::item:disabled { color: #777777; }
"""
STYLE += f"""
QComboBox::down-arrow, QSpinBox::down-arrow {{
    image: url('{resource_path("chevron-down.svg").as_posix()}'); width: 14px; height: 9px;
}}
QComboBox[popupOpen="true"]::down-arrow, QSpinBox::up-arrow {{
    image: url('{resource_path("chevron-up.svg").as_posix()}'); width: 14px; height: 9px;
}}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; width: 22px; }}
"""


def make_style():
    return STYLE

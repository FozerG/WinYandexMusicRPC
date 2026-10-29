"""Rounded, fixed-size window chrome with native title-bar dragging."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QWidget

from .constants import resource_path
from .ui_i18n import bind_text
from .widgets import IconLabel


class CaptionButton(QPushButton):
    def __init__(self, kind, parent):
        super().__init__(parent)
        self.kind = kind
        self.setAutoDefault(False)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setObjectName("captionClose" if kind == "close" else "captionButton")
        self.setFixedSize(46, 40)
        bind_text(self, f"window.{kind}", "setAccessibleName")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            color = ("#753b40" if self.kind == "close" else "#393939")
            if self.isDown():
                color = "#91434b" if self.kind == "close" else "#454545"
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(4, 4, -4, -4), 9, 9)
        painter.setPen(QPen(QColor("#f4f4f4"), 1.35))
        x, y = self.width() / 2, self.height() / 2
        if self.kind == "minimize":
            painter.drawLine(int(x - 6), int(y), int(x + 6), int(y))
        else:
            painter.drawLine(int(x - 7), int(y - 7), int(x + 7), int(y + 7))
            painter.drawLine(int(x + 7), int(y - 7), int(x - 7), int(y + 7))


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.setFixedHeight(48)
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 0, 3, 0)
        row.setSpacing(10)
        icon = IconLabel(QIcon(str(resource_path("YMRPC_ico.ico"))), 22)
        icon.setFixedSize(22, 22)
        title = QLabel("WinYandexMusicRPC", objectName="appBrand")
        for label in (icon, title):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row.addWidget(label)
        row.addStretch()
        row.setSpacing(0)
        self.minimize = CaptionButton("minimize", self)
        self.close_button = CaptionButton("close", self)
        self.minimize.clicked.connect(window.showMinimized)
        self.close_button.clicked.connect(window.close)
        for button in (self.minimize, self.close_button):
            row.addWidget(button, alignment=Qt.AlignmentFlag.AlignTop)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemMove()


class RoundedDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsWindow")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#1f1f1f"))
        painter.setPen(QPen(QColor("#353535"), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 21, 21)


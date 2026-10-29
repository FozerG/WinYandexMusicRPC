"""Shared rounded dialogs for help, errors and update results."""

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .constants import REPO_URL, resource_path
from .fonts import application_font
from .i18n import tr
from .theme import make_style
from .widgets import ActionButton, IconLabel
from .window_frame import CaptionButton, RoundedDialog


class DialogHeader(QWidget):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemMove()
            event.accept()
        else:
            super().mousePressEvent(event)


class MessageDialog(RoundedDialog):
    def __init__(self, parent, title, text="", *, subtitle="", sections=(), rich_text=False,
                 action_text=None, action=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(title)
        self.setFont(application_font())
        self.setStyleSheet(make_style())
        self.setFixedWidth(620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(22)
        self.header = DialogHeader(self)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 16, 0)
        header_layout.setSpacing(16)
        icon = IconLabel(QIcon(str(resource_path("info.svg"))), 38)
        icon.setFixedSize(40, 40)
        header_layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignVCenter)
        heading = QVBoxLayout()
        heading.setSpacing(6)
        heading.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        heading.addWidget(self._label(title, "popupTitle"))
        if subtitle:
            heading.addWidget(self._label(subtitle, "muted"))
        header_layout.addLayout(heading, 1)
        for label in self.header.findChildren(QLabel):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.header)
        self.close_button = CaptionButton("close", self)
        self.close_button.move(self.width() - 50, 6)
        self.close_button.clicked.connect(self.reject)
        if text:
            body = self._label(text, "popupBody")
            if rich_text:
                body.setTextFormat(Qt.TextFormat.RichText)
                body.setOpenExternalLinks(True)
            layout.addWidget(body)
        for section_title, body in sections:
            section = QVBoxLayout()
            section.setSpacing(8)
            section.setAlignment(Qt.AlignmentFlag.AlignTop)
            section.addWidget(self._label(section_title, "rowTitle"))
            section.addWidget(self._label(body, "popupBody"))
            layout.addLayout(section)
        divider = QFrame(objectName="divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        buttons = QHBoxLayout()
        buttons.addStretch()
        if action:
            later = ActionButton(tr("common.later"))
            later.clicked.connect(self.reject)
            buttons.addWidget(later)
        self.primary = ActionButton(action_text or tr("common.got_it"), objectName="primary")
        self.primary.setMinimumWidth(116)
        self.primary.clicked.connect(lambda: self._accept_action(action))
        buttons.addWidget(self.primary)
        layout.addLayout(buttons)

    @staticmethod
    def _label(text, name):
        label = QLabel(text, objectName=name)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        return label

    def _accept_action(self, action):
        if action:
            action()
        self.accept()

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and event.position().y() <= self.header.geometry().bottom()):
            self.windowHandle().startSystemMove()
            event.accept()
        else:
            super().mousePressEvent(event)

    def showEvent(self, event):
        self.setFixedHeight(self.layout().totalHeightForWidth(self.width()))
        if self.parentWidget():
            self.move(self.parentWidget().frameGeometry().center() - self.rect().center())
        super().showEvent(event)
        self.close_button.raise_()


def update_dialog(parent, result):
    if result.key == "updates.available":
        return MessageDialog(
            parent, tr("updates.available_title"), tr("updates.available_body"),
            action_text=tr("updates.download"),
            action=lambda: QDesktopServices.openUrl(QUrl(f"{REPO_URL}/releases/latest")),
        )
    if result.key == "updates.current":
        return MessageDialog(parent, tr("updates.current_title"), tr("updates.current_body"))
    return MessageDialog(parent, tr("updates.failed_title"), tr("updates.failed"))

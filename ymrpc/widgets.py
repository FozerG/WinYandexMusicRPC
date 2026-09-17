from PyQt6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QUrl
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QLabel,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
)


class CoverArt(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 80)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: #303035; border-radius: 10px; font-size: 36px;")
        self.setText("♪")
        self._network = QNetworkAccessManager(self)
        self._reply = None
        self._url = None

    def set_url(self, url):
        if self._url == url:
            return
        self._url = url
        if self._reply:
            self._reply.abort()
        self.clear()
        self.setText("♪")
        if not url or QUrl(url).scheme() != "https":
            return
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(5000)
        reply = self._network.get(request)
        self._reply = reply
        reply.downloadProgress.connect(
            lambda received, _: reply.abort() if received > 2_000_000 else None
        )
        reply.finished.connect(lambda: self._finished(reply, url))

    def _finished(self, reply, url):
        if self._url == url and reply.error() == QNetworkReply.NetworkError.NoError:
            pixmap = QPixmap()
            if pixmap.loadFromData(reply.readAll()):
                self.setPixmap(
                    pixmap.scaled(
                        self.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        if self._reply is reply:
            self._reply = None
        reply.deleteLater()


class ToggleSwitch(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)

    def sizeHint(self):
        return QSize(60 + self.fontMetrics().horizontalAdvance(self.text()), 32)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, point):
        return self.rect().contains(point)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        track = QRectF(1, 3, 46, 26)
        painter.setPen(QPen(QColor("#414147"), 1))
        painter.setBrush(QColor("#242427"))
        painter.drawRoundedRect(track, 13, 13)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f5ca66" if self.isChecked() else "#777780"))
        painter.drawEllipse(QRectF(24 if self.isChecked() else 4, 6, 20, 20))
        painter.setPen(QColor("#ededee"))
        painter.drawText(
            self.rect().adjusted(60, 0, 0, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )


class DropdownDelegate(QStyledItemDelegate):
    def __init__(self, combo, parent):
        super().__init__(parent)
        self.combo = combo

    def sizeHint(self, option, index):
        return QSize(180, 42)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        active = index.row() == self.combo.currentIndex()
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        keyboard = bool(option.state & QStyle.StateFlag.State_Selected)
        background = "#51452b" if active else "#242427"
        if hovered or (keyboard and not active):
            background = "#625437" if active else "#333338"
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(QRectF(option.rect).adjusted(0, 2, 0, -2), 7, 7)
        painter.setFont(option.font)
        painter.setPen(QColor("#f5ca66" if active else "#ededee"))
        text = option.fontMetrics.elidedText(
            str(index.data() or ""), Qt.TextElideMode.ElideRight, option.rect.width() - 24
        )
        painter.drawText(option.rect.adjusted(12, 0, -12, 0), Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()


class DropdownPopup(QFrame):
    def __init__(self, combo):
        super().__init__(combo, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.combo = combo
        self.list = QListView(self)
        self.list.setObjectName("dropdownMenu")
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setMouseTracking(True)
        self.list.setUniformItemSizes(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setStyleSheet(
            "QListView#dropdownMenu { background: transparent; border: none; padding: 0; outline: none; }"
        )
        self.list.setItemDelegate(DropdownDelegate(combo, self.list))
        self.list.clicked.connect(self.choose)
        self.list.installEventFilter(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.list)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#414147"), 1))
        painter.setBrush(QColor("#242427"))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 10, 10)

    def mousePressEvent(self, event):
        point = self.combo.mapFromGlobal(event.globalPosition().toPoint())
        if self.combo.rect().contains(point):
            self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
            self.combo.hidePopup()
            event.accept()
            return
        super().mousePressEvent(event)

    def choose(self, index):
        if index.isValid() and index.flags() & Qt.ItemFlag.ItemIsEnabled:
            self.combo.setCurrentIndex(index.row())
            self.combo.activated.emit(index.row())
            self.combo.hidePopup()

    def hideEvent(self, event):
        QComboBox.hidePopup(self.combo)
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self.choose(self.list.currentIndex())
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.combo.hidePopup()
                return True
        return super().eventFilter(watched, event)


class Dropdown(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup = DropdownPopup(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._popup.isVisible():
            self.hidePopup()
            event.accept()
            return
        super().mousePressEvent(event)

    def showPopup(self):
        if not self.count():
            return
        view = self._popup.list
        view.setModel(self.model())
        view.setModelColumn(self.modelColumn())
        view.setCurrentIndex(self.model().index(self.currentIndex(), self.modelColumn()))
        screen = self.screen().availableGeometry()
        anchor = self.mapToGlobal(QPoint(0, self.height() + 6))
        width = min(self.width(), screen.width())
        height = min(self.count(), 8) * 42 + 16
        below = screen.bottom() - anchor.y()
        if below >= 58:
            height = min(height, below)
        else:
            top = self.mapToGlobal(QPoint(0, 0)).y() - 6
            height = min(height, top - screen.top())
            anchor.setY(top - height)
        self._popup.setGeometry(
            max(screen.left(), min(anchor.x(), screen.right() - width + 1)),
            anchor.y(),
            width,
            max(40, height),
        )
        self._popup.show()
        view.scrollTo(view.currentIndex())
        view.setFocus()

    def hidePopup(self):
        self._popup.hide()
        super().hidePopup()

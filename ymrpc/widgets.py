from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QUrl
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QLabel,
    QListView,
    QListWidget,
    QMenu,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QVBoxLayout,
)


class CoverArt(QLabel):
    def __init__(self, parent=None, *, size=80, circular=False, placeholder="♪",
                 hide_until_loaded=False):
        super().__init__(parent)
        self._hide_until_loaded = hide_until_loaded
        if hide_until_loaded:
            self.hide()
        self._circular = circular
        self._placeholder = placeholder
        self._playback = None
        self._render_key = None
        self._rendered = QPixmap()
        self._image = QPixmap()
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: transparent; font-size: 36px;")
        self.setText(self._placeholder)
        self._network = QNetworkAccessManager(self)
        self._reply = None
        self._url = None

    def set_playback(self, state):
        if state != self._playback:
            self._playback = state
            self.update()

    def set_url(self, url):
        if self._url == url:
            return
        self._url = url
        if self._reply:
            self._reply.abort()
        self._image = QPixmap()
        self.clear()
        self.setText(self._placeholder)
        if self._hide_until_loaded:
            self.hide()
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
                self._image = pixmap
                self.setText("")
                if self._hide_until_loaded:
                    self.show()
                self.update()
        if self._reply is reply:
            self._reply = None
        reply.deleteLater()

    def paintEvent(self, event):
        dpr = self.devicePixelRatioF()
        key = (self._image.cacheKey(), self.width(), self.height(), dpr,
               self.font().toString(), self._playback)
        if key != self._render_key:
            # Antialiased alpha mask at 3x device resolution; clipping alone has hard edges.
            scale = dpr * 3
            layer = QImage(
                round(self.width() * scale),
                round(self.height() * scale),
                QImage.Format.Format_ARGB32_Premultiplied,
            )
            layer.fill(Qt.GlobalColor.transparent)
            painter = QPainter(layer)
            painter.scale(scale, scale)
            painter.setRenderHints(
                QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
            )
            painter.fillRect(self.rect(), QColor("#303030"))
            if self._image.isNull():
                painter.setFont(self.font())
                painter.setPen(QColor("#bbbbc2"))
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._placeholder)
            else:
                side = min(self._image.width(), self._image.height())
                source = QRectF(
                    (self._image.width() - side) / 2, (self._image.height() - side) / 2, side, side
                )
                painter.drawPixmap(QRectF(self.rect()), self._image, source)
            painter.end()
            mask = QImage(layer.size(), QImage.Format.Format_ARGB32_Premultiplied)
            mask.fill(Qt.GlobalColor.transparent)
            mask_painter = QPainter(mask)
            mask_painter.scale(scale, scale)
            mask_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            mask_painter.setPen(Qt.PenStyle.NoPen)
            mask_painter.setBrush(Qt.GlobalColor.white)
            inset = 1.5 if self._circular else 0.75
            bounds = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
            radius = self.width() / 2 if self._circular else 12
            mask_painter.drawRoundedRect(bounds, radius, radius)
            mask_painter.end()
            painter = QPainter(layer)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            painter.drawImage(0, 0, mask)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.scale(scale, scale)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("#303030" if self._circular else "#3c3c3c"),
                                2.5 if self._circular else 0.7))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(bounds, radius, radius)
            if self._playback:
                center = QPointF(self.width() - 18, self.height() - 18)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(Qt.GlobalColor.white)
                painter.drawEllipse(center, 22, 22)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                painter.setBrush(QColor("#303030"))
                painter.drawEllipse(center, 18, 18)
                painter.setBrush(QColor("#f5f5f5"))
                x, y = center.x(), center.y()
                if self._playback == "playing":
                    painter.drawPolygon(QPolygonF([
                        QPointF(x - 5, y - 8), QPointF(x + 8, y), QPointF(x - 5, y + 8),
                    ]))
                else:
                    painter.drawRoundedRect(QRectF(x - 6, y - 7, 4, 14), 0.8, 0.8)
                    painter.drawRoundedRect(QRectF(x + 2, y - 7, 4, 14), 0.8, 0.8)
            painter.end()
            layer = layer.scaled(
                round(self.width() * dpr),
                round(self.height() * dpr),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._rendered = QPixmap.fromImage(layer)
            self._rendered.setDevicePixelRatio(dpr)
            self._render_key = key
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._rendered)


class ToggleSwitch(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def mousePressEvent(self, event):
        self.clearFocus()
        super().mousePressEvent(event)

    def sizeHint(self):
        return QSize(
            (64 + self.fontMetrics().horizontalAdvance(self.text())) if self.text() else 50, 34
        )

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, point):
        return self.rect().contains(point)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        track = QRectF(1, 4, 48, 26)
        painter.setPen(QPen(QColor("#5a5a5a"), 1))
        painter.setBrush(QColor("#393939"))
        painter.drawRoundedRect(track, 13, 13)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f5f5f5" if self.isChecked() else "#b5b5bd"))
        painter.drawEllipse(QRectF(26 if self.isChecked() else 4, 7, 20, 20))
        painter.setPen(QColor("#ededee"))
        if self.hasFocus():
            painter.setPen(QPen(QColor("#eeeeee"), 1, Qt.PenStyle.DotLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0, 0, -1, -1), 5, 5)
        painter.drawText(
            self.rect().adjusted(64, 0, 0, 0),
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
        if active or hovered or keyboard:
            background = "#494949" if active else "#414141"
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(background))
            painter.drawRoundedRect(QRectF(option.rect).adjusted(0, 2, 0, -2), 7, 7)
        painter.setFont(option.font)
        painter.setPen(QColor("#f5f5f5" if active else "#ededee"))
        text = option.fontMetrics.elidedText(
            str(index.data() or ""), Qt.TextElideMode.ElideRight, option.rect.width() - 48
        )
        painter.drawText(option.rect.adjusted(12, 0, -36, 0), Qt.AlignmentFlag.AlignVCenter, text)
        if active:
            painter.setPen(QPen(QColor("#eeeeee"), 1.8, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            x, y = option.rect.right() - 18, option.rect.center().y()
            painter.drawLine(x - 5, y, x - 1, y + 4)
            painter.drawLine(x - 1, y + 4, x + 6, y - 4)
        painter.restore()


class DropdownPopup(QFrame):
    def __init__(self, combo):
        super().__init__(combo, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setObjectName("dropdownPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("QFrame#dropdownPopup { background: transparent; border: none; }")
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
        self.list.viewport().setAutoFillBackground(False)
        self.list.setItemDelegate(DropdownDelegate(combo, self.list))
        self.list.clicked.connect(self.choose)
        self.list.installEventFilter(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.list)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#3a3a3a"))
        gradient.setColorAt(1, QColor("#303030"))
        painter.setBrush(gradient)
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
        self.combo._set_popup_open(False)
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
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._popup = DropdownPopup(self)
        self.currentTextChanged.connect(self._update_width)

    def _update_width(self):
        width = self.fontMetrics().horizontalAdvance(self.currentText()) + 56
        self.setFixedWidth(max(180, min(260, width)))
        self.setToolTip(self.currentText())

    def showEvent(self, event):
        super().showEvent(event)
        self._update_width()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._update_width()

    def wheelEvent(self, event):
        # Let the surrounding page scroll without changing the selected setting.
        event.ignore()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self.clearFocus()
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
        text_width = max(self.fontMetrics().horizontalAdvance(self.itemText(i))
                         for i in range(self.count()))
        width = min(max(self.width(), text_width + 64), screen.width())
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
        self._set_popup_open(True)
        self._popup.show()
        view.scrollTo(view.currentIndex())
        view.setFocus()

    def hidePopup(self):
        self._popup.hide()
        super().hidePopup()

    def _set_popup_open(self, opened):
        self.setProperty("popupOpen", opened)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class NavigationList(QListWidget):
    """Repaint hover from the actual cursor position, including rapid clicks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.viewport().update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.viewport().update()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.viewport().update()


class NavigationDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._icons = {}

    def sizeHint(self, option, index):
        return QSize(180, 54)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(option.rect, QColor("#1f1f1f"))
        rect = QRectF(option.rect).adjusted(0, 3, 0, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        view = self.parent()
        cursor = view.viewport().mapFromGlobal(QCursor.pos())
        hovered = view.viewport().rect().contains(cursor) and view.indexAt(cursor) == index
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#353535" if selected else "#292929"))
            painter.drawRoundedRect(rect, 13, 13)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon:
            dpr = painter.device().devicePixelRatioF()
            key = (icon.cacheKey(), dpr)
            if key not in self._icons:
                # Rasterize the SVG above device resolution, then filter once.
                pixels = round(24 * dpr)
                pixmap = icon.pixmap(QSize(pixels * 3, pixels * 3)).scaled(
                    pixels, pixels, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                pixmap.setDevicePixelRatio(dpr)
                self._icons[key] = pixmap
            painter.drawPixmap(
                int(rect.left() + 15), int(rect.center().y() - 12), self._icons[key]
            )
        font = option.font
        font.setPixelSize(15)
        font.setWeight(600 if selected else 400)
        painter.setFont(font)
        painter.setPen(QColor("#fafafa" if selected else "#bfc0ca"))
        painter.drawText(
            rect.adjusted(52, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter, str(index.data())
        )
        painter.restore()


class RoundedMenu(QMenu):
    def __init__(self, parent=None, *, compact=False):
        super().__init__(parent)
        self._compact = compact
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("""
            QMenu { color: #eeeeee; background: transparent; border: none; padding: 8px; }
            QMenu::item { background: transparent; padding: 11px 18px; border-radius: 7px; }
            QMenu::item:selected { background: #494949; }
            QMenu::separator { height: 1px; background: #505050; margin: 6px 10px; }
        """)
        if compact:
            self.setMinimumWidth(224)
            self.setStyleSheet(self.styleSheet() + """
                QMenu::item { padding: 9px 14px; border-radius: 6px; }
                QMenu::item:selected { background: #353535; }
                QMenu::item:disabled { color: #777777; }
                QMenu::separator { background: #454545; margin: 5px 0; }
            """)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#3a3a3a"))
        gradient.setColorAt(1, QColor("#303030"))
        painter.setBrush(QColor("#1f1f1f") if self._compact else gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 10, 10)
        painter.end()
        super().paintEvent(event)


class ActionButton(QPushButton):
    """Derive hover from the cursor, independent of focus and checked state."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAutoDefault(False)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def style_option(self):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.state &= ~(QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_On)
        cursor = self.mapFromGlobal(QCursor.pos())
        popup = QApplication.activePopupWidget()
        hovered = self.isVisible() and self.rect().contains(cursor) and popup is None
        if hovered:
            option.state |= QStyle.StateFlag.State_MouseOver
        elif not self.hasFocus():
            option.state &= ~QStyle.StateFlag.State_Sunken
        return option

    def setMenu(self, menu):
        previous = self.menu()
        if previous:
            previous.aboutToHide.disconnect(self._menu_closed)
        super().setMenu(menu)
        if menu:
            menu.aboutToHide.connect(self._menu_closed)

    def _menu_closed(self):
        self.setDown(False)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, self.style_option(), painter, self)


class TrailingButton(ActionButton):
    def __init__(self, direction, parent=None):
        super().__init__(parent)
        self.direction = direction

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 62, 38)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        option = self.style_option()
        option.text = ""
        option.features &= ~QStyleOptionButton.ButtonFeature.HasMenu
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)
        painter.setFont(self.font())
        painter.setPen(option.palette.color(QPalette.ColorRole.ButtonText))
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        group_width = text_width + 24
        left = (self.width() - group_width) / 2
        painter.drawText(
            QRectF(left, 0, text_width, self.height()), Qt.AlignmentFlag.AlignVCenter, self.text()
        )
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(option.palette.color(QPalette.ColorRole.ButtonText), 1.4))
        x, y = round(left + text_width + 19), self.height() // 2
        if self.direction == "right":
            painter.drawLine(x - 3, y - 4, x + 1, y)
            painter.drawLine(x + 1, y, x - 3, y + 4)
        else:
            d = -1 if self.isChecked() else 1
            painter.drawLine(x - 4, y - 2 * d, x, y + 2 * d)
            painter.drawLine(x, y + 2 * d, x + 4, y - 2 * d)


class IconButton(ActionButton):
    def paintEvent(self, event):
        option = self.style_option()
        option.text = ""
        option.icon = QIcon()
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)
        painter.setFont(self.font())
        painter.setPen(option.palette.color(QPalette.ColorRole.ButtonText))
        size = self.iconSize()
        width = size.width() + 13 + self.fontMetrics().horizontalAdvance(self.text())
        x = (self.width() - width) // 2
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        self.icon().paint(
            painter, x, (self.height() - size.height()) // 2, size.width(), size.height(), mode=mode
        )
        painter.drawText(
            self.rect().adjusted(x + size.width() + 13, 0, -8, 0),
            Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )


class IconLabel(QLabel):
    def __init__(self, icon, size, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.icon = icon
        self.icon_size = size

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        self.icon.paint(
            painter,
            (self.width() - self.icon_size) // 2,
            (self.height() - self.icon_size) // 2,
            self.icon_size,
            self.icon_size,
        )

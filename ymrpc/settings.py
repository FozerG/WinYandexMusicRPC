from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .config import ConfigStore
from .constants import resource_path
from .fonts import load_fonts
from .models import Buttons, CaptureMode, DisplayFormat, Language, PlaybackStatus, Settings
from .presence import status_name
from .theme import STYLE
from .widgets import CoverArt, Dropdown, ToggleSwitch


class SettingsDialog(QDialog):
    saved = pyqtSignal()
    login_requested = pyqtSignal()
    logout_requested = pyqtSignal()
    autostart_changed = pyqtSignal(bool)
    updates_requested = pyqtSignal()
    logs_requested = pyqtSignal()

    def __init__(self, config: ConfigStore, sessions: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.config = config
        self._logged_in = False
        self.setWindowTitle("WinYandexMusicRPC")
        self.setWindowIcon(QIcon(str(resource_path("YMRPC_ico.ico"))))
        load_fonts()
        self.resize(860, 610)
        self.setMinimumSize(860, 610)
        self.setStyleSheet(STYLE)
        settings = config.settings
        self.language = self._combo(
            [("Русский", Language.RUSSIAN), ("English", Language.ENGLISH)], settings.language
        )
        self.buttons = self._combo(
            [
                ("Браузер и приложение", Buttons.BOTH),
                ("Только браузер", Buttons.YANDEX_MUSIC_WEB),
                ("Только приложение", Buttons.YANDEX_MUSIC_APP),
                ("Без кнопок", Buttons.NEITHER),
            ],
            settings.buttons,
        )
        self.display = self._combo(
            [
                ("Яндекс Музыка", DisplayFormat.APPLICATION),
                ("Артист", DisplayFormat.ARTIST),
                ("Артист — Трек", DisplayFormat.ARTIST_TRACK),
                ("Трек", DisplayFormat.TRACK),
            ],
            settings.display_format,
        )
        self.capture_mode = self._combo(
            [("Windows.Media.Control", CaptureMode.WINDOWS), ("Yandex Ynison", CaptureMode.YNISON)],
            settings.capture_mode,
        )
        self.session = Dropdown()
        self.session.setMinimumWidth(220)
        self.session.setMaximumWidth(350)
        self.session.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.update_sessions(sessions)
        self.never_hide = ToggleSwitch("Не отключать во время паузы")
        self.never_hide.setChecked(settings.pause_timeout == -1)
        self.pause_timeout = QSpinBox()
        self.pause_timeout.setRange(0, 86400)
        self.pause_timeout.setSuffix(" сек.")
        self.pause_timeout.setSpecialValueText("Сразу")
        self.pause_timeout.setValue(max(0, settings.pause_timeout))
        self.pause_timeout.setEnabled(not self.never_hide.isChecked())
        self.never_hide.toggled.connect(lambda checked: self.pause_timeout.setEnabled(not checked))
        self.show_unknown = ToggleSwitch("Показывать непроверенное медиа")
        self.show_unknown.setChecked(settings.show_unknown_media)
        self.warning = self._label(
            "Могут отображаться видео из браузера и другое медиа. Выберите конкретное приложение "
            "для захвата, чтобы уменьшить вероятность лишней активности.",
            "warning",
        )
        self.warning.setVisible(settings.show_unknown_media)
        self.show_unknown.toggled.connect(self.warning.setVisible)
        self.autostart = ToggleSwitch("Запускать вместе с Windows")
        self.autostart.toggled.connect(self.autostart_changed)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(250)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(18, 28, 18, 22)
        left.addWidget(self._label("WinYandexMusicRPC", "brand"))
        left.addWidget(self._label("Сделано с любовью ❤️", "muted"))
        left.addSpacing(30)
        self.navigation = QListWidget()
        self.navigation.addItems(["Обзор", "Активность", "Захват медиа", "Приложение"])
        left.addWidget(self.navigation, 1)
        account_card = QFrame(objectName="card")
        account_layout = QVBoxLayout(account_card)
        account_layout.setContentsMargins(14, 18, 14, 18)
        account_layout.setSpacing(16)
        account_header = QHBoxLayout()
        account_header.setSpacing(9)
        yandex_icon = QLabel()
        yandex_icon.setFixedSize(24, 24)
        yandex_icon.setPixmap(QIcon(str(resource_path("yandex.svg"))).pixmap(24, 24))
        account_header.addWidget(yandex_icon)
        account_header.addWidget(self._label("Вход в Яндекс"), 1)
        self.account_info = QPushButton(objectName="info")
        self.account_info.setIcon(QIcon(str(resource_path("info.svg"))))
        self.account_info.setIconSize(QSize(17, 17))
        self.account_info.setFixedSize(24, 24)
        self.account_info.setToolTip("Зачем входить через Яндекс?")
        self.account_info.setAccessibleName("Информация о входе в Яндекс")
        self.account_info.clicked.connect(self._show_account_info)
        account_header.addWidget(self.account_info)
        account_layout.addLayout(account_header)
        self.account_label = self._label("Без авторизации")
        account_layout.addWidget(self.account_label)
        self.login = QPushButton("Войти в Яндекс")
        self.logout = QPushButton("Выйти из аккаунта")
        self.login.clicked.connect(self.login_requested)
        self.logout.clicked.connect(self.logout_requested)
        self.logout.hide()
        account_layout.addWidget(self.login)
        account_layout.addWidget(self.logout)
        left.addWidget(account_card)
        left.addSpacing(10)
        left.addWidget(self._label(f"WinYandexMusicRPC  ·  {__version__}", "muted"))
        root.addWidget(sidebar)
        right = QVBoxLayout()
        right.setContentsMargins(24, 24, 24, 20)
        right.setSpacing(18)
        self.pages = QStackedWidget()
        right.addWidget(self.pages, 1)
        root.addLayout(right, 1)

        overview = self._page("Обзор", "Текущий трек и состояние статуса Discord.")
        self.capture_notice = self._label("", "warning")
        overview.addWidget(self.capture_notice)
        self._update_capture_notice()
        card = QFrame(objectName="card")
        now = QVBoxLayout(card)
        now.setContentsMargins(18, 18, 18, 18)
        now.setSpacing(8)
        self.playback_heading = self._label("Сейчас в плеере", "playbackHeading")
        now.addWidget(self.playback_heading)
        now.addSpacing(10)
        track_row = QHBoxLayout()
        track_row.setSpacing(14)
        self.cover = CoverArt()
        track_row.addWidget(self.cover)
        track_text = QVBoxLayout()
        track_text.setSpacing(4)
        self.track_title = self._label("Музыка ещё не играет", "trackTitle")
        self.track_artist = self._label("Откройте плеер и включите трек", "muted")
        self.track_album = self._label("", "muted")
        track_text.addWidget(self.track_title)
        track_text.addWidget(self.track_artist)
        track_text.addWidget(self.track_album)
        timeline = QHBoxLayout()
        timeline.setSpacing(9)
        self.elapsed = self._label("00:00", "timecode")
        self.duration = self._label("—:—", "timecode")
        self.progress = QProgressBar()
        self.progress.setObjectName("playbackProgress")
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        timeline.addWidget(self.elapsed)
        timeline.addWidget(self.progress, 1)
        timeline.addWidget(self.duration)
        track_text.addLayout(timeline)
        track_row.addLayout(track_text, 1)
        now.addLayout(track_row)
        now.addSpacing(10)
        self.status_label = self._label("Ожидание воспроизведения")
        self.track_source = self._label("", "muted")
        self.track_link = self._label("")
        self.track_link.setOpenExternalLinks(True)
        now.addWidget(self.status_label)
        now.addWidget(self.track_source)
        now.addWidget(self.track_link)
        overview.addWidget(card)
        overview.addSpacing(8)
        self.search_heading = self._label("Информация о поиске", "brand")
        self.search_description = self._label("3 источника", "muted")
        overview.addWidget(self.search_heading)
        overview.addWidget(self.search_description)
        self.source_labels = {}
        self.source_rows = {}
        for source, label in (
            ("Yandex", "Яндекс Музыка"),
            ("iTunes", "iTunes"),
            ("Deezer", "Deezer"),
        ):
            row = QHBoxLayout()
            row.addWidget(self._label(label), 1)
            status = self._label("—  Не использовался", "muted")
            row.addWidget(status)
            self.source_labels[source] = status
            container = QWidget()
            container.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            overview.addWidget(container)
            self.source_rows[source] = container
        overview.addStretch()

        activity = self._page("Активность", "Настройте, как музыка отображается в Discord.")
        self._row(activity, "Название статуса", "Яндекс Музыка, артист или трек", self.display)
        self._row(activity, "Язык статуса", "Подписи и кнопки в Discord", self.language)
        self._row(activity, "Ссылки на трек", "Кнопки доступного каталога", self.buttons)
        self._row(activity, "Отключение после паузы", "0 — скрывать сразу", self.pause_timeout)
        activity.addWidget(self.never_hide)
        activity.addStretch()

        capture = self._page("Захват медиа", "Выберите плеер и правила публикации.")
        self._row(capture, "Режим захвата", "Источник текущего воспроизведения", self.capture_mode)
        self.ynison_warning = self._label(
            "Ynison получает состояние вашего аккаунта с серверов Яндекса, а не из медиасессий "
            "компьютера. В статусе может отображаться музыка с телефона или другого устройства. "
            "Также поддерживаются подкасты и ваши загруженные треки в Яндекс Музыке. "
            "Режим экспериментальный: иногда сервер сообщает о паузе во время воспроизведения; "
            "на телефонах обычно работает стабильнее. Требуется вход в аккаунт Яндекс.",
            "warning",
        )
        capture.addWidget(self.ynison_warning)
        self.windows_description = self._label(
            "Windows.Media.Control получает название трека, исполнителя и состояние плеера "
            "из Windows. Можно слушать музыку в VK, Spotify, Apple Music и других приложениях "
            "или браузерах, которые передают эти данные Windows. Найденные в каталогах треки "
            "появляются в статусе Discord.",
            "warning",
        )
        capture.addWidget(self.windows_description)
        self.ynison_controls = QWidget()
        fix_layout = QHBoxLayout(self.ynison_controls)
        fix_layout.setContentsMargins(0, 0, 0, 0)
        self.fix_pause = ToggleSwitch("Исправлять паузу")
        self.fix_pause.setChecked(settings.fix_ynison_pause)
        fix_layout.addWidget(self.fix_pause)
        fix_layout.addStretch()
        pause_info = QPushButton(objectName="info")
        pause_info.setIcon(QIcon(str(resource_path("info.svg"))))
        pause_info.setIconSize(QSize(17, 17))
        pause_info.setFixedSize(24, 24)
        pause_info.setToolTip("Как работает исправление паузы?")
        pause_info.setAccessibleName("Информация об исправлении паузы")
        pause_info.clicked.connect(self._show_pause_info)
        fix_layout.addWidget(pause_info)
        capture.addWidget(self.ynison_controls)
        self.windows_controls = QWidget()
        windows_layout = QVBoxLayout(self.windows_controls)
        windows_layout.setContentsMargins(0, 0, 0, 0)
        windows_layout.setSpacing(12)
        self._row(windows_layout, "Приложение", "Активные медиасессии Windows", self.session)
        windows_layout.addWidget(self.show_unknown)
        windows_layout.addWidget(self.warning)
        capture.addWidget(self.windows_controls)
        self.capture_mode.currentIndexChanged.connect(self._update_capture_mode)
        self._update_capture_mode()
        capture.addStretch()

        application = self._page("Приложение", "Запуск, обновления и диагностика.")
        application.addWidget(self.autostart)
        application.addSpacing(25)
        self.update_button = QPushButton("Проверить обновления")
        self.update_button.clicked.connect(self.updates_requested)
        self._row(
            application, "Обновления", "При запуске сообщим о новой версии", self.update_button
        )
        logs = QPushButton("Открыть журнал")
        logs.clicked.connect(self.logs_requested)
        self._row(application, "Журнал работы", "Только текущий и предыдущий запуск", logs)
        application.addStretch()

        footer = QHBoxLayout()
        footer.setSpacing(14)
        self.save_status = self._label("", "saved")
        footer.addWidget(self.save_status, 1)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.reject)
        self.save_button = QPushButton("Сохранить", objectName="primary")
        self.save_button.clicked.connect(self._save)
        self.save_button.hide()
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(3000)
        self.save_timer.timeout.connect(self.save_status.clear)
        footer.addWidget(close)
        footer.addWidget(self.save_button)
        right.addLayout(footer)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        for control in (self.language, self.buttons, self.display, self.session, self.capture_mode):
            control.currentIndexChanged.connect(self._update_dirty)
        self.pause_timeout.valueChanged.connect(self._update_dirty)
        self.show_unknown.toggled.connect(self._update_dirty)
        self.never_hide.toggled.connect(self._update_dirty)
        self.fix_pause.toggled.connect(self._update_dirty)

    def _update_capture_mode(self):
        ynison = self.capture_mode.currentData() == CaptureMode.YNISON
        self.windows_controls.setVisible(not ynison)
        self.windows_description.setVisible(not ynison)
        self.ynison_warning.setVisible(ynison)
        self.ynison_controls.setVisible(ynison)

    def _update_capture_notice(self, auth_required=None):
        ynison = self.config.settings.capture_mode == CaptureMode.YNISON
        missing = not self._logged_in if auth_required is None else auth_required
        self.capture_notice.setVisible(ynison and missing)
        if ynison:
            self.capture_notice.setText("Для работы режима Ynison войдите в аккаунт Яндекс.")
            self.capture_notice.setStyleSheet(
                "background: #351e22; color: #ffb4ba; border: 1px solid #85434b; "
                "border-radius: 8px; padding: 12px;"
            )

    def _show_pause_info(self):
        QMessageBox.information(
            self,
            "Исправление паузы Ynison",
            "Яндекс Музыка в браузере и настольном приложении иногда передаёт через Ynison "
            "статус «На паузе», хотя музыка играет. Эта проблема встречается давно; на телефонах "
            "статус обычно передаётся корректно.\n\n"
            "Переключатель позволяет сверять трек с медиасессиями этого компьютера через "
            "Windows.Media.Control. Если совпадают название, исполнитель и длительность и "
            "локальный плеер воспроизводит трек, программа исправляет паузу и использует его "
            "текущую позицию. Для треков без исполнителя нужны точное совпадение названия и "
            "разница длительности не больше двух секунд. Без подходящей локальной сессии "
            "сохраняются данные Ynison.",
        )

    @staticmethod
    def _label(text, name=""):
        label = QLabel(text, objectName=name)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        return label

    def _page(self, title, subtitle):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(self._label(title, "heading"))
        layout.addWidget(self._label(subtitle, "muted"))
        layout.addSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.setWidget(content)
        self.pages.addWidget(scroll)
        return layout

    def _row(self, layout, title, description, control):
        row = QHBoxLayout()
        row.setContentsMargins(0, 12, 0, 12)
        labels = QVBoxLayout()
        labels.addWidget(self._label(title))
        labels.addWidget(self._label(description, "muted"))
        row.addLayout(labels, 1)
        row.addSpacing(15)
        row.addWidget(control)
        layout.addLayout(row)
        divider = QFrame(objectName="divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

    @staticmethod
    def _combo(items, selected):
        combo = Dropdown()
        combo.setMinimumWidth(220)
        for label, value in items:
            combo.addItem(label, value)
        combo.setCurrentIndex(combo.findData(selected))
        return combo

    def update_sessions(self, sessions: tuple[str, ...]) -> None:
        selected = self.session.currentData() or self.config.settings.selected_session
        self.session.blockSignals(True)
        self.session.clear()
        self.session.addItem("Автоматически", "Automatic")
        for session in sessions:
            if session != "Automatic":
                self.session.addItem(session, session)
        if selected != "Automatic" and selected not in sessions:
            self.session.addItem(f"{selected} (неактивно)", selected)
        self.session.setCurrentIndex(self.session.findData(selected))
        self.session.blockSignals(False)

    def set_account(self, text: str):
        self.account_label.setText(text)
        logged_in = text != "Без авторизации"
        self._logged_in = logged_in
        self._update_capture_notice()
        self.logout.setVisible(logged_in)
        self.login.setText("Сменить аккаунт" if logged_in else "Войти в Яндекс")

    def set_auth_busy(self, busy: bool):
        self.login.setEnabled(not busy)
        self.logout.setEnabled(not busy)

    def set_autostart(self, enabled: bool):
        self.autostart.blockSignals(True)
        self.autostart.setChecked(enabled)
        self.autostart.blockSignals(False)

    def set_track(self, value):
        from html import escape

        media, track, state = value[:3]
        ynison = self.config.settings.capture_mode == CaptureMode.YNISON
        self.search_heading.setText("Источник воспроизведения" if ynison else "Информация о поиске")
        capture_info = value[5] if len(value) > 5 else {}
        self._update_capture_notice(capture_info.get("auth_required"))
        device = capture_info.get("device") or "Ожидание данных об устройстве"
        description = f"Устройство: {device}" if ynison else "3 источника"
        if ynison and capture_info.get("pause_corrected"):
            description += "\nПауза успешно исправлена через Windows.Media.Control"
        self.search_description.setText(description)
        source_states = dict(value[3]) if len(value) > 3 else {}
        statuses = {
            "unused": ("—  Не использовался", "#9898a3"),
            "searching": ("◌  Ищем…", "#f5ca66"),
            "matched": ("✓  Найдено", "#9dd9ad"),
            "not_found": ("×  Не найдено", "#b0b0bb"),
            "unavailable": ("!  Ошибка запроса", "#efd497"),
        }
        for source, label in self.source_labels.items():
            self.source_rows[source].setVisible(not ynison)
            text, color = statuses.get(source_states.get(source, "unused"), statuses["unused"])
            label.setText(text)
            label.setStyleSheet(f"color: {color};")
        self.cover.set_url(track.cover if track else None)
        title = media.title if media else "Музыка ещё не играет"
        self.playback_heading.setText(
            ("На паузе · " if media.status == PlaybackStatus.PAUSED else "Слушает ")
            + status_name(media, track, self.config.settings.display_format)
            if media
            else "Сейчас в плеере"
        )
        duration = (media.duration or (track.duration if track else 0)) if media else 0
        position = max(0, media.position) if media else 0
        if duration:
            position = min(position, duration)
        self.elapsed.setText(self._timecode(position))
        self.duration.setText(self._timecode(duration) if duration else "—:—")
        self.progress.setValue(round(1000 * position / duration) if duration else 0)
        self.track_title.setText(title)
        self.track_artist.setText(media.artist if media else "Откройте плеер и включите трек")
        self.track_album.setText((media.album or (track.album if track else "")) if media else "")
        source = f"{media.source}  ·  " if media else ""
        source += (
            (
                "Получено напрямую из Ynison"
                if state == "direct"
                else f"Подтверждено: {track.source}"
            )
            if track
            else {
                "searching": "Ищем в каталогах…",
                "not_found": "Совпадение не найдено",
                "unavailable": "Не удалось проверить",
                "idle": "",
            }.get(state, "")
        )
        if len(value) > 4 and value[4]:
            source += ("\n" if source else "") + value[4]
        self.track_source.setText(source)
        self.track_link.setTextFormat(Qt.TextFormat.RichText)
        self.track_link.setText(
            f'<a style="color:#f5ca66" href="{escape(track.url, quote=True)}">Открыть трек ↗</a>'
            if track and track.url
            else ""
        )

    @staticmethod
    def _timecode(seconds):
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"

    def _show_account_info(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Вход в Яндекс")
        dialog.setMinimumWidth(470)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        layout.addWidget(self._label("Зачем мне входить через Яндекс?", "brand"))
        text = QLabel(
            "<p>Это не обязательно, но рекомендуется в некоторых случаях. "
            "Если вы используете скрипт в странах, где недоступна "
            '<a style="color:#f5ca66" href="https://clck.ru/3VsPHq">'
            "бесплатная версия Яндекс Музыки</a>, или используете VPN, "
            "вход через Яндекс может помочь избежать ошибок.</p>"
            "<p>Кроме того, авторизация через Яндекс позволяет получить доступ к трекам, "
            "которые недоступны без входа в систему.</p>"
            "<p><b>Если у вас нет подписки «Плюс», вход будет скорее бесполезным.</b></p>"
        )
        text.setWordWrap(True)
        text.setOpenExternalLinks(True)
        layout.addWidget(text)
        close = QPushButton("Понятно")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def _form_settings(self) -> Settings:
        return Settings(
            capture_mode=CaptureMode(self.capture_mode.currentData()),
            fix_ynison_pause=self.fix_pause.isChecked(),
            language=Language(self.language.currentData()),
            buttons=Buttons(self.buttons.currentData()),
            display_format=DisplayFormat(self.display.currentData()),
            selected_session=self.session.currentData(),
            pause_timeout=-1 if self.never_hide.isChecked() else self.pause_timeout.value(),
            show_unknown_media=self.show_unknown.isChecked(),
        )

    def _update_dirty(self):
        self.save_timer.stop()
        self.save_status.clear()
        self.save_button.setVisible(self._form_settings() != self.config.settings)

    def _save(self) -> None:
        settings = self._form_settings()
        try:
            self.config.save(settings)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Настройки не сохранены", str(error))
            return
        self._update_capture_notice()
        self.saved.emit()
        self.save_button.hide()
        self.save_status.setText("Настройки применены")
        self.save_timer.start()

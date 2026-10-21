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
from .i18n import Message, message, render, set_language, tr
from .models import (
    ActivityType,
    Buttons,
    CaptureMode,
    DisplayFormat,
    Language,
    PlaybackStatus,
    Settings,
    Track,
)
from .presence import build_payload
from .search import UNUSED_SOURCES
from .theme import STYLE
from .ui_i18n import TEXT_ROLE, bind_text, retranslate, show_message
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
        set_language(config.settings.app_language)
        self._account = None
        self._track = (None, None, "idle")
        self._status = message("status.waiting")
        self._logged_in = False
        self.setWindowTitle("WinYandexMusicRPC")
        self.setWindowIcon(QIcon(str(resource_path("YMRPC_ico.ico"))))
        load_fonts()
        self.resize(860, 610)
        self.setMinimumSize(860, 610)
        self.setStyleSheet(STYLE)
        settings = config.settings
        self.activity_type = self._combo(
            [
                ("activity.listening", ActivityType.LISTENING),
                ("activity.playing", ActivityType.PLAYING),
            ],
            settings.activity_type,
        )
        self.language = self._combo(
            [("language.russian", Language.RUSSIAN), ("language.english", Language.ENGLISH)],
            settings.language,
        )
        self.app_language = self._combo(
            [("language.russian", Language.RUSSIAN), ("language.english", Language.ENGLISH)],
            settings.app_language,
        )
        self.buttons = self._combo(
            [
                ("buttons.both", Buttons.BOTH),
                ("buttons.browser", Buttons.YANDEX_MUSIC_WEB),
                ("buttons.app", Buttons.YANDEX_MUSIC_APP),
                ("buttons.none", Buttons.NEITHER),
            ],
            settings.buttons,
        )
        self.display = self._combo(
            [
                ("music.name", DisplayFormat.APPLICATION),
                ("display.artist", DisplayFormat.ARTIST),
                ("display.artist_track", DisplayFormat.ARTIST_TRACK),
                ("display.track", DisplayFormat.TRACK),
            ],
            settings.display_format,
        )
        self.capture_mode = self._combo(
            [
                ("capture.windows", CaptureMode.WINDOWS),
                ("capture.ynison", CaptureMode.YNISON),
            ],
            settings.capture_mode,
        )
        self.session = Dropdown()
        self.session.setMinimumWidth(220)
        self.session.setMaximumWidth(350)
        self.session.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.update_sessions(sessions)
        self.never_hide = bind_text(ToggleSwitch(), "pause.never_hide")
        self.never_hide.setChecked(settings.pause_timeout == -1)
        self.pause_timeout = QSpinBox()
        self.pause_timeout.setRange(0, 86400)
        bind_text(self.pause_timeout, "pause.seconds", "setSuffix")
        bind_text(self.pause_timeout, "pause.immediately", "setSpecialValueText")
        self.pause_timeout.setValue(max(0, settings.pause_timeout))
        self.pause_timeout.setEnabled(not self.never_hide.isChecked())
        self.never_hide.toggled.connect(lambda checked: self.pause_timeout.setEnabled(not checked))
        self.show_unknown = bind_text(ToggleSwitch(), "capture.unknown")
        self.show_unknown.setChecked(settings.show_unknown_media)
        self.warning = self._translated_label(
            "capture.unknown_warning",
            "warning",
        )
        self.warning.setVisible(settings.show_unknown_media)
        self.show_unknown.toggled.connect(self.warning.setVisible)
        self.autostart = bind_text(ToggleSwitch(), "app.autostart")
        self.autostart.toggled.connect(self.autostart_changed)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(250)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(18, 28, 18, 22)
        left.addWidget(self._label("WinYandexMusicRPC", "brand"))
        left.addWidget(self._translated_label("app.tagline", "tagline"))
        left.addSpacing(30)
        self.navigation = QListWidget()
        for key in ("nav.overview", "nav.activity", "nav.capture", "nav.application"):
            self.navigation.addItem(tr(key))
            self.navigation.item(self.navigation.count() - 1).setData(TEXT_ROLE, key)
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
        account_header.addWidget(self._translated_label("account.title"), 1)
        self.account_info = QPushButton(objectName="info")
        self.account_info.setIcon(QIcon(str(resource_path("info.svg"))))
        self.account_info.setIconSize(QSize(17, 17))
        self.account_info.setFixedSize(24, 24)
        bind_text(self.account_info, "account.why_tooltip", "setToolTip")
        bind_text(self.account_info, "account.info_accessible", "setAccessibleName")
        self.account_info.clicked.connect(self._show_account_info)
        account_header.addWidget(self.account_info)
        account_layout.addLayout(account_header)
        self.account_label = self._translated_label("account.signed_out")
        account_layout.addWidget(self.account_label)
        self.login = bind_text(QPushButton(), "account.sign_in")
        self.logout = bind_text(QPushButton(), "account.sign_out")
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

        overview = self._page("nav.overview", "overview.description")
        self.capture_notice = self._label("", "warning")
        overview.addWidget(self.capture_notice)
        self._update_capture_notice()
        card = QFrame(objectName="card")
        now = QVBoxLayout(card)
        now.setContentsMargins(18, 18, 18, 18)
        now.setSpacing(8)
        self.playback_heading = self._translated_label("playback.heading", "playbackHeading")
        now.addWidget(self.playback_heading)
        now.addSpacing(10)
        track_row = QHBoxLayout()
        track_row.setSpacing(14)
        self.cover = CoverArt()
        track_row.addWidget(self.cover)
        track_text = QVBoxLayout()
        track_text.setSpacing(4)
        self.track_title = self._translated_label("playback.empty", "trackTitle")
        self.track_artist = self._translated_label("playback.empty_hint", "muted")
        self.track_album = self._label("", "muted")
        self.track_album.hide()
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
        self.status_label = self._translated_label("status.waiting")
        self.track_source = self._label("", "muted")
        self.track_link = self._label("")
        self.track_link.setOpenExternalLinks(True)
        now.addWidget(self.status_label)
        now.addWidget(self.track_source)
        now.addWidget(self.track_link)
        overview.addWidget(card)
        overview.addSpacing(8)
        self.search_heading = self._translated_label("search.heading", "brand")
        self.search_description = self._translated_label("search.description", "muted")
        overview.addWidget(self.search_heading)
        overview.addWidget(self.search_description)
        self.ynison_idle_notice = self._translated_label("capture.ynison_outage", "errorNotice")
        self.ynison_idle_notice.hide()
        overview.addWidget(self.ynison_idle_notice)
        self.source_labels = {}
        self.source_rows = {}
        for source, _ in UNUSED_SOURCES:
            row = QHBoxLayout()
            row.addWidget(
                self._translated_label("music.name") if source == "Yandex" else self._label(source),
                1,
            )
            status = self._translated_label("search.unused", "muted")
            row.addWidget(status)
            self.source_labels[source] = status
            container = QWidget()
            container.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            overview.addWidget(container)
            self.source_rows[source] = container
        overview.addStretch()

        activity = self._page("nav.activity", "activity.description")
        self._row(
            activity,
            "activity.type",
            "activity.type_hint",
            self.activity_type,
        )
        self._row(
            activity,
            "activity.name",
            "activity.name_hint",
            self.display,
        )
        self._row(activity, "activity.language", "activity.language_hint", self.language)
        self._row(
            activity,
            "activity.links",
            "activity.links_hint",
            self.buttons,
        )
        self._row(
            activity,
            "pause.timeout",
            "pause.timeout_hint",
            self.pause_timeout,
            divider=False,
        )
        activity.addWidget(self.never_hide)
        activity.addStretch()

        capture = self._page("nav.capture", "capture.description")
        self._row(
            capture,
            "capture.mode",
            "capture.mode_hint",
            self.capture_mode,
            divider=False,
        )
        self.ynison_warning = self._translated_label(
            "capture.ynison_warning",
            "warning",
        )
        capture.addWidget(self.ynison_warning)
        self.ynison_outage_notice = self._translated_label("capture.ynison_outage", "errorNotice")
        capture.addWidget(self.ynison_outage_notice)
        self.windows_description = self._translated_label(
            "capture.windows_description",
            "warning",
        )
        capture.addWidget(self.windows_description)
        self._divider(capture)
        self.ynison_controls = QWidget()
        fix_layout = QHBoxLayout(self.ynison_controls)
        fix_layout.setContentsMargins(0, 0, 0, 0)
        self.fix_pause = bind_text(ToggleSwitch(), "capture.fix_pause")
        self.fix_pause.setChecked(settings.fix_ynison_pause)
        fix_layout.addWidget(self.fix_pause)
        fix_layout.addStretch()
        pause_info = QPushButton(objectName="info")
        pause_info.setIcon(QIcon(str(resource_path("info.svg"))))
        pause_info.setIconSize(QSize(17, 17))
        pause_info.setFixedSize(24, 24)
        bind_text(pause_info, "capture.pause_tooltip", "setToolTip")
        bind_text(pause_info, "capture.pause_accessible", "setAccessibleName")
        pause_info.clicked.connect(self._show_pause_info)
        fix_layout.addWidget(pause_info)
        capture.addWidget(self.ynison_controls)
        self.windows_controls = QWidget()
        windows_layout = QVBoxLayout(self.windows_controls)
        windows_layout.setContentsMargins(0, 0, 0, 0)
        windows_layout.setSpacing(12)
        self._row(windows_layout, "nav.application", "capture.session_hint", self.session)
        windows_layout.addWidget(self.show_unknown)
        windows_layout.addWidget(self.warning)
        capture.addWidget(self.windows_controls)
        self.capture_mode.currentIndexChanged.connect(self._update_capture_mode)
        self._update_capture_mode()
        capture.addStretch()

        application = self._page("nav.application", "app.description")
        self._row(application, "app.language", "app.language_hint", self.app_language)
        autostart_row = QHBoxLayout()
        autostart_row.setContentsMargins(0, 12, 0, 12)
        autostart_row.addWidget(self.autostart)
        application.addLayout(autostart_row)
        self._divider(application)
        self.update_button = bind_text(QPushButton(), "updates.check")
        self.update_button.clicked.connect(self.updates_requested)
        self._row(
            application,
            "updates.title",
            "updates.description",
            self.update_button,
        )
        logs = bind_text(QPushButton(), "logs.open")
        logs.clicked.connect(self.logs_requested)
        self._row(
            application,
            "logs.title",
            "logs.description",
            logs,
        )
        application.addStretch()

        footer = QHBoxLayout()
        footer.setSpacing(14)
        self.save_status = self._label("", "saved")
        footer.addWidget(self.save_status, 1)
        close = bind_text(QPushButton(), "common.close")
        close.clicked.connect(self.reject)
        self.save_button = bind_text(QPushButton(objectName="primary"), "common.save")
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
        for control in (
            self.activity_type,
            self.language,
            self.app_language,
            self.buttons,
            self.display,
            self.session,
            self.capture_mode,
        ):
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
        self.ynison_outage_notice.setVisible(ynison)
        self.ynison_controls.setVisible(ynison)

    def _update_capture_notice(self, auth_required=None):
        ynison = self.config.settings.capture_mode == CaptureMode.YNISON
        missing = not self._logged_in if auth_required is None else auth_required
        self.capture_notice.setVisible(ynison and missing)
        if ynison:
            self.capture_notice.setText(tr("capture.sign_in_required"))
            self.capture_notice.setStyleSheet(
                "background: #351e22; color: #ffb4ba; border: 1px solid #85434b; "
                "border-radius: 8px; padding: 12px;"
            )

    def _show_pause_info(self):
        show_message(
            self,
            tr("capture.pause_title"),
            tr("capture.pause_help"),
        )

    @staticmethod
    def _label(text, name=""):
        label = QLabel(text, objectName=name)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        return label

    def _translated_label(self, key, name=""):
        return bind_text(self._label("", name), key)

    def _page(self, title, subtitle):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(self._translated_label(title, "heading"))
        layout.addWidget(self._translated_label(subtitle, "muted"))
        layout.addSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.setWidget(content)
        self.pages.addWidget(scroll)
        return layout

    def _row(self, layout, title, description, control, *, divider=True):
        row = QHBoxLayout()
        row.setContentsMargins(0, 12, 0, 12 if divider else 0)
        labels = QVBoxLayout()
        labels.addWidget(self._translated_label(title))
        labels.addWidget(self._translated_label(description, "muted"))
        row.addLayout(labels, 1)
        row.addSpacing(15)
        row.addWidget(control)
        layout.addLayout(row)
        if divider:
            self._divider(layout)

    @staticmethod
    def _divider(layout):
        line = QFrame(objectName="divider")
        line.setFixedHeight(1)
        layout.addWidget(line)

    @staticmethod
    def _combo(items, selected):
        combo = Dropdown()
        combo.setMinimumWidth(220)
        for key, value in items:
            combo.addItem(tr(key), value)
            combo.setItemData(combo.count() - 1, key, TEXT_ROLE)
        combo.setCurrentIndex(combo.findData(selected))
        return combo

    def update_sessions(self, sessions: tuple[str, ...]) -> None:
        self._sessions = sessions
        selected = self.session.currentData() or self.config.settings.selected_session
        self.session.blockSignals(True)
        self.session.clear()
        self.session.addItem(tr("capture.automatic"), "Automatic")
        for session in sessions:
            if session != "Automatic":
                self.session.addItem(session, session)
        if selected != "Automatic" and selected not in sessions:
            self.session.addItem(tr("capture.inactive", session=selected), selected)
        self.session.setCurrentIndex(self.session.findData(selected))
        self.session.blockSignals(False)

    def set_account(self, account: str | Message | None):
        self._account = account
        self.account_label.setText(
            render(account) if account is not None else tr("account.signed_out")
        )
        logged_in = account is not None
        self._logged_in = logged_in
        self._update_capture_notice()
        self.logout.setVisible(logged_in)
        self.login.setText(tr("account.switch") if logged_in else tr("account.sign_in"))

    def set_status(self, status: str | Message):
        self._status = status
        self.status_label.setText(render(status))

    def set_auth_busy(self, busy: bool):
        self.login.setEnabled(not busy)
        self.logout.setEnabled(not busy)

    def set_autostart(self, enabled: bool):
        self.autostart.blockSignals(True)
        self.autostart.setChecked(enabled)
        self.autostart.blockSignals(False)

    def set_track(self, value):
        from html import escape

        self._track = value
        media, track, state = value[:3]
        ynison = self.config.settings.capture_mode == CaptureMode.YNISON
        self.search_heading.setText(
            tr("playback.source_heading") if ynison else tr("search.heading")
        )
        capture_info = value[5] if len(value) > 5 else {}
        self._update_capture_notice(capture_info.get("auth_required"))
        device = capture_info.get("device") or tr("playback.device_waiting")
        description = tr("playback.device", device=device) if ynison else tr("search.description")
        if ynison and capture_info.get("pause_corrected"):
            description += tr("playback.pause_corrected")
        self.search_description.setText(description)
        self.ynison_idle_notice.setVisible(ynison and state == "idle")
        source_states = dict(value[3]) if len(value) > 3 else {}
        statuses = {
            "unused": (tr("search.unused"), "#9898a3"),
            "searching": (tr("search.searching"), "#f5ca66"),
            "matched": (tr("search.matched"), "#9dd9ad"),
            "not_found": (tr("search.not_found"), "#b0b0bb"),
            "unavailable": (tr("search.unavailable"), "#efd497"),
        }
        for source, label in self.source_labels.items():
            self.source_rows[source].setVisible(not ynison)
            text, color = statuses.get(source_states.get(source, "unused"), statuses["unused"])
            label.setText(text)
            label.setStyleSheet(f"color: {color};")
        self.cover.set_url(track.cover if track else None)
        payload = {}
        if media:
            displayed = track or Track(media.title, media.artist, media.album, media.duration)
            payload = build_payload(media, displayed, self.config.settings, wall_time=0)
        self.playback_heading.setText(
            (
                tr("playback.paused_prefix")
                if media.status == PlaybackStatus.PAUSED
                else tr("playback.listening_prefix")
            )
            + payload["name"]
            if media
            else tr("playback.heading")
        )
        duration = (media.duration or (track.duration if track else 0)) if media else 0
        position = max(0, media.position) if media else 0
        if duration:
            position = min(position, duration)
        self.elapsed.setText(self._timecode(position))
        self.duration.setText(self._timecode(duration) if duration else "—:—")
        self.progress.setValue(round(1000 * position / duration) if duration else 0)
        self.track_title.setText(payload.get("details", tr("playback.empty")))
        self.track_artist.setText(payload.get("state", tr("playback.empty_hint")))
        album = payload.get("large_text", "")
        self.track_album.setText(album)
        self.track_album.setVisible(bool(album))
        source = f"{media.source}  ·  " if media else ""
        source += (
            (
                tr("playback.direct")
                if state == "direct"
                else tr("playback.verified", source=track.source)
            )
            if track
            else {
                "searching": tr("playback.searching"),
                "not_found": tr("playback.not_found"),
                "unavailable": tr("playback.unavailable"),
                "idle": "",
            }.get(state, "")
        )
        if len(value) > 4 and value[4]:
            source += ("\n" if source else "") + render(value[4])
        self.track_source.setText(source)
        self.track_link.setTextFormat(Qt.TextFormat.RichText)
        self.track_link.setText(
            f'<a style="color:#f5ca66" href="{escape(track.url, quote=True)}">'
            f"{escape(tr('playback.open_track'))}</a>"
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
        dialog.setWindowTitle(tr("account.title"))
        dialog.setMinimumWidth(470)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        layout.addWidget(self._translated_label("account.why_title", "brand"))
        text = bind_text(QLabel(), "account.help")
        text.setWordWrap(True)
        text.setOpenExternalLinks(True)
        layout.addWidget(text)
        close = bind_text(QPushButton(), "common.got_it")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def _form_settings(self) -> Settings:
        return Settings(
            app_language=Language(self.app_language.currentData()),
            capture_mode=CaptureMode(self.capture_mode.currentData()),
            fix_ynison_pause=self.fix_pause.isChecked(),
            activity_type=ActivityType(self.activity_type.currentData()),
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
            show_message(self, tr("settings.save_failed"), str(error), QMessageBox.Icon.Warning)
            return
        set_language(settings.app_language)
        retranslate(self)
        self.update_sessions(self._sessions)
        self.set_account(self._account)
        self.set_track(self._track)
        self.set_status(self._status)
        self.saved.emit()
        self.save_button.hide()
        self.save_status.setText(tr("settings.saved"))
        self.save_timer.start()

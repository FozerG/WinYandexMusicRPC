from PyQt6.QtCore import QCoreApplication, QEvent, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
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
from .cover_hosts import UNUSED_UPLOADS
from .covers import CoverResult
from .dialogs import MessageDialog
from .fonts import application_font, load_fonts
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
from .theme import make_style
from .ui_i18n import TEXT_ROLE, bind_text, retranslate, show_message
from .widgets import (
    ActionButton,
    CoverArt,
    Dropdown,
    IconButton,
    IconLabel,
    NavigationDelegate,
    NavigationList,
    RoundedMenu,
    ToggleSwitch,
    TrailingButton,
)
from .window_frame import RoundedDialog, TitleBar


class SettingsDialog(RoundedDialog):
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
        self._account_avatar = ""
        self._track = (None, None, "idle")
        self._status = message("status.waiting")
        self._logged_in = False
        self.setWindowTitle("WinYandexMusicRPC")
        self.setWindowIcon(QIcon(str(resource_path("YMRPC_ico.ico"))))
        load_fonts()
        self.setFixedSize(900, 650)
        self.setStyleSheet(make_style())
        self.setFont(application_font())
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
        self.update_sessions(sessions)
        self.never_hide = bind_text(ToggleSwitch(), "pause.never_hide")
        self.never_hide.setChecked(settings.pause_timeout == -1)
        self.pause_timeout = QSpinBox()
        self.pause_timeout.setRange(0, 86400)
        bind_text(self.pause_timeout, "pause.seconds", "setSuffix")
        bind_text(self.pause_timeout, "pause.immediately", "setSpecialValueText")
        self.pause_timeout.setValue(
            settings.last_pause_timeout if settings.pause_timeout == -1 else settings.pause_timeout
        )
        self.pause_timeout.setEnabled(not self.never_hide.isChecked())
        self.never_hide.toggled.connect(lambda checked: self.pause_timeout.setEnabled(not checked))
        self.show_unknown = bind_text(ToggleSwitch(), "capture.unknown")
        self.show_unknown.setChecked(settings.show_unknown_media)
        self.warning = self._translated_label(
            "capture.unknown_warning",
            "warning",
        )
        self.show_unknown.toggled.connect(self.warning.setVisible)
        self.show_unknown_cover = bind_text(ToggleSwitch(), "capture.unknown_cover")
        self.show_unknown_cover.setChecked(settings.show_unknown_cover)
        self.cover_warning = self._translated_label("capture.cover_warning", "warning")
        self.cover_warning.setTextFormat(Qt.TextFormat.RichText)
        self.show_unknown.toggled.connect(self._update_cover_controls)
        self.show_unknown_cover.toggled.connect(self._update_cover_controls)
        self.autostart = ToggleSwitch()
        bind_text(self.autostart, "app.autostart", "setAccessibleName")
        self.autostart.toggled.connect(self.autostart_changed)

        shell = QVBoxLayout(self)
        shell.setContentsMargins(1, 1, 1, 1)
        shell.setSpacing(0)
        self.title_bar = TitleBar(self)
        shell.addWidget(self.title_bar)
        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        shell.addLayout(root, 1)
        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(196)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(14, 8, 10, 22)
        left.setSpacing(0)
        self.navigation = NavigationList()
        for key in ("nav.overview", "nav.activity", "nav.capture", "nav.application"):
            self.navigation.addItem(tr(key))
            self.navigation.item(self.navigation.count() - 1).setData(TEXT_ROLE, key)
        self.navigation.setItemDelegate(NavigationDelegate(self.navigation))
        self.navigation.setIconSize(QSize(26, 26))
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for index, icon in enumerate(("home", "activity", "monitor", "settings")):
            self.navigation.item(index).setIcon(QIcon(str(resource_path(f"{icon}.svg"))))
        left.addWidget(self.navigation, 1)
        left.addSpacing(10)
        left.addWidget(self._label(f"WinYandexMusicRPC  {__version__}", "version"))
        root.addWidget(sidebar)
        right = QVBoxLayout()
        right.setContentsMargins(20, 6, 20, 22)
        right.setSpacing(0)
        self.pages = QStackedWidget()
        right.addWidget(self.pages, 1)
        root.addLayout(right, 1)

        overview = self._page("nav.overview", "overview.description")
        overview.setSpacing(8)
        overview.itemAt(0).widget().setFixedHeight(72)
        self.capture_notice = self._label("", "warning")
        overview.addWidget(self.capture_notice)
        self._update_capture_notice()
        card = QFrame(objectName="card")
        card.setMinimumHeight(164)
        track_row = QHBoxLayout(card)
        track_row.setContentsMargins(18, 18, 18, 18)
        track_row.setSpacing(16)
        self.playback_heading = self._translated_label("playback.heading", "playbackHeading")
        self.playback_heading.hide()
        self.cover = CoverArt(size=128, placeholder_size=44)
        track_row.addWidget(self.cover)
        track_text = QVBoxLayout()
        track_text.setSpacing(8)
        track_text.addStretch()
        self.track_title = self._translated_label("playback.empty", "trackTitle")
        self.track_artist = self._translated_label("playback.empty_hint", "trackArtist")
        self.track_album = self._label("", "muted")
        self.track_album.hide()
        track_text.addWidget(self.track_title)
        track_text.addWidget(self.track_artist)
        track_text.addSpacing(15)
        self.elapsed = self._label("00:00", "timecode")
        self.duration = self._label("—:—", "timecode")
        self.progress = QProgressBar(objectName="playbackProgress")
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        track_text.addWidget(self.progress)
        timeline = QHBoxLayout()
        timeline.addWidget(self.elapsed)
        timeline.addStretch()
        timeline.addWidget(self.duration)
        track_text.addLayout(timeline)
        track_text.addStretch()
        track_row.addLayout(track_text, 1)
        self.track_actions = QWidget()
        actions = QVBoxLayout(self.track_actions)
        actions.setContentsMargins(0, 16, 0, 13)
        self.status_label = self._translated_label("status.waiting", "status")
        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        status_row.addStretch()
        status_row.addWidget(self.status_label)
        actions.addLayout(status_row)
        actions.addStretch()
        self.track_source = self._label("", "muted")
        self.track_link = bind_text(IconButton(objectName="primary"), "playback.open_track")
        self.track_link.setIcon(QIcon(str(resource_path("external.svg"))))
        self.track_link.setIconSize(QSize(21, 21))
        self.track_link.setMinimumWidth(148)
        self.track_link.clicked.connect(self._open_track)
        self.track_link.setEnabled(False)
        actions.addWidget(self.track_link)
        track_row.addWidget(self.track_actions)
        overview.addWidget(card)
        overview.addSpacing(8)
        connections_header = QWidget()
        connections_labels = QVBoxLayout(connections_header)
        connections_labels.setContentsMargins(0, 5, 0, 7)
        connections_labels.setSpacing(5)
        connections_labels.addWidget(self._translated_label("connections.title", "brand"))
        connections_labels.addWidget(self._translated_label("connections.description", "muted"))
        overview.addWidget(connections_header)
        discord_card = QFrame(objectName="card")
        discord_row = QHBoxLayout(discord_card)
        discord_row.setContentsMargins(18, 12, 22, 12)
        discord_row.setSpacing(12)
        self.discord_avatar = CoverArt(size=52, circular=True, hide_until_loaded=True)
        discord_icon = self._service_icon("discord.svg", 30)
        discord_icon.setToolTip("Discord")
        discord_row.addWidget(discord_icon)
        discord_row.addWidget(self.discord_avatar)
        discord_text = QVBoxLayout()
        discord_text.setSpacing(4)
        discord_text.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        discord_text.setContentsMargins(0, 0, 0, 0)
        self.discord_name = self._label("Discord", "connectionName")
        self.discord_username = self._translated_label("discord.offline_hint", "profileUsername")
        discord_text.addWidget(self.discord_name)
        discord_text.addWidget(self.discord_username)
        discord_row.addLayout(discord_text, 1)
        self.discord_state = self._label("", "status")
        discord_row.addWidget(self.discord_state)
        overview.addWidget(discord_card)
        self._discord_profile = {}
        self.set_discord_profile({"connected": False})

        account_card = QFrame(objectName="card")
        account_row = QHBoxLayout(account_card)
        account_row.setContentsMargins(18, 12, 22, 12)
        account_row.setSpacing(12)
        account_row.addWidget(self._service_icon("music-mark.svg", 38))
        self.yandex_avatar = CoverArt(size=52, circular=True, hide_until_loaded=True)
        account_row.addWidget(self.yandex_avatar)
        account_text = QVBoxLayout()
        account_text.setSpacing(4)
        account_text.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.account_label = self._translated_label("account.signed_out", "connectionName")
        account_text.addWidget(self.account_label)
        account_text.addWidget(self._translated_label("connections.yandex", "muted"))
        account_row.addLayout(account_text, 1)
        self.account_manage = bind_text(TrailingButton("right"), "account.manage")
        account_menu = RoundedMenu(self.account_manage)
        self.login = bind_text(account_menu.addAction(""), "account.sign_in")
        self.logout = bind_text(account_menu.addAction(""), "account.sign_out")
        self.login.triggered.connect(self.login_requested)
        self.logout.triggered.connect(self.logout_requested)
        self.logout.setVisible(False)
        account_menu.addSeparator()
        self.account_info = bind_text(account_menu.addAction(""), "account.why_tooltip")
        self.account_info.triggered.connect(self._show_account_info)
        self.account_manage.setMenu(account_menu)
        account_row.addWidget(self.account_manage)
        overview.addWidget(account_card)

        search_card = QFrame(objectName="card")
        search_layout = QVBoxLayout(search_card)
        search_layout.setContentsMargins(18, 12, 18, 12)
        summary_row = QHBoxLayout()
        summary_row.setSpacing(16)
        self.summary_cover = CoverArt(size=52)
        summary_row.addWidget(self.summary_cover)
        summary_text = QVBoxLayout()
        summary_text.setSpacing(4)
        summary_text.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.cover_summary = self._translated_label("cover.waiting", "resultTitle")
        summary_text.addWidget(self.cover_summary)
        summary_text.addWidget(self._translated_label("cover.description", "muted"))
        summary_row.addLayout(summary_text, 1)
        self.details_button = bind_text(TrailingButton("down"), "common.details")
        self.details_button.setCheckable(True)
        summary_row.addWidget(self.details_button)
        search_layout.addLayout(summary_row)
        self.search_details = QWidget()
        details_layout = QVBoxLayout(self.search_details)
        details_layout.setContentsMargins(0, 12, 0, 0)
        self.search_heading = self._translated_label("search.heading", "rowTitle")
        self.search_description = self._translated_label("search.description", "muted")
        self.search_description.hide()
        details_layout.addWidget(self.search_heading)
        details_layout.addWidget(self.search_description)
        details_layout.addWidget(self.track_source)
        details_layout.addSpacing(6)
        search_layout.addWidget(self.search_details)
        self.search_details.hide()
        self.details_button.toggled.connect(self._toggle_details)
        overview.addWidget(search_card)
        self.ynison_idle_notice = self._translated_label("capture.ynison_outage", "errorNotice")
        self.ynison_idle_notice.hide()
        overview.insertWidget(3, self.ynison_idle_notice)
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
            details_layout.addWidget(container)
            self.source_rows[source] = container
        self.upload_details = QWidget()
        uploads_layout = QVBoxLayout(self.upload_details)
        uploads_layout.setContentsMargins(0, 10, 0, 0)
        self.upload_heading = self._translated_label("uploads.heading", "rowTitle")
        uploads_layout.addWidget(self.upload_heading)
        uploads_layout.addSpacing(6)
        self.upload_labels = {}
        for name, _ in UNUSED_UPLOADS:
            row = QHBoxLayout()
            row.addWidget(self._label(name), 1)
            label = self._label("", "muted")
            row.addWidget(label)
            uploads_layout.addLayout(row)
            self.upload_labels[name] = label
        details_layout.addWidget(self.upload_details)
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
        pause_info = ActionButton(objectName="info")
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
        windows_layout.addWidget(self.show_unknown_cover)
        windows_layout.addWidget(self.cover_warning)
        self.warning.setVisible(settings.show_unknown_media)
        self._update_cover_controls()
        capture.addWidget(self.windows_controls)
        self.capture_mode.currentIndexChanged.connect(self._update_capture_mode)
        self._update_capture_mode()
        capture.addStretch()

        application = self._page("nav.application", "app.description")
        self._row(application, "app.language", "app.language_hint", self.app_language)
        self._row(application, "app.autostart", "app.autostart_hint", self.autostart)
        self.update_button = bind_text(ActionButton(), "updates.check")
        self.update_button.setObjectName("primary")
        self.update_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.update_button.setMinimumWidth(200)
        self.update_button.clicked.connect(self.updates_requested)
        self._row(
            application,
            "updates.title",
            "updates.description",
            self.update_button,
        )
        logs = bind_text(IconButton(), "logs.open")
        logs.setIcon(QIcon(str(resource_path("document.svg"))))
        logs.setIconSize(QSize(24, 24))
        logs.setMinimumWidth(190)
        logs.clicked.connect(self.logs_requested)
        self._row(
            application,
            "logs.title",
            "logs.description",
            logs,
        )
        application.addStretch()

        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        self.navigation.setFocus()
        self.set_status(self._status)
        for control in (
            self.activity_type,
            self.language,
            self.app_language,
            self.buttons,
            self.display,
            self.session,
            self.capture_mode,
        ):
            control.currentIndexChanged.connect(self._save)
        self.pause_timeout.valueChanged.connect(self._save)
        self.show_unknown.toggled.connect(self._save)
        self.show_unknown_cover.toggled.connect(self._save)
        self.never_hide.toggled.connect(self._save)
        self.fix_pause.toggled.connect(self._save)

    @staticmethod
    def _service_icon(filename, size):
        label = IconLabel(QIcon(str(resource_path(filename))), size, objectName="serviceIcon")
        label.setFixedSize(52, 52)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _toggle_details(self, expanded):
        page = self.pages.widget(0)
        page.setUpdatesEnabled(False)
        try:
            self.search_details.setVisible(expanded)
            # Resolve content height and the scrollbar before painting the expansion.
            card = self.search_details.parentWidget()
            card.layout().invalidate()
            card.layout().activate()
            card.updateGeometry()
            page.widget().layout().activate()
            page.widget().resize(page.viewport().size().expandedTo(page.widget().minimumSizeHint()))
            QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
            page.widget().layout().activate()
            if expanded:
                page.ensureWidgetVisible(self.search_details, 0, 12)
        finally:
            page.setUpdatesEnabled(True)

    def _update_cover_controls(self):
        page = self.pages.widget(2) if hasattr(self, "pages") and self.pages.count() > 2 else None
        if page:
            page.setUpdatesEnabled(False)
        enabled = self.show_unknown.isChecked()
        self.show_unknown_cover.setVisible(enabled)
        self.cover_warning.setVisible(enabled and self.show_unknown_cover.isChecked())
        if page:
            # The toggled signal also saves/retranslates the form. Keep painting
            # suspended until those synchronous changes and the layout settle.
            QTimer.singleShot(0, lambda: self._settle_cover_controls(page))

    def _settle_cover_controls(self, page):
        try:
            content = page.widget()
            content.layout().invalidate()
            content.layout().activate()
            content.resize(page.viewport().size().expandedTo(content.minimumSizeHint()))
            QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
            content.layout().activate()
            if not self.cover_warning.isHidden():
                bottom = self.cover_warning.mapTo(
                    content, self.cover_warning.rect().bottomLeft()
                ).y()
                bar = page.verticalScrollBar()
                bar.setValue(max(bar.value(), bottom + 12 - page.viewport().height()))
        finally:
            page.setUpdatesEnabled(True)

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
        MessageDialog(
            self, tr("capture.pause_title"), subtitle=tr("capture.pause_subtitle"),
            sections=(
                (tr("capture.pause_reason_title"), tr("capture.pause_reason")),
                (tr("capture.pause_action_title"), tr("capture.pause_action")),
            ),
        ).exec()

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
        layout.setContentsMargins(0, 0, 14, 0)
        layout.setSpacing(10)
        header = QWidget()
        header.setFixedHeight(72)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 9)
        header_layout.setSpacing(0)
        title_label = self._translated_label(title, "heading")
        title_label.setFixedHeight(39)
        header_layout.addWidget(title_label)
        header_layout.addWidget(self._translated_label(subtitle, "subtitle"))
        layout.addWidget(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if title != "nav.overview":
            layout.setContentsMargins(0, 0, 14, 18)
            scroll.setViewportMargins(0, 0, 0, 16)
        scroll.setWidget(content)
        self.pages.addWidget(scroll)
        return layout

    def _row(self, layout, title, description, control, *, divider=True):
        card = QFrame(objectName="card")
        row = QHBoxLayout(card)
        card.setMinimumHeight(90 if control is self.autostart else 82)
        row.setContentsMargins(20, 16, 20, 16)
        labels = QVBoxLayout()
        labels.setSpacing(7)
        labels.addWidget(self._translated_label(title, "rowTitle"))
        labels.addWidget(self._translated_label(description, "muted"))
        row.addLayout(labels, 1)
        row.addSpacing(15)
        row.addWidget(control)
        layout.addWidget(card)

    @staticmethod
    def _divider(layout):
        line = QFrame(objectName="divider")
        line.setFixedHeight(1)
        layout.addWidget(line)

    @staticmethod
    def _combo(items, selected):
        combo = Dropdown()
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

    def set_account(self, account: str | Message | None, avatar_url: str = ""):
        self._account = account
        self._account_avatar = avatar_url if account is not None else ""
        self.yandex_avatar.set_url(self._account_avatar)
        self.account_label.setText(
            render(account) if account is not None else tr("account.signed_out")
        )
        logged_in = account is not None
        self._logged_in = logged_in
        self._update_capture_notice()
        self.logout.setVisible(logged_in)
        self.login.setVisible(not logged_in)
        self.login.setText(tr("account.sign_in"))

    def set_status(self, status: str | Message):
        self._status = status
        self.status_label.setText("●  " + render(status))
        active = isinstance(status, Message) and status.key in (
            "status.active",
            "status.unverified",
        )
        color = "#9dd9ad" if active else "#a8a8af"
        self.status_label.setStyleSheet(f"color: {color};")

    def set_auth_busy(self, busy: bool):
        self.login.setEnabled(not busy)
        self.logout.setEnabled(not busy)

    def set_autostart(self, enabled: bool):
        self.autostart.blockSignals(True)
        self.autostart.setChecked(enabled)
        self.autostart.blockSignals(False)

    def set_track(self, value):
        self._track = value
        media, track, state = value[:3]
        self.cover.set_playback(
            "playing" if media and media.status == PlaybackStatus.PLAYING
            else "paused" if media and media.status == PlaybackStatus.PAUSED
            else None
        )
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
        self.search_description.setVisible(ynison)
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
        fallback = capture_info.get("cover", CoverResult())
        fallback_enabled = (
            not ynison and self.config.settings.show_unknown_media
            and self.config.settings.show_unknown_cover
        )
        if not fallback_enabled:
            fallback = CoverResult(state="disabled")
        elif fallback.state == "disabled":
            fallback = CoverResult()
        self.upload_details.setVisible(fallback_enabled)
        self.upload_heading.setToolTip(tr("uploads." + fallback.state))
        upload_states = dict(fallback.sources)
        for name, label in self.upload_labels.items():
            upload_state = upload_states.get(name, "unused")
            label.setText(tr("uploads." + upload_state))
            label.setStyleSheet("color: " + {
                "uploaded": "#9dd9ad", "uploading": "#f5ca66",
                "unavailable": "#efd497", "rate_limited": "#efd497",
            }.get(upload_state, "#9898a3") + ";")
        cover_url = track.cover if track else fallback.url
        self.cover.set_url(cover_url)
        self.summary_cover.set_url(cover_url)
        payload = {}
        if media:
            displayed = track or Track(
                media.title, media.artist, media.album, media.duration, cover=cover_url
            )
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
        self.track_title.setText(
            track.full_title if track else media.title if media else tr("playback.empty")
        )
        self.track_artist.setText(
            track.artist if track else media.artist if media else tr("playback.empty_hint")
        )
        album = payload.get("large_text", "")
        self.track_album.setText(album)
        self.track_title.setToolTip(album)
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
        if track and len(value) > 4 and value[4]:
            source += ("\n" if source else "") + render(value[4])
        self.track_source.setText(source)
        self.track_source.setVisible(bool(source))
        self.track_link.setEnabled(
            bool(track and track.url and QUrl(track.url).scheme() == "https")
        )
        unverified_blocked = (
            not ynison and media is not None and track is None
            and state in ("not_found", "unavailable")
            and not self.config.settings.show_unknown_media
        )
        self.cover_summary.setText(
            tr(
                "cover.found",
                source=tr("music.name")
                if track.source in ("Yandex", "Yandex Music", "")
                else track.source,
            )
            if track and track.cover
            else tr("cover.temporary", source=fallback.host) if fallback.url and not track
            else tr("cover.not_found") if unverified_blocked
            else tr("cover.no_artwork") if track
            else tr("cover.missing") if state in ("not_found", "unavailable")
            else tr("cover.waiting")
        )
        self.cover_summary.setStyleSheet(
            "color: #ffb4ba;"
            if unverified_blocked
            else "color: #f5f5f5;"
        )

    def _open_track(self):
        track = self._track[1]
        if track and track.url and QUrl(track.url).scheme() == "https":
            QDesktopServices.openUrl(QUrl(track.url))

    def set_discord_profile(self, profile):
        import re

        self._discord_profile = profile
        connected = profile.get("connected", False)
        username = profile.get("username") or ""
        self.discord_name.setText(profile.get("global_name") or username or "Discord")
        self.discord_username.setText(
            f"@{username}"
            if username
            else tr("discord.profile_missing" if connected else "discord.offline_hint")
        )
        self.discord_state.setText(
            "●  " + tr("discord.connected" if connected else "discord.disconnected")
        )
        self.discord_state.setStyleSheet("color: #9dd9ad;" if connected else "color: #a8a8af;")
        user_id, avatar = str(profile.get("id") or ""), str(profile.get("avatar") or "")
        url = None
        if connected and user_id.isdigit() and re.fullmatch(r"(?:a_)?[a-fA-F0-9]+", avatar):
            url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png?size=128"
        self.discord_avatar.set_url(url)

    @staticmethod
    def _timecode(seconds):
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"

    def _show_account_info(self):
        MessageDialog(self, tr("account.why_title"), tr("account.help"), rich_text=True).exec()

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
            last_pause_timeout=self.pause_timeout.value(),
            show_unknown_media=self.show_unknown.isChecked(),
            show_unknown_cover=self.show_unknown_cover.isChecked(),
        )

    def _save(self) -> None:
        settings = self._form_settings()
        previous = self.config.settings
        if settings == previous:
            return
        try:
            self.config.save(settings)
        except (OSError, ValueError) as error:
            show_message(self, tr("settings.save_failed"), str(error))
            return
        if settings.app_language != previous.app_language:
            set_language(settings.app_language)
            retranslate(self)
            self.update_sessions(self._sessions)
        self.set_account(self._account, self._account_avatar)
        self.set_track(self._track)
        self.set_status(self._status)
        self.set_discord_profile(self._discord_profile)
        self.saved.emit()

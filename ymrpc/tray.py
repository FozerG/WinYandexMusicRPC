import logging
import subprocess
import webbrowser

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .config import ConfigStore, data_directory
from .constants import APP_NAME, REPO_URL, resource_path
from .settings import SettingsDialog
from .windows import autostart_enabled, set_autostart
from .worker import PresenceWorker

logger = logging.getLogger(__name__)


class TrayController:
    def __init__(self, app: QApplication, config: ConfigStore):
        self.app = app
        self.config = config
        self.sessions: tuple[str, ...] = ()
        self.settings_dialog = None
        self.auth_dialog = None
        self._quitting = False
        self._track = (None, None, "idle")
        self._auth_busy = False
        self.worker = PresenceWorker(config)
        self.tray = QSystemTrayIcon(QIcon(str(resource_path("YMRPC_ico.ico"))), app)
        self.tray.setToolTip(APP_NAME)
        self.menu = QMenu()
        self._status_text = "Ожидание воспроизведения"
        self._account_text = "Без авторизации"
        self._autostart_enabled = autostart_enabled()
        self.menu.addAction("Открыть WinYandexMusicRPC", self.open_settings)
        self.menu.addSeparator()
        self.menu.addAction("Открыть журнал", self._open_logs)
        self.menu.addAction("GitHub", lambda: webbrowser.open(REPO_URL))
        self.check_updates = self.menu.addAction("Проверить обновления", self._check_updates)
        self.menu.addAction("Выход", self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        self.worker.sessions_changed.connect(self._sessions_changed)
        self.worker.status_changed.connect(self._status_changed)
        self.worker.account_changed.connect(self._account_changed)
        self.worker.track_changed.connect(self._track_changed)
        self.worker.authentication_finished.connect(self._authentication_finished)
        self.worker.update_checked.connect(self._update_checked)
        self.worker.finished.connect(self._worker_finished)
        self.tray.show()
        self.worker.start()
        QTimer.singleShot(1500, self._startup_updates)

    def _activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_settings()

    def open_settings(self) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self.config, self.sessions)
            self.settings_dialog.saved.connect(self.worker.refresh)
            self.settings_dialog.finished.connect(self._settings_closed)
            self.settings_dialog.login_requested.connect(self.open_auth)
            self.settings_dialog.logout_requested.connect(self._logout)
            self.settings_dialog.autostart_changed.connect(self._set_autostart)
            self.settings_dialog.updates_requested.connect(self._check_updates)
            self.settings_dialog.logs_requested.connect(self._open_logs)
            self.settings_dialog.set_account(self._account_text)
            self.settings_dialog.set_auth_busy(self._auth_busy)
            self.settings_dialog.set_autostart(self._autostart_enabled)
            self.settings_dialog.status_label.setText(self._status_text)
            self.settings_dialog.set_track(self._track)
            self.settings_dialog.update_button.setEnabled(self.check_updates.isEnabled())
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _settings_closed(self) -> None:
        self.settings_dialog.deleteLater()
        self.settings_dialog = None

    def open_auth(self) -> None:
        if self.auth_dialog is not None:
            return
        from .authorization import AuthorizationProcess

        self.auth_dialog = AuthorizationProcess()
        self.auth_dialog.token_received.connect(self._authenticate)
        self.auth_dialog.failed.connect(lambda text: self._authentication_finished(False, text))
        self.auth_dialog.finished.connect(self._auth_closed)
        self.auth_dialog.start()

    def _auth_closed(self) -> None:
        dialog, self.auth_dialog = self.auth_dialog, None
        dialog.deleteLater()
        if self._quitting and not self.worker.isRunning():
            self._worker_finished()

    def _authenticate(self, token: str) -> None:
        self._set_auth_busy(True)
        self.worker.authenticate(token)

    def _logout(self) -> None:
        self._set_auth_busy(True)
        self.worker.logout()

    def _check_updates(self) -> None:
        self.check_updates.setEnabled(False)
        if self.settings_dialog:
            self.settings_dialog.update_button.setEnabled(False)
        self.worker.check_updates()

    def _update_checked(self, message: str) -> None:
        self.check_updates.setEnabled(True)
        if self.settings_dialog:
            self.settings_dialog.update_button.setEnabled(True)
        self.tray.showMessage(APP_NAME, message)

    def _authentication_finished(self, success: bool, message: str) -> None:
        self._set_auth_busy(False)
        icon = (
            QSystemTrayIcon.MessageIcon.Information
            if success
            else QSystemTrayIcon.MessageIcon.Warning
        )
        self.tray.showMessage(APP_NAME, message, icon)

    def _sessions_changed(self, sessions: tuple[str, ...]) -> None:
        self.sessions = sessions
        if self.settings_dialog is not None:
            self.settings_dialog.update_sessions(sessions)

    def _status_changed(self, text: str) -> None:
        self._status_text = text
        if self.settings_dialog:
            self.settings_dialog.status_label.setText(text)
        self.tray.setToolTip(f"{APP_NAME}\n{text}"[:127])

    def _set_autostart(self, enabled: bool) -> None:
        try:
            set_autostart(enabled)
            self._autostart_enabled = enabled
            logger.info("Windows autostart: %s", enabled)
        except OSError as error:
            self._autostart_enabled = autostart_enabled()
            QMessageBox.warning(None, "Не удалось изменить автозапуск", str(error))
        if self.settings_dialog:
            self.settings_dialog.set_autostart(self._autostart_enabled)

    def _open_logs(self):
        try:
            subprocess.Popen(["explorer.exe", "/select,", str(data_directory() / "rpc.log")])
        except OSError as error:
            QMessageBox.warning(self.settings_dialog, "Журнал недоступен", str(error))

    def _startup_updates(self):
        if not self._quitting:
            self.worker.check_updates(automatic=True)

    def _set_auth_busy(self, busy):
        self._auth_busy = busy
        if self.settings_dialog:
            self.settings_dialog.set_auth_busy(busy)

    def _account_changed(self, text):
        self._account_text = text
        if self.settings_dialog:
            self.settings_dialog.set_account(text)

    def _track_changed(self, value):
        self._track = value
        if self.settings_dialog:
            self.settings_dialog.set_track(value)

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self.menu.setEnabled(False)
        self.tray.setToolTip("Завершение работы…")
        for dialog in (self.auth_dialog, self.settings_dialog):
            if dialog is not None:
                dialog.close()
        self.worker.stop()
        if not self.worker.isRunning():
            self._worker_finished()

    def _worker_finished(self) -> None:
        if self._quitting:
            if self.auth_dialog is not None:
                return
            self.tray.hide()
            QTimer.singleShot(0, self.app.quit)
        else:
            logger.error("Presence worker stopped unexpectedly")
            self.tray.showMessage(
                APP_NAME, "Служба RPC остановлена. Перезапустите приложение и проверьте журнал."
            )

    def shutdown(self) -> None:
        self.worker.stop()
        self.worker.wait()
        self.tray.hide()

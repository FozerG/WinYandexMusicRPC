import argparse
import logging
import signal
import sys

from . import __version__


def _run() -> int:
    parser = argparse.ArgumentParser(description="Yandex Music Discord Rich Presence for Windows")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--run-through-startup", action="store_true")
    parser.add_argument("--show-settings", action="store_true")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--authorize-channel", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows 10 or newer is required")

    from PyQt6.QtCore import QCoreApplication, Qt, QTimer
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from .config import ConfigStore
    from .constants import resource_path
    from .fonts import application_font
    from .logging_setup import configure_logging
    from .tray import TrayController
    from .windows import SingleInstance

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(application_font())
    app.setApplicationName("WinYandexMusicRPC")
    app.setWindowIcon(QIcon(str(resource_path("YMRPC_ico.ico"))))
    app.setQuitOnLastWindowClosed(False)
    if args.authorize_channel:
        from .authorization import run_authorization

        return run_authorization(app, args.authorize_channel)
    if args.smoke_test:
        import json
        import os

        from PyQt6.QtCore import qVersion
        from PyQt6.QtGui import QFontInfo
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        from .settings import SettingsDialog

        browser = QWebEngineView()
        dialog = SettingsDialog(ConfigStore(), ())
        dialog.show()
        app.processEvents()
        screenshot = os.environ.get("YMRPC_SMOKE_SCREENSHOT")
        if screenshot:
            dialog.grab().save(screenshot)
        report = json.dumps(
            {
                "version": __version__,
                "qt": qVersion(),
                "font": QFontInfo(dialog.font()).family(),
                "size": [dialog.width(), dialog.height()],
                "gui": "ready",
                "icon": not dialog.windowIcon().isNull(),
            }
        )
        if sys.stdout is not None:
            print(report, flush=True)
        report_path = os.environ.get("YMRPC_SMOKE_REPORT")
        if report_path:
            from pathlib import Path

            Path(report_path).write_text(report, encoding="utf-8")
        QTimer.singleShot(100, app.quit)
        code = app.exec()
        browser.close()
        dialog.close()
        return code
    instance = SingleInstance()
    controller = None
    try:
        if instance.already_running:
            if args.run_through_startup:
                return 0
            QMessageBox.information(
                None,
                "WinYandexMusicRPC",
                "Приложение уже запущено. Откройте настройки через значок в трее.",
            )
            return 0
        configure_logging()
        config = ConfigStore()
        logging.getLogger(__name__).info("Settings: %s", config.settings)
        controller = TrayController(app, config)
        app.aboutToQuit.connect(controller.shutdown)
        signal.signal(signal.SIGINT, lambda *_: controller.quit())
        timer = QTimer()
        timer.timeout.connect(lambda: None)
        timer.start(250)
        if args.show_settings or not args.run_through_startup:
            controller.open_settings()
        logging.getLogger(__name__).info("Started WinYandexMusicRPC %s", __version__)
        return app.exec()
    except Exception:
        logging.getLogger(__name__).exception("Application startup failed")
        QMessageBox.critical(
            None,
            "WinYandexMusicRPC",
            "Не удалось запустить приложение. Подробности в %LOCALAPPDATA%/WinYandexMusicRPC/rpc.log.",
        )
        return 1
    finally:
        if controller is not None:
            controller.shutdown()
        instance.close()


def main() -> int:
    try:
        return _run()
    except Exception as error:
        if "--authorize-channel" in sys.argv:
            return 1
        from .logging_setup import configure_logging

        if not logging.getLogger().handlers:
            configure_logging()
        logging.getLogger(__name__).exception("Application bootstrap failed")
        if "--smoke-test" not in sys.argv:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                f"Не удалось запустить WinYandexMusicRPC.\n\n{error}\n\n"
                "Подробности: %LOCALAPPDATA%/WinYandexMusicRPC/rpc.log",
                "Ошибка запуска",
                0x10,
            )
        return 1

import json
import logging
import sys
import uuid
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal
from PyQt6.QtNetwork import QLocalServer

logger = logging.getLogger(__name__)


class AuthorizationProcess(QObject):
    token_received = pyqtSignal(str)
    finished = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._received = False
        self._closing = False
        self._buffer = bytearray()
        self._socket = None
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._connected)
        self.process = QProcess(self)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)

    def start(self):
        channel = f"WinYandexMusicRPC-auth-{uuid.uuid4().hex}"
        if not self.server.listen(channel):
            self.failed.emit("Не удалось открыть локальный канал авторизации.")
            self.finished.emit()
            return
        arguments = ["--authorize-channel", channel]
        executable = sys.executable
        if not getattr(sys, "frozen", False):
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            executable = str(pythonw if pythonw.exists() else Path(sys.executable))
            arguments.insert(0, str(Path(__file__).resolve().parent.parent / "main.py"))
        self.process.start(executable, arguments)
        logger.info("Authorization browser process starting")

    def _connected(self):
        socket = self.server.nextPendingConnection()
        if self._socket is not None:
            socket.disconnectFromServer()
            socket.deleteLater()
            return
        self._socket = socket
        socket.readyRead.connect(self._read)
        self._read()

    def _read(self):
        self._buffer.extend(bytes(self._socket.readAll()))
        if len(self._buffer) > 8192:
            self.close()
            return
        if b"\n" not in self._buffer or self._received:
            return
        try:
            token = json.loads(bytes(self._buffer).split(b"\n", 1)[0]).get("token")
            if not isinstance(token, str) or not 10 < len(token) <= 4096:
                raise ValueError("Invalid token payload")
        except (ValueError, AttributeError):
            self.close()
            return
        self._buffer.clear()
        self._received = True
        logger.info("OAuth token delivered to main process")
        self._socket.write(b"ok\n")
        self._socket.flush()
        self.token_received.emit(token)

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.failed.emit("Не удалось запустить окно входа в Яндекс.")
            self.server.close()
            self.finished.emit()

    def _finished(self, code, status):
        logger.info(
            "Authorization browser exited: code=%s; token_received=%s", code, self._received
        )
        self.server.close()
        if (
            not self._closing
            and not self._received
            and (code != 0 or status == QProcess.ExitStatus.CrashExit)
        ):
            self.failed.emit(
                "Окно Яндекса аварийно закрылось. Основная программа продолжает работать."
            )
        self.finished.emit()

    def close(self):
        self._closing = True
        self.process.terminate()
        QTimer.singleShot(2000, self._kill_if_running)

    def _kill_if_running(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()


def run_authorization(app, channel):
    from PyQt6.QtNetwork import QLocalSocket

    from .auth import AuthorizationDialog

    socket = QLocalSocket(app)
    socket.connectToServer(channel)
    if not socket.waitForConnected(3000):
        return 1
    dialog = AuthorizationDialog()
    pending = [False]
    ack = bytearray()

    def send_token(token):
        pending[0] = True
        socket.write(json.dumps({"token": token}).encode("utf-8") + b"\n")
        socket.flush()

    def acknowledged():
        ack.extend(bytes(socket.readAll()))
        if pending[0] and bytes(ack).strip() == b"ok":
            pending[0] = False
            dialog.dispose()

    def closed():
        if not pending[0]:
            dialog.dispose()
        else:
            QTimer.singleShot(5000, dialog.dispose)

    socket.readyRead.connect(acknowledged)
    socket.disconnected.connect(dialog.close)
    dialog.token_received.connect(send_token)
    dialog.finished.connect(closed)
    dialog.destroyed.connect(app.quit)
    dialog.show()
    return app.exec()

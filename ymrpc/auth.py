import html
import logging
import re
from urllib.parse import parse_qs, urlparse

from PyQt6.QtCore import QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QVBoxLayout

from .constants import OAUTH_URL, resource_path

logger = logging.getLogger(__name__)
CALLBACK_HOSTS = {"oauth.yandex.ru", "music.yandex.ru"}
TOKEN = re.compile(r"access_token=([A-Za-z0-9._~+/-]{11,4096})(?:[&\s\"'<>]|$)")


def token_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in CALLBACK_HOSTS or parsed.username:
        return None
    token = parse_qs(parsed.fragment).get("access_token", [None])[0]
    return token if token and re.fullmatch(r"[A-Za-z0-9._~+/-]{11,4096}", token) else None


def token_from_response(url: str, body: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "oauth.yandex.ru":
        return None
    match = TOKEN.search(html.unescape(body))
    return match.group(1) if match else None


class OAuthPage(QWebEnginePage):
    token_found = pyqtSignal(str)

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        token = token_from_url(url.toString()) if is_main_frame else None
        if token:
            self.token_found.emit(token)
            return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        # Chromium diagnostics can include OAuth redirects containing credentials.
        pass


class AuthorizationDialog(QDialog):
    token_received = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Вход в Яндекс Музыку")
        self.setWindowIcon(QIcon(str(resource_path("YMRPC_ico.ico"))))
        self.resize(700, 800)
        self._completed = False
        self._pending_token = None
        self._disposing = False
        self._reply = None
        self._attempts = 0
        self.browser = QWebEngineView(self)
        self.profile = QWebEngineProfile(self)
        self.page = OAuthPage(self.profile, self.browser)
        self.browser.setPage(self.page)
        self.network = QNetworkAccessManager(self)
        cookies = self.profile.cookieStore()
        cookies.cookieAdded.connect(self.network.cookieJar().insertCookie)
        cookies.cookieRemoved.connect(self.network.cookieJar().deleteCookie)
        cookies.loadAllCookies()
        self.page.token_found.connect(self._receive_token)
        self.browser.urlChanged.connect(self._url_changed)
        self.browser.loadFinished.connect(self._loaded)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.browser)
        self.finished.connect(self._stop)
        self.browser.setUrl(QUrl(OAUTH_URL))

    def _url_changed(self, url: QUrl) -> None:
        token = token_from_url(url.toString())
        if token:
            self._receive_token(token)
        elif url.scheme() == "https" and url.host() == "music.yandex.ru":
            QTimer.singleShot(0, self._fetch_token)

    def _loaded(self, success):
        url = self.browser.url()
        if success and url.scheme() == "https" and url.host() in CALLBACK_HOSTS:
            self._fetch_token()

    def _fetch_token(self):
        if self._completed or self._reply is not None or self._attempts >= 4:
            return
        self._attempts += 1
        request = QNetworkRequest(QUrl(OAUTH_URL))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
        )
        request.setTransferTimeout(10000)
        request.setRawHeader(b"User-Agent", self.profile.httpUserAgent().encode())
        reply = self.network.get(request)
        self._reply = reply
        reply.downloadProgress.connect(
            lambda received, _: reply.abort() if received > 2_000_000 else None
        )
        reply.finished.connect(lambda: self._fetched(reply))

    def _fetched(self, reply):
        if self._reply is reply:
            self._reply = None
        try:
            if self._completed:
                return
            if reply.error() != QNetworkReply.NetworkError.NoError:
                logger.warning("OAuth completion request failed (%s)", reply.error().name)
                if self._attempts < 4:
                    QTimer.singleShot(1500, self._fetch_token)
                return
            redirect = reply.attribute(QNetworkRequest.Attribute.RedirectionTargetAttribute)
            target = reply.url().resolved(redirect).toString() if redirect else ""
            token = token_from_url(target) or token_from_response(
                reply.url().toString(), bytes(reply.readAll()).decode("utf-8", errors="replace")
            )
            if token:
                self._receive_token(token)
            else:
                logger.info("OAuth completion is waiting for account authorization")
                if self.browser.url().host() == "music.yandex.ru" and self._attempts < 4:
                    QTimer.singleShot(500, self._fetch_token)
        finally:
            reply.deleteLater()

    def _receive_token(self, token):
        if self._completed:
            return
        self._completed = True
        self._pending_token = token
        # Navigation callbacks must return before stopping or destroying WebEngine objects.
        QTimer.singleShot(0, self._finish_auth)

    def _finish_auth(self):
        token, self._pending_token = self._pending_token, None
        if token is None:
            return
        logger.info("OAuth token received; handing off to account worker")
        self.token_received.emit(token)
        self.accept()

    def _stop(self):
        self._completed = True
        self._pending_token = None
        self.browser.stop()
        if self._reply is not None:
            self._reply.abort()

    def dispose(self):
        if self._disposing:
            return
        self._disposing = True
        self._stop()
        logger.info("OAuth cleanup: deleting browser page")
        self.page.destroyed.connect(self._page_deleted)
        self.page.deleteLater()

    def _page_deleted(self):
        self.page = None
        logger.info("OAuth cleanup: page deleted; deleting profile")
        self.profile.destroyed.connect(self._profile_deleted)
        self.profile.deleteLater()

    def _profile_deleted(self):
        self.profile = None
        logger.info("OAuth cleanup: profile deleted")
        self.deleteLater()

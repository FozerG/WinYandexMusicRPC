from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QIcon
import sys
import re

URL_WITH_ACCESS_TOKEN_REGEX = r'https:\/\/music\.yandex\.(?:ru|com|by|kz|ua)\/#access_token=([^&]*)'


class CustomWebEnginePage(QWebEnginePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.profile().setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36"
        )
        
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        pass


class TokenWindow(QMainWindow):
    def __init__(self, url, icon_path):
        super().__init__()
        self.setWindowTitle("Authorization")
        self.setGeometry(100, 100, 700, 800)
        self.setWindowIcon(QIcon(icon_path))
        
        self.browser = QWebEngineView()
        self.browser.setPage(CustomWebEnginePage(self.browser))
        self.browser.page().profile().cookieStore().deleteAllCookies()
        self.browser.urlChanged.connect(self.on_url_changed)

        self.browser.setUrl(QUrl(url))
        
        central_widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.browser)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
        
        self.token = None

    def on_url_changed(self, url):
        url_str = url.toString()
        match = re.search(URL_WITH_ACCESS_TOKEN_REGEX, url_str)
        if match:
            self.token = match.group(1) 
            self.close()


def update_token(icon_path):
    app = QApplication(sys.argv)
    oauth_url = "https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d"  # Official link to OAuth Yandex.Music
    token_window = TokenWindow(oauth_url, icon_path)
    token_window.show()
    app.exec_()
    return token_window.token
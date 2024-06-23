from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QIcon
import sys

class CustomWebEnginePage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        pass
    
class TokenWindow(QMainWindow):
    def __init__(self, url, icon_path):
        super().__init__()
        self.setWindowTitle("Авторизация")
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
        if "#access_token" in url_str:
            self.token = url_str.split("=")[1].split("&")[0]
            self.close()

def update_token(icon_path):
    app = QApplication(sys.argv)
    oauth_url = "https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d" # Official link to OAuth Yandex.Music
    token_window = TokenWindow(oauth_url, icon_path)
    token_window.show()
    app.exec_()
    return token_window.token
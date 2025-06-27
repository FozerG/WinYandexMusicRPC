import sys
import re
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QIcon

ACCESS_TOKEN_REGEX = r'access_token=([^&]*)'

class CustomWebEnginePage(QWebEnginePage):
    token_found = pyqtSignal(str)

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        match = re.search(ACCESS_TOKEN_REGEX, message)
        if match:
            token = match.group(1)
            self.token_found.emit(token)


class TokenWindow(QMainWindow):
    def __init__(self, initial_url, icon_path=None):
        super().__init__()
        self.setWindowTitle("Authorization")
        self.setGeometry(100, 100, 700, 800)
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self.browser = QWebEngineView()
        self.page = CustomWebEnginePage(self.browser)
        self.browser.setPage(self.page)

        self.page.token_found.connect(self.on_token_found)
        self.browser.urlChanged.connect(self.on_url_changed)

        # Clear all cookies to ensure a fresh login session.
        self.browser.page().profile().cookieStore().deleteAllCookies()
        self.browser.setUrl(QUrl(initial_url))

        central_widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.browser)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.token = None

    def on_token_found(self, token):
        self.token = token
        QApplication.quit()

    def on_url_changed(self, url):
        url_str = url.toString()
        if "music.yandex.ru" in url_str:
            # If redirected to the main music site, go back to the auth page.
            self.browser.setUrl(QUrl("https://oauth.yandex.ru"))
        elif "oauth.yandex" in url_str:
            # When on the oauth page, execute the script to get the token.
            self.execute_fetch_script()

    def execute_fetch_script(self):
        """
        Executes a JavaScript snippet in the web page to perform a fetch
        request and log the access token to the console.
        """
        script = """
        fetch("https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d")
            .then((response) => response.text())
            .then((text) => {
                // This part of the script is now less critical because the token
                // is often found in the URL redirect itself, but it's kept as a fallback.
                const tokenMatch = text.match(/access_token=(.*?)&/);
                if (tokenMatch) {
                    // Log the token to the console, which our custom page will intercept.
                    console.log("access_token=" + tokenMatch[1]);
                }
            });
        """
        self.browser.page().runJavaScript(script)

def get_yandex_music_token(icon_path=None):
    app = QApplication(sys.argv)
    # The official Yandex.Music OAuth URL.
    initial_url = "https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d"
    token_window = TokenWindow(initial_url, icon_path)
    token_window.show()
    app.exec()
    return token_window.token

if __name__ == '__main__':
    # You might want to provide a path to an icon file.
    token = get_yandex_music_token()

    if token:
        print(f"Successfully retrieved token: {token}")
    else:
        print("Failed to retrieve token or window was closed.")
import sys
from pathlib import Path

APP_NAME = "WinYandexMusicRPC"
REPO_URL = "https://github.com/FozerG/WinYandexMusicRPC"
CLIENT_ID_EN = "1269807014393942046"
CLIENT_ID_RU_LISTENING = "1269826362399522849"
ASSETS_URL = f"https://raw.githubusercontent.com/FozerG/{APP_NAME}/main/assets"
OAUTH_URL = (
    "https://oauth.yandex.ru/authorize?response_type=token"
    "&client_id=23cabbbdc6cd418abb4b39c32c41195d"
)


def resource_path(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "assets" / name

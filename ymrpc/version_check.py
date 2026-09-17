import json
from urllib.request import Request, urlopen

from packaging.version import Version

from . import __version__
from .constants import APP_NAME, REPO_URL


def latest_release() -> str | None:
    request = Request(
        "https://api.github.com/repos/FozerG/WinYandexMusicRPC/releases/latest",
        headers={"User-Agent": APP_NAME, "Accept": "application/vnd.github+json"},
    )
    with urlopen(request, timeout=5) as response:
        release = json.load(response)
    tag = release["tag_name"]
    if Version(tag) > Version(__version__):
        return f"{REPO_URL}/releases/latest"
    return None

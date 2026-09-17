import gzip
import json
import logging
import time
from collections import deque
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .matching import choose, normalize
from .models import MediaSnapshot, Track

logger = logging.getLogger(__name__)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


class CatalogHttp:
    def __init__(self):
        self._apple_requests: deque[float] = deque()

    def get(self, url: str, params: dict) -> dict:
        if "itunes.apple.com" in url:
            now = time.monotonic()
            while self._apple_requests and self._apple_requests[0] <= now - 60:
                self._apple_requests.popleft()
            if len(self._apple_requests) >= 18:
                raise OSError("iTunes local request budget exhausted; retry later")
            self._apple_requests.append(now)
        request = Request(
            url + "?" + urlencode(params),
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip",
            },
        )
        with urlopen(request, timeout=4) as response:
            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                with gzip.GzipFile(fileobj=response) as stream:
                    body = stream.read(2_000_001)
            else:
                body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("Catalog response exceeds 2 MB")
        data = json.loads(body)
        if not isinstance(data, dict) or data.get("error"):
            raise ValueError("Catalog returned an error or invalid response")
        return data


class ITunesCatalog:
    name = "iTunes"

    def __init__(self, http=None):
        self.http = http or CatalogHttp()

    @staticmethod
    def _tracks(rows):
        return [
            Track(
                title=row.get("trackName", ""),
                artist=row.get("artistName", ""),
                album=row.get("collectionName", ""),
                duration=(row.get("trackTimeMillis") or 0) / 1000,
                cover=row.get("artworkUrl100"),
                url=row.get("trackViewUrl"),
                source="iTunes",
            )
            for row in rows
            if row.get("kind") == "song"
        ]

    def search(self, media: MediaSnapshot, cancelled=lambda: False) -> list[Track]:
        query = f"{media.artist} {media.title}"
        logger.info("iTunes search: query=%r country=US", query)
        rows = self.http.get(
            "https://itunes.apple.com/search",
            {
                "term": query,
                "media": "music",
                "entity": "song",
                "country": "us",
                "limit": 25,
            },
        ).get("results", [])
        tracks = self._tracks(rows)
        if choose(media, tracks) or cancelled():
            return tracks
        logger.info("iTunes fallback: artist=%r; discovering albums", media.artist)
        rows = self.http.get(
            "https://itunes.apple.com/search",
            {
                "term": media.artist,
                "media": "music",
                "entity": "song",
                "attribute": "artistTerm",
                "country": "us",
                "limit": 200,
            },
        ).get("results", [])
        tracks.extend(self._tracks(rows))
        if choose(media, tracks):
            return tracks
        rows.sort(
            key=lambda row: normalize(row.get("collectionName", "")) != normalize(media.album)
        )
        album_ids = dict.fromkeys(
            row["collectionId"]
            for row in rows
            if row.get("collectionId")
            and normalize(row.get("artistName", "")) == normalize(media.artist)
        )
        for album_id in list(album_ids)[:4]:
            if cancelled():
                break
            logger.info("iTunes album lookup: id=%s country=US", album_id)
            rows = self.http.get(
                "https://itunes.apple.com/lookup",
                {
                    "id": album_id,
                    "entity": "song",
                    "country": "us",
                    "limit": 200,
                },
            ).get("results", [])
            tracks.extend(self._tracks(rows))
            if choose(media, tracks):
                break
        return tracks


class DeezerCatalog:
    name = "Deezer"

    def __init__(self, http=None):
        self.http = http or CatalogHttp()

    def search(self, media: MediaSnapshot, cancelled=lambda: False) -> list[Track]:
        query = f"{media.artist} {media.title}"
        logger.info("Deezer search: query=%r", query)
        rows = self.http.get("https://api.deezer.com/search", {"q": query, "limit": 25}).get(
            "data", []
        )
        return [
            Track(
                title=row.get("title", ""),
                artist=(row.get("artist") or {}).get("name", ""),
                album=(row.get("album") or {}).get("title", ""),
                duration=row.get("duration") or 0,
                cover=(row.get("album") or {}).get("cover_xl"),
                url=row.get("link"),
                source="Deezer",
            )
            for row in rows
        ]

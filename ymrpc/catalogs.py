import gzip
import json
import logging
import time
from collections import deque
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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
        return self._tracks(rows)


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


class SpotifyCatalog:
    name = "Spotify"

    def search(self, media: MediaSnapshot, cancelled=lambda: False) -> list[Track]:
        if cancelled():
            return []
        # Import and open the client only when the preceding catalogs did not match.
        from spotify_scraper import RetryPolicy, SpotifyClient

        query = f"{media.artist} {media.title}"
        logger.info("Spotify search: query=%r", query)
        # TrackResolver owns caching and backoff; avoid nested retries and close all sockets.
        with SpotifyClient(timeout=4, retry=RetryPolicy(max_attempts=1)) as client:
            result = client.search(query, types=("track",), limit=25)
        if cancelled():
            return []
        tracks = []
        for row in result.tracks:
            if not row.id or not row.name or not row.artists:
                continue
            cover = max(row.images, key=lambda image: image.width or 0, default=None)
            tracks.append(
                Track(
                    title=row.name,
                    artist=", ".join(artist.name for artist in row.artists),
                    album=row.album.name if row.album else "",
                    duration=row.duration_ms / 1000,
                    cover=cover.url if cover else None,
                    url=row.url,
                    app_url=row.uri,
                    source=self.name,
                )
            )
        return tracks

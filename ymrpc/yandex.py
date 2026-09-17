import logging

from yandex_music import Client

from .matching import choose, normalize
from .models import MediaSnapshot, Track

logger = logging.getLogger(__name__)


def track_metadata(track) -> Track:
    albums = track.albums or []
    track_id = str(track.id).split(":")[0]
    path = f"album/{albums[0].id}/track/{track_id}" if albums else f"track/{track_id}"
    cover = track.og_image or track.cover_uri
    if cover:
        cover = "https://" + cover.removeprefix("https://").removeprefix("http://").replace(
            "%%", "400x400"
        )
    return Track(
        title=track.title,
        version=track.version or "",
        artist=", ".join(track.artists_name()),
        album=albums[0].title if albums else "",
        duration=(track.duration_ms or 0) / 1000,
        cover=cover,
        url=f"https://music.yandex.ru/{path}",
        app_url=f"yandexmusic://{path}",
        source="Yandex",
    )


class YandexCatalog:
    name = "Yandex"

    def __init__(self, client=None):
        self.client = client

    def search(self, media: MediaSnapshot, cancelled=lambda: False) -> list[Track]:
        if self.client is None:
            self.client = Client()
        query = f"{media.artist} {media.title}"
        tracks = []
        for text in dict.fromkeys((query, normalize(query))):
            if cancelled():
                break
            logger.info("Yandex search: query=%r", text)
            result = self.client.search(text, type_="track", nocorrect=True, timeout=4)
            if result is None or result.tracks is None:
                continue
            tracks.extend(
                track_metadata(track)
                for track in result.tracks.results[:25]
                if track.type in (None, "music", "track")
            )
            if choose(media, tracks):
                break
        return tracks

import logging
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event

from .catalogs import DeezerCatalog, ITunesCatalog
from .matching import choose, compare
from .models import MediaSnapshot, Track
from .yandex import YandexCatalog

logger = logging.getLogger(__name__)
UNUSED_SOURCES = (("Yandex", "unused"), ("iTunes", "unused"), ("Deezer", "unused"))


@dataclass(frozen=True)
class SearchResult:
    track: Track | None = None
    state: str = "searching"
    sources: tuple[tuple[str, str], ...] = UNUSED_SOURCES


class TrackResolver:
    def __init__(self, providers=None, clock=time.monotonic):
        self.providers = (
            providers
            if providers is not None
            else [
                YandexCatalog(),
                ITunesCatalog(),
                DeezerCatalog(),
            ]
        )
        self._clock = clock
        self._cache = OrderedDict()
        self._retry_at = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="catalog-search")
        self._pending = None
        self._pending_key = None
        self._cancel = Event()
        self._generation = 0
        self._progress = SearchResult()

    def set_client(self, client) -> None:
        self._cancel.set()
        self._generation += 1
        self._cache.clear()
        self._retry_at.clear()
        # Replace the adapter so an in-flight request keeps its original credentials.
        self.providers = [
            YandexCatalog(client) if p.name == "Yandex" else p for p in self.providers
        ]

    def resolve(self, media: MediaSnapshot) -> SearchResult:
        key = (self._generation, media.title, media.artist, media.album, round(media.duration))
        if self._pending is not None:
            if self._pending.done():
                result = self._pending.result()
                if result.state != "cancelled" and self._pending_key[0] == self._generation:
                    self._cache[self._pending_key] = (
                        self._clock() + (3600 if result.track else 60),
                        result,
                    )
                self._pending = None
                while len(self._cache) > 128:
                    self._cache.popitem(last=False)
            elif key != self._pending_key:
                self._cancel.set()
        cached = self._cache.get(key)
        if cached and cached[0] > self._clock():
            self._cache.move_to_end(key)
            return cached[1]
        if not media.artist.strip():
            logger.info("Search skipped: media has no artist credit")
            result = SearchResult(state="not_found")
            self._cache[key] = (self._clock() + 60, result)
            while len(self._cache) > 128:
                self._cache.popitem(last=False)
            return result
        if self._pending is None:
            self._cancel = Event()
            self._pending_key = key
            self._progress = SearchResult()
            self._pending = self._executor.submit(
                self._search,
                media,
                tuple(self.providers),
                self._cancel,
            )
        return self._progress if key == self._pending_key else SearchResult()

    def _search(self, media, providers, cancel):
        unavailable = False
        states = {provider.name: "unused" for provider in providers}
        for provider in providers:
            if cancel.is_set():
                return SearchResult(state="cancelled")
            if self._clock() < self._retry_at.get(provider, 0):
                unavailable = True
                states[provider.name] = "unavailable"
                logger.info("%s search skipped: retry backoff active", provider.name)
                continue
            started = self._clock()
            states[provider.name] = "searching"
            self._progress = SearchResult(sources=tuple(states.items()))
            try:
                tracks = provider.search(media, cancel.is_set)
                if cancel.is_set():
                    return SearchResult(state="cancelled")
                selected = choose(media, tracks)
                logger.info(
                    "%s returned %d candidates in %.2fs",
                    provider.name,
                    len(tracks),
                    self._clock() - started,
                )
                for track in tracks[:5]:
                    logger.info(
                        "Candidate [%s]: %r — %r; %.1fs; %s",
                        provider.name,
                        track.artist,
                        track.full_title,
                        track.duration,
                        compare(media, track)[1],
                    )
                if selected:
                    states[provider.name] = "matched"
                    logger.info(
                        "Matched [%s]: %r — %r; album=%r; url=%s; cover=%s",
                        provider.name,
                        selected.artist,
                        selected.full_title,
                        selected.album,
                        selected.url or "none",
                        selected.cover or "none",
                    )
                    return SearchResult(selected, "matched", tuple(states.items()))
                states[provider.name] = "not_found"
            except Exception as error:
                unavailable = True
                states[provider.name] = "unavailable"
                self._retry_at[provider] = self._clock() + 60
                logger.warning("%s search unavailable (%s)", provider.name, type(error).__name__)
        if cancel.is_set():
            return SearchResult(state="cancelled")
        state = "unavailable" if unavailable else "not_found"
        logger.info("Search finished: %s; no verified catalog match", state)
        return SearchResult(state=state, sources=tuple(states.items()))

    def close(self) -> None:
        self._cancel.set()
        self._executor.shutdown(wait=True, cancel_futures=True)

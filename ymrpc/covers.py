"""Opt-in, single-flight fallback artwork with bounded in-memory caches."""

import logging
import time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass, field
from hashlib import sha256
from threading import Event, Lock, Thread
from urllib.error import HTTPError

from .cover_hosts import COVER_HOSTS, UNUSED_UPLOADS
from .thumbnail import normalize_thumbnail, read_thumbnail

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoverResult:
    url: str | None = None
    host: str = ""
    state: str = "unused"
    sources: tuple[tuple[str, str], ...] = UNUSED_UPLOADS


@dataclass
class _Entry:
    data: bytes | None
    result: CoverResult
    expires: float = float("inf")
    read_attempts: int = 0


@dataclass
class _Job:
    key: tuple
    deadline: float
    future: Future = field(default_factory=Future)
    cancel: Event = field(default_factory=Event)
    lock: Lock = field(default_factory=Lock)
    progress: CoverResult = field(default_factory=lambda: CoverResult(state="reading"))
    timed_out: bool = False
    read_attempts: int = 0


class FallbackCovers:
    def __init__(self, *, hosts=COVER_HOSTS, reader=read_thumbnail,
                 normalize=normalize_thumbnail, clock=time.monotonic, authorized=lambda: True):
        self._hosts = hosts
        self._reader = reader
        self._normalize = normalize
        self._clock = clock
        self._authorized = authorized
        self._cache = OrderedDict()
        self._uploaded = OrderedDict()
        self._retry_at = {}
        self._read_retry_at = 0
        self._job = None
        self._closed = False

    def poll(self, media=None, properties=None, *, enabled=False) -> CoverResult:
        """Never block the presence loop, even if a COM getter blocks forever."""
        key = (media.artwork_key, *media.identity, media.album) if media else None
        active = enabled and key is not None and not self._closed
        now = self._clock()
        job = self._job
        if job:
            if not active or job.key != key:
                job.cancel.set()
            with job.lock:
                if not job.future.done() and now >= job.deadline and not job.timed_out:
                    job.timed_out = True
                    job.cancel.set()
                    state = job.progress.state
                    states = tuple(
                        (name, "unavailable" if status == "uploading" else status)
                        for name, status in job.progress.sources
                    )
                    job.progress = CoverResult(state="unavailable", sources=states)
                    self._read_retry_at = now + 30
                    logger.warning("Fallback artwork timed out during %s; retaining single flight", state)
                progress = job.progress
            if job.future.done():
                entry = job.future.result()
                if job.timed_out:
                    entry = _Entry(entry.data, progress, now + 30 if entry.data else float("inf"))
                elif job.cancel.is_set():
                    # Retain already-read bytes, but never publish a cancelled URL.
                    entry = _Entry(entry.data, CoverResult(), 0) if entry.data else entry
                entry.read_attempts = job.read_attempts
                if (entry.data is None and entry.result.state == "unavailable"
                        and entry.read_attempts < 2):
                    entry.expires = now + 30
                self._cache[job.key] = entry
                self._cache.move_to_end(job.key)
                # Normalized JPEGs are <=512px; also bound their aggregate size.
                while len(self._cache) > 32 or sum(
                    len(e.data or b"") for e in self._cache.values()
                ) > 8 * 1024 * 1024:
                    self._cache.popitem(last=False)
                self._job = job = None
            elif active and job.key == key:
                return (
                    progress if job.timed_out or not job.cancel.is_set()
                    else CoverResult(state="unavailable")
                )
        if not active:
            return CoverResult(state="disabled" if not enabled else "unused")
        cached = self._cache.get(key)
        if cached and now < cached.expires:
            self._cache.move_to_end(key)
            return cached.result
        # Never enqueue a second native read or HTTP upload behind a stuck one.
        if job:
            return CoverResult(state="unavailable" if job.timed_out else "waiting")
        data = cached.data if cached else None
        if data is None and now < self._read_retry_at:
            return CoverResult(state="unavailable")
        if data is None and properties is None:
            return CoverResult(state="waiting")
        job = self._job = _Job(
            key, now + (35 if data else 5),
            read_attempts=cached.read_attempts if cached else 0,
        )
        Thread(target=self._run, args=(job, properties, data), name="fallback-artwork",
               daemon=True).start()
        return job.progress

    def _run(self, job, properties, data):
        entry = _Entry(data, CoverResult(state="unavailable"))
        try:
            if self._cancelled(job):
                return
            if data is None:
                job.read_attempts += 1
                raw = self._reader(properties)
                if raw is None:
                    entry = _Entry(None, CoverResult(state="absent"))
                    return
                data = self._normalize(raw)
                entry = _Entry(data, CoverResult(), 0)
            if self._cancelled(job):
                return
            with job.lock:
                if self._clock() >= job.deadline:
                    job.cancel.set()
                    job.timed_out = True
                    job.progress = CoverResult(state="unavailable")
                    self._read_retry_at = self._clock() + 30
                    entry = _Entry(data, CoverResult(state="unavailable"))
                    return
                job.deadline = self._clock() + 35
            digest = sha256(data).digest()
            cached = self._uploaded.get(digest)
            if cached and self._clock() < cached[0]:
                entry = _Entry(data, cached[1], cached[0])
                return
            states = dict(UNUSED_UPLOADS)
            for host in self._hosts:
                if self._cancelled(job):
                    return
                retry = self._retry_at.get(host.name)
                if retry and self._clock() < retry[0]:
                    states[host.name] = retry[1]
                    continue
                states[host.name] = "uploading"
                with job.lock:
                    job.progress = CoverResult(state="uploading", sources=tuple(states.items()))
                try:
                    uploaded = host.upload(data)
                    if self._cancelled(job):
                        return
                    states[host.name] = "uploaded"
                    result = CoverResult(uploaded.url, host.name, "uploaded", tuple(states.items()))
                    expires = self._clock() + uploaded.lifetime
                    self._uploaded[digest] = (expires, result)
                    self._uploaded.move_to_end(digest)
                    while len(self._uploaded) > 64:
                        self._uploaded.popitem(last=False)
                    entry = _Entry(data, result, expires)
                    logger.info("Fallback artwork uploaded to %s", host.name)
                    return
                except Exception as error:
                    limited = isinstance(error, HTTPError) and error.code == 429
                    state = "rate_limited" if limited else "unavailable"
                    delay = 3600 if limited else 60
                    if limited:
                        try:
                            delay = max(60, min(86400, int(
                                (error.headers or {}).get("Retry-After", delay)
                            )))
                        except (TypeError, ValueError):
                            pass
                    self._retry_at[host.name] = (self._clock() + delay, state)
                    states[host.name] = state
                    logger.warning("Artwork upload failed: host=%s; error=%s", host.name,
                                   type(error).__name__)
            entry = _Entry(data, CoverResult(state="unavailable", sources=tuple(states.items())),
                           self._clock() + 60)
        except Exception as error:
            self._read_retry_at = self._clock() + 30
            logger.warning("Windows thumbnail unavailable (%s)", type(error).__name__)
        finally:
            job.future.set_result(entry)

    def _cancelled(self, job):
        if self._closed or not self._authorized():
            job.cancel.set()
        return job.cancel.is_set()

    def close(self):
        self._closed = True
        if self._job:
            self._job.cancel.set()
        # A native call cannot safely be killed. A daemon is deliberately used
        # instead of ThreadPoolExecutor, whose shutdown can hang application exit.
        self._cache.clear()

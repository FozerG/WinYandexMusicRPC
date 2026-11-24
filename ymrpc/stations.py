import asyncio
import contextlib
import ipaddress
import json
import logging
import math
import re
import ssl
import time
from dataclasses import dataclass, replace
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

import certifi
from websockets.asyncio.client import connect
from zeroconf import IPVersion, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from .models import MediaSnapshot, PlaybackStatus, StationPreference, Track
from .ynison import YnisonSnapshot

logger = logging.getLogger(__name__)
wire_logger = logging.getLogger(__name__ + ".wire")
wire_logger.disabled = True
SERVICE = "_yandexio._tcp.local."
STALE_AFTER = 20


@dataclass(frozen=True)
class Station:
    device_id: str
    platform: str
    name: str
    room: str = ""
    model: str = ""


def local_address(value: str) -> str:
    address = ipaddress.ip_address(value.strip())
    if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
        raise ValueError("A local network IP address is required")
    return str(address)


def request_json(url, token):
    request = Request(url, headers={"Authorization": "OAuth " + token})
    with urlopen(request, timeout=8, context=ssl.create_default_context(cafile=certifi.where())) as r:
        data = json.load(r)
    if data.get("status", "ok") != "ok":
        raise ValueError("Yandex request failed")
    return data


def load_stations(token):
    data = request_json("https://quasar.yandex.net/glagol/device_list", token)
    metadata, rooms = {}, {}
    with contextlib.suppress(Exception):
        info = request_json("https://api.iot.yandex.net/v1.0/user/info", token)
        rooms = {r["id"]: r.get("name", "") for r in info.get("rooms", [])}
        metadata = {d["quasar_info"]["device_id"]: d for d in info.get("devices", [])
                    if d.get("quasar_info", {}).get("device_id")}
    stations = []
    for d in data.get("devices", []):
        platform = d.get("platform", "")
        if not d.get("id") or not platform or any(
            word in platform for word in ("_app_", "_ios", "_android", "yandexmodule", "yandex_tv")
        ):
            continue
        extra = metadata.get(d["id"], {})
        if extra and not extra.get("type", "").startswith("devices.types.smart_speaker"):
            continue
        stations.append(Station(
            d["id"], platform, extra.get("name") or d.get("name") or platform,
            rooms.get(extra.get("room"), ""), (extra.get("device_info") or {}).get("model", ""),
        ))
    return tuple(sorted(stations, key=lambda d: d.device_id))


def parse_state(device: Station, state: dict) -> YnisonSnapshot:
    player = state.get("playerState") or {}
    if player.get("type") != "Track" or not player.get("title"):
        return YnisonSnapshot(state="idle", device_id=device.device_id, station=True)

    def seconds(key):
        try:
            value = float(player.get(key) or 0)
            return max(0, value) if math.isfinite(value) else 0
        except (ValueError, TypeError):
            return 0

    duration, position = seconds("duration"), seconds("progress")
    cover = (player.get("extra") or {}).get("coverURI")
    if isinstance(cover, str) and cover:
        cover = cover.replace("%%", "400x400")
        if cover.startswith("//"):
            cover = "https:" + cover
        elif "://" not in cover:
            cover = "https://" + cover
        if not cover.startswith("https://"):
            cover = None
    else:
        cover = None
    track_id = str(player.get("id", ""))
    url = f"https://music.yandex.ru/track/{track_id.split(':')[0]}" if re.fullmatch(
        r"\d+(?::\d+)?", track_id
    ) else None
    track = Track(player["title"], player.get("subtitle") or "", duration=duration,
                  cover=cover, url=url, app_url=url.replace("https://music.yandex.ru/", "yandexmusic://")
                  if url else None, source="Yandex Music")
    media = MediaSnapshot(
        source=f"Yandex Glagol · {device.device_id}", title=track.title, artist=track.artist,
        duration=duration, position=min(position, duration) if duration else position,
        status=PlaybackStatus.PLAYING if state.get("playing") is True else PlaybackStatus.PAUSED,
    )
    return YnisonSnapshot(media, track, "direct", device.name,
                          device_id=device.device_id, station=True)


class StationSources:
    def __init__(self):
        self.devices = ()
        self.state = "loading"
        self._token = None
        self._discovery = None
        self._browser = None
        self._addresses = {}
        self._resolving = set()
        self._tasks = {}
        self._snapshots = {}
        self._catalog = None
        self._next_catalog = 0
        self._selected = ""

    async def read(self, token, settings, cloud):
        if not settings.show_stations or not token:
            await self.close()
            if not token:
                self.state = "auth_required"
            return cloud
        if self._token != token:
            await self.close()
            self._token = token
        if self._discovery is None:
            try:
                self._discovery = AsyncZeroconf(ip_version=IPVersion.V4Only)
                self._browser = AsyncServiceBrowser(
                    self._discovery.zeroconf, SERVICE, handlers=[self._discover]
                )
            except OSError:
                logger.warning("Station discovery unavailable; retrying")
        now = time.monotonic()
        if self._catalog is None and now >= self._next_catalog:
            self._catalog = asyncio.create_task(asyncio.to_thread(load_stations, token))
        if self._catalog and self._catalog.done():
            try:
                self.devices = self._catalog.result()
                self.state = "ready" if self.devices else "empty"
                self._next_catalog = now + 300
            except Exception as error:
                logger.warning("Station list unavailable (%s)", type(error).__name__)
                self.state = "unavailable"
                self._next_catalog = now + 30
            self._catalog = None
        preferences = {p.device_id: p for p in settings.stations}
        wanted = {}
        for device in self.devices:
            pref = preferences.get(device.device_id, StationPreference(device.device_id))
            if not pref.enabled:
                continue
            address = self._addresses.get(device.device_id, "")
            if address:
                with contextlib.suppress(ValueError):
                    wanted[device.device_id] = (device, local_address(address))
        for device_id, (address, task) in list(self._tasks.items()):
            if device_id not in wanted or wanted[device_id][1] != address:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                self._tasks.pop(device_id)
                self._snapshots.pop(device_id, None)
        for device_id, (device, address) in wanted.items():
            if device_id not in self._tasks:
                self._tasks[device_id] = (address, asyncio.create_task(self._listen(device, address)))
        candidates = {}
        known = {d.device_id for d in self.devices} | set(preferences)
        if cloud.media and cloud.device_id not in known:
            candidates['cloud:' + cloud.device_id] = cloud
        for device_id, (snapshot, updated) in self._snapshots.items():
            if device_id not in wanted or now - updated > STALE_AFTER or not snapshot.media:
                continue
            if snapshot.media.status == PlaybackStatus.PLAYING:
                position = snapshot.media.position + max(0, now - updated)
                if snapshot.media.duration:
                    position = min(position, snapshot.media.duration)
                snapshot = replace(snapshot, media=replace(snapshot.media, position=position))
            candidates['station:' + device_id] = snapshot
        return self.select(candidates, cloud if not cloud.media else YnisonSnapshot(state="idle"))

    @property
    def playing_devices(self):
        now = time.monotonic()
        return tuple(sorted(
            device_id for device_id, (snapshot, updated) in self._snapshots.items()
            if now - updated <= STALE_AFTER and snapshot.media
            and snapshot.media.status == PlaybackStatus.PLAYING
        ))

    def select(self, candidates, fallback):
        playing = {k: v for k, v in candidates.items()
                   if v.media.status == PlaybackStatus.PLAYING}
        pool = playing or candidates
        if self._selected not in pool:
            self._selected = min(pool, default="")
        return pool.get(self._selected, fallback)

    def _discover(self, zeroconf, service_type, name, state_change):
        if state_change == ServiceStateChange.Removed:
            return
        task = asyncio.create_task(self._resolve(service_type, name))
        self._resolving.add(task)
        task.add_done_callback(self._resolving.discard)

    async def _resolve(self, service_type, name):
        try:
            info = AsyncServiceInfo(service_type, name)
            if not await info.async_request(self._discovery.zeroconf, 3000):
                return
            device_id = info.properties.get(b"deviceId", b"").decode()
            platform = info.properties.get(b"platform", b"").decode()
            for address in info.parsed_addresses(IPVersion.V4Only):
                if device_id and platform:
                    self._addresses[device_id] = local_address(address)
                    break
        except (OSError, ValueError, AttributeError):
            pass

    async def _listen(self, device, address):
        delay = 1
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        tls.check_hostname = False
        tls.verify_mode = ssl.CERT_NONE
        host = f"[{address}]" if ":" in address else address
        while True:
            try:
                query = urlencode({"device_id": device.device_id, "platform": device.platform})
                response = await asyncio.to_thread(
                    request_json, "https://quasar.yandex.net/glagol/token?" + query, self._token
                )
                conversation_token = response["token"]
                async with connect(f"wss://{host}:1961", ssl=tls, proxy=None,
                                   open_timeout=5, close_timeout=2, ping_interval=10,
                                   ping_timeout=10, max_size=2**20, logger=wire_logger) as ws:
                    async def send(command, conversation_token=conversation_token):
                        await ws.send(json.dumps({
                            "conversationToken": conversation_token, "id": str(uuid4()),
                            "payload": {"command": command}, "sentTime": int(time.time() * 1000),
                        }))
                    await send("softwareVersion")
                    last_state = time.monotonic()
                    while True:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=5)
                        except TimeoutError:
                            if time.monotonic() - last_state >= STALE_AFTER:
                                raise TimeoutError("Station state expired") from None
                            await send("ping")
                            continue
                        data = json.loads(raw)
                        if isinstance(data.get("state"), dict):
                            snapshot = parse_state(device, data["state"])
                            last_state = time.monotonic()
                            self._snapshots[device.device_id] = (snapshot, last_state)
                            delay = 1
                        if time.monotonic() - last_state >= STALE_AFTER:
                            raise TimeoutError("Station state expired")
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.debug("Station connection interrupted (%s)", type(error).__name__)
            finally:
                self._snapshots.pop(device.device_id, None)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    async def close(self):
        tasks = [task for _, task in self._tasks.values()] + list(self._resolving)
        if self._catalog:
            tasks.append(self._catalog)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self._browser:
            await self._browser.async_cancel()
        if self._discovery:
            await self._discovery.async_close()
        self.__init__()

"""Anonymous temporary image hosts. Only normalized image bytes leave the app."""

import json
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import uuid4

import certifi

from . import __version__
from .constants import APP_NAME, REPO_URL

USER_AGENT = f"{APP_NAME}/{__version__} (+{REPO_URL})"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward a private upload to an unexpected host.
        return None


def post_image(url, field, data, fields):
    boundary = uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'
            f'{value}\r\n'.encode()
        )
    parts.extend((
        f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; '
        'filename="cover.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode(),
        data,
        f'\r\n--{boundary}--\r\n'.encode(),
    ))
    request = Request(url, data=b"".join(parts), headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    # OpenSSL can select an expired chain from the Windows certificate store.
    # Use maintained public roots with normal hostname/certificate verification.
    context = ssl.create_default_context(cafile=certifi.where())
    with build_opener(_NoRedirect(), HTTPSHandler(context=context)).open(request, timeout=8) as response:
        body = response.read(65537)
    if len(body) > 65536:
        raise ValueError("Upload response is too large")
    result = json.loads(body)
    if not isinstance(result, dict):
        raise ValueError("Invalid upload response")
    return result


@dataclass(frozen=True)
class HostedCover:
    url: str
    lifetime: float


@dataclass(frozen=True)
class CoverHost:
    name: str
    endpoint: str
    field: str
    fields: tuple[tuple[str, str], ...]
    lifetime: int
    domain: str

    def upload(self, data, *, post=post_image, wall_clock=time.time):
        started = wall_clock()
        result = post(self.endpoint, self.field, data, dict(self.fields))
        if self.name == "Uguu":
            if result.get("success") is not True:
                raise ValueError("Uguu rejected the upload")
            item = result["files"][0]
            url = item["url"]
            # Uguu can return an old duplicate with unknown remaining retention.
            if item.get("dupe"):
                raise ValueError("Uguu returned a duplicate with unknown expiry")
            expires = started + self.lifetime
        elif self.name == "Img4.you":
            url = result["download"]
            expires = datetime.fromisoformat(result["expires_at"].replace("Z", "+00:00")).timestamp()
        else:
            if result.get("kind") != "image":
                raise ValueError("Host did not return a plain image")
            url = result["url"]
            expires = float(result["expires"])
        parsed = urlsplit(url)
        hostname = parsed.hostname or ""
        if (
            parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443)
            or not (hostname == self.domain or hostname.endswith("." + self.domain))
        ):
            raise ValueError("Host returned an unexpected image URL")
        lifetime = min(expires - wall_clock(), self.lifetime) - 120
        if lifetime <= 0:
            raise ValueError("Host returned an expired image URL")
        return HostedCover(url, lifetime)


COVER_HOSTS = (
    CoverHost("imgdb.io", "https://imgdb.io/api/v1/upload", "file",
              (("ttl", "3600"),), 3600, "imgdb.io"),
    CoverHost("Uguu", "https://uguu.se/upload", "files[]", (), 10800, "uguu.se"),
    CoverHost("Img4.you", "https://img4.you/images", "file",
              (("expires_in_hours", "1"),), 3600, "img4.you"),
)
UNUSED_UPLOADS = tuple((host.name, "unused") for host in COVER_HOSTS)

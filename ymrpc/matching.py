import re
import unicodedata

from .models import MediaSnapshot, Track

FEATURE = re.compile(r"\s*[\[(](?:feat\.?|ft\.?|featuring)\s+(.+?)[\])]", re.I)
TRAILING_FEATURE = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+(.+)$", re.I)
SEPARATOR = re.compile(r"\s*(?:,|;|&|\bfeat\.?\s|\bft\.?\s|\bfeaturing\s)\s*", re.I)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    return " ".join("".join(c if c.isalnum() else " " for c in value).split())


def artists(value: str) -> set[str]:
    return {normalize(part) for part in SEPARATOR.split(value) if normalize(part)}


def title_parts(value: str) -> tuple[str, set[str]]:
    guests = set()
    for feature in FEATURE.finditer(value):
        guests.update(artists(feature.group(1)))
    value = FEATURE.sub("", value)
    trailing = TRAILING_FEATURE.search(value)
    if trailing:
        guests.update(artists(trailing.group(1)))
        value = value[: trailing.start()]
    return normalize(value), guests


def base_title(value: str) -> str:
    value = FEATURE.sub("", value)
    value = TRAILING_FEATURE.sub("", value)
    while True:
        shortened = re.sub(r"\s*[\[(][^()[\]]+[\])]\s*$", "", value)
        if shortened == value or not shortened.strip():
            break
        value = shortened
    value = re.split(r"\s+[–—-]\s+", value, maxsplit=1)[0]
    return normalize(value)


def compare(media: MediaSnapshot, track: Track) -> tuple[bool, str]:
    title, guests = title_parts(media.title)
    candidate, candidate_guests = title_parts(track.title)
    full_title, version_guests = title_parts(track.full_title)
    candidate_guests |= version_guests
    different_suffix = title not in (candidate, full_title)
    if not title:
        return False, "missing title"
    if different_suffix:
        base = base_title(media.title)
        if not base or base != base_title(track.title):
            return False, "base title differs"
        if media.duration <= 0 or track.duration <= 0:
            return False, "different title suffixes require duration verification"
    wanted = artists(media.artist) | guests
    actual = artists(track.artist) | candidate_guests
    if not wanted or not wanted <= actual:
        return False, "artist credits differ or are missing"
    if media.duration > 0 and track.duration > 0:
        if abs(media.duration - track.duration) > max(8, media.duration * 0.04):
            return False, "duration differs"
    if different_suffix:
        return True, "base title, artist credits and duration agree; title suffixes differ"
    if track.version and title == candidate and title != full_title:
        return (
            True,
            "title, artist credits and available duration agree; player omits catalog version",
        )
    return True, "title, artist credits and available duration agree"


def choose(media: MediaSnapshot, tracks: list[Track]) -> Track | None:
    candidates = [track for track in tracks if compare(media, track)[0]]
    if not candidates:
        return None
    # Prefer the player's album, then the closest duration among verified recordings.
    return min(
        candidates,
        key=lambda track: (
            bool(media.album) and normalize(media.album) != normalize(track.album),
            abs(media.duration - track.duration) if media.duration and track.duration else 999,
            not bool(track.cover),
        ),
    )

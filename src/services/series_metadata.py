"""Conservative helpers for structured book-series metadata."""

from __future__ import annotations

import re
from typing import Any, Iterable


_SERIES_SUFFIX = re.compile(
    r"^(?P<series>.+?)\s+"
    r"(?:(?:book|volume|vol[.]?)\s*|#\s*)"
    r"(?P<number>\d+(?:[.]\d+)?)$",
    flags=re.IGNORECASE,
)

_SERIES_PREFIX = re.compile(
    r"^(?P<series>.+?\D)\s+"
    r"(?P<number>\d+(?:[.]\d+)?)\s*"
    r"(?:-|\u2013|\u2014|:)\s+"
    r"(?P<title>.+)$",
    flags=re.IGNORECASE,
)

_NUMBER_WORDS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
    "seventh": "7",
    "eighth": "8",
    "ninth": "9",
    "tenth": "10",
    "eleventh": "11",
    "twelfth": "12",
}
_DESCRIPTION_NUMBER = (
    r"(?:\d+(?:[.]\d+)?(?:st|nd|rd|th)?|"
    + "|".join(_NUMBER_WORDS)
    + r")"
)
_DESCRIPTION_SERIES = re.compile(
    r"\b(?:book\s+(?P<after>" + _DESCRIPTION_NUMBER + r")|"
    r"(?P<before>" + _DESCRIPTION_NUMBER + r")\s+book)"
    r"\s+in\b[^.!?]{0,120}?\bseries\s*[,;:\u2013\u2014-]\s*"
    r"(?P<series>[^,.;!?]{3,100})",
    flags=re.IGNORECASE,
)

# Providers normally return only the immediate numbered series. These
# verified relationships preserve a higher-level reading universe without
# merging every book by an author into one folder. The group number orders
# component series; the normal series number still orders books within it.
_KNOWN_SERIES_GROUPS = {
    "the belgariad": ("Belgariad Universe", "1"),
    "the malloreon": ("Belgariad Universe", "2"),
    "belgariad prequels": ("Belgariad Universe", "3"),
    "the elenium": ("Sparhawk Universe", "1"),
    "the tamuli": ("Sparhawk Universe", "2"),
}

# The 1632 books are labelled differently by otherwise reputable providers.
# Goodreads commonly uses ``Assiti Shards``, retailers use ``Ring of Fire``,
# and some editions expose the curated ``Main Line Novels`` reading list as
# though it were a separate series.  They must share one folder in Twano.
_RING_OF_FIRE_ALIASES = {
    "1632 universe",
    "1632 universe/ring of fire",
    "assiti shards",
    "ring of fire",
    "ring of fire main line novels",
    "ring of fire series",
}

# The canonical order follows the provider's broad Assiti Shards sequence,
# which includes both main-line novels and related volumes.  Explicit title
# entries also repair narrower retailer numbering before files are organised.
_RING_OF_FIRE_ORDER = {
    "1632": "1",
    "1633": "2",
    "1634 the galileo affair": "3",
    "1634 the ram rebellion": "4",
    "1635 the cannon law": "8",
    "1635 the eastern front": "10",
    "1635 the tangled web": "14",
}


def split_title_series(value: str) -> tuple[str, str, str]:
    """Split explicit title/series patterns without guessing ordinary titles."""
    title = " ".join(str(value or "").split())
    match = re.fullmatch(r"(?P<title>.+?)\s*\((?P<label>[^()]+)\)", title)
    if match is not None:
        series, number = parse_series_label(match.group("label"))
        if series and number:
            return match.group("title").strip(), series, number
    prefix_match = _SERIES_PREFIX.fullmatch(title)
    if prefix_match is not None:
        return (
            prefix_match.group("title").strip(),
            prefix_match.group("series").strip(" ,-:"),
            prefix_match.group("number"),
        )
    return title, "", ""


def parse_series_label(value: str) -> tuple[str, str]:
    """Return a series name and order from a provider's explicit label."""
    label = " ".join(str(value or "").split()).strip(" ,-:")
    match = _SERIES_SUFFIX.fullmatch(label)
    if match is None:
        return label, ""
    return match.group("series").strip(" ,-:"), match.group("number")


def google_series_details(
    series_info: Any,
    *,
    title_series: str = "",
    title_number: str = "",
) -> tuple[str, str]:
    """Read useful structured fields from a Google Books ``seriesInfo``."""
    if not isinstance(series_info, dict):
        return title_series, title_number
    series = clean_series_name(next(
        (
            " ".join(str(series_info.get(field) or "").split())
            for field in ("seriesName", "title")
            if str(series_info.get(field) or "").strip()
        ),
        title_series,
    ))
    number = ""
    volume_series = series_info.get("volumeSeries")
    if isinstance(volume_series, list):
        for item in volume_series:
            if not isinstance(item, dict):
                continue
            raw_number = item.get("orderNumber")
            if raw_number not in (None, ""):
                number = str(raw_number).strip()
                break
    if not number:
        number = str(series_info.get("bookDisplayNumber") or "").strip()
    return series, number or title_number


def clean_series_name(value: str) -> str:
    """Remove provider display truncation without changing a real series name."""
    name = " ".join(str(value or "").split()).strip()
    if name.endswith("...") or name.endswith("…"):
        name = name.rstrip(".…").rstrip()
    return name


def canonical_series_details(
    value: str,
    *,
    title: str = "",
    number: object = "",
) -> tuple[str, str]:
    """Return one stable series label and order for verified provider aliases."""
    name = clean_series_name(value)
    cleaned_number = str(number or "").strip()
    if name.casefold() not in _RING_OF_FIRE_ALIASES:
        return name, cleaned_number
    title_key = re.sub(
        r"[^a-z0-9]+",
        " ",
        clean_series_name(title).casefold(),
    ).strip()
    return "Ring of Fire", _RING_OF_FIRE_ORDER.get(title_key, cleaned_number)


def _series_comparison_key(value: str) -> str:
    """Return a wording/casing-insensitive key for comparing series names.

    Collapses the differences a free-text resolver (a web search snippet,
    a scraped article) commonly introduces run to run: casing, punctuation,
    extra whitespace, and a redundant trailing "series" word.
    """
    normalised = "".join(
        character if character.isalnum() else " "
        for character in clean_series_name(value).casefold()
    )
    normalised = " ".join(normalised.split())
    if normalised.endswith(" series"):
        normalised = normalised[: -len(" series")]
    return normalised


def match_existing_series(value: str, known_series: Iterable[str]) -> str:
    """Return an already-catalogued series name matching ``value``, if any.

    A resolver can return this user's own series under slightly different
    wording on different runs (casing, an extra trailing "series" word, a
    stray comma). Rather than creating a new, near-duplicate series folder
    each time, this snaps back onto whatever name this user's own library
    already established -- the exact wording of the first-known instance
    always wins, so every volume of a series keeps landing in the same
    place regardless of what a later lookup happens to return.
    """
    name = clean_series_name(value)
    if not name:
        return name
    key = _series_comparison_key(name)
    if not key:
        return name
    for candidate in known_series:
        candidate_name = clean_series_name(str(candidate or ""))
        if not candidate_name:
            continue
        if _series_comparison_key(candidate_name) == key:
            return candidate_name
    return name


def known_series_group(value: str) -> tuple[str, str]:
    """Return a verified parent group and component order for one series."""
    series = clean_series_name(value).casefold()
    return _KNOWN_SERIES_GROUPS.get(series, ("", ""))


def series_from_description(value: str) -> tuple[str, str]:
    """Read an explicitly named series and order from provider prose.

    This intentionally requires both a clear book number and a series name
    introduced after punctuation. General mentions of sequels or series are
    ignored so descriptive marketing text cannot silently reorganise files.
    """
    description = " ".join(str(value or "").split())
    match = _DESCRIPTION_SERIES.search(description)
    if match is None:
        return "", ""
    series = match.group("series").strip(" ,-:\u2013\u2014")
    number = _description_number(match.group("after") or match.group("before"))
    if not series or not number:
        return "", ""
    return series, number


def _description_number(value: str) -> str:
    cleaned = str(value or "").strip().casefold()
    if cleaned in _NUMBER_WORDS:
        return _NUMBER_WORDS[cleaned]
    match = re.fullmatch(r"(\d+(?:[.]\d+)?)(?:st|nd|rd|th)?", cleaned)
    return match.group(1) if match is not None else ""

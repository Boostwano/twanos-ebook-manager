"""Calibre-independent direct cover-provider search."""

from __future__ import annotations

import html
import json
import re
import socket
from dataclasses import dataclass, replace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from services.series_metadata import google_series_details, split_title_series


GOOGLE_BOOKS_SEARCH_URL = "https://www.googleapis.com/books/v1/volumes"
APPLE_BOOKS_SEARCH_URL = "https://itunes.apple.com/search"
ISBNDB_API_URL = "https://api2.isbndb.com"
DIRECT_COVER_TIMEOUT_SECONDS = 10.0
DIRECT_COVER_USER_AGENT = "Twanos-eBook-Manager/4 (manual cover search)"
DIRECT_COVER_ACCEPT_LANGUAGE = "en-AU,en;q=0.9"


@dataclass(frozen=True)
class CoverSearchSource:
    """One direct cover provider retained for service compatibility."""

    source_id: str
    display_name: str
    automatic: bool
    description: str
    plugin_id: str = ""


COVER_SEARCH_SOURCES = (
    CoverSearchSource(
        "automatic",
        "All Automatic Sources",
        True,
        "Search every automatic cover plugin you have enabled.",
    ),
    CoverSearchSource(
        "open_library",
        "Open Library",
        True,
        "Search the Internet Archive's Open Library cover catalogue.",
        "open_library_metadata",
    ),
    CoverSearchSource(
        "google_books",
        "Google Books",
        True,
        "Search Google's public Books catalogue for edition covers.",
        "google_books_covers",
    ),
    CoverSearchSource(
        "hardcover",
        "Hardcover",
        True,
        "Search Hardcover using the API token saved on Plugins.",
        "hardcover_metadata",
    ),
    CoverSearchSource(
        "comic_vine",
        "Comic Vine",
        True,
        "Search comic and graphic-novel covers using your Comic Vine key.",
        "comic_vine_metadata",
    ),
    CoverSearchSource(
        "apple_books",
        "Apple Books",
        True,
        "Search Apple's public ebook catalogue for descriptions and covers.",
        "apple_books_metadata",
    ),
    CoverSearchSource(
        "amazon",
        "Amazon",
        True,
        "Search public Amazon book listings for matching cover artwork.",
        "amazon_metadata",
    ),
    CoverSearchSource(
        "goodreads",
        "Goodreads",
        True,
        "Search Goodreads' public book pages for cover art and series "
        "data. Off by default -- enable in Plugins to use.",
        "goodreads_metadata",
    ),
    CoverSearchSource(
        "isbndb",
        "ISBNdb",
        True,
        "Search ISBNdb using the API key saved on Plugins.",
        "isbndb_metadata",
    ),
    CoverSearchSource(
        "gutenberg",
        "Project Gutenberg",
        True,
        "Search public-domain ebook covers through Gutendex.",
        "gutenberg_metadata",
    ),
    CoverSearchSource(
        "big_book",
        "Big Book API",
        True,
        "Search Big Book API using the key saved on Plugins.",
        "big_book_metadata",
    ),
    CoverSearchSource(
        "openweb_ninja",
        "OpenWeb Ninja",
        True,
        "Search OpenWeb Ninja using the key saved on Plugins.",
        "openweb_ninja_metadata",
    ),
)


@dataclass(frozen=True)
class DirectCoverResult:
    """One result from a supported direct cover API."""

    title: str
    author: str
    isbn: str
    publisher: str
    language: str
    published_date: str
    cover_url: str
    source_url: str
    provider_name: str
    confidence: int
    confidence_reason: str
    description: str = ""
    series: str = ""
    series_number: str = ""
    series_group: str = ""
    series_group_number: str = ""
    provider_rating: float = 0.0
    rating_count: int = 0


class CoverSearchError(RuntimeError):
    """Readable failure from a direct cover provider."""


class CoverSearchService:
    """Search supported direct APIs without opening browser websites."""

    def __init__(self, *, timeout: float = DIRECT_COVER_TIMEOUT_SECONDS) -> None:
        self.timeout = float(timeout)

    @staticmethod
    def sources() -> tuple[CoverSearchSource, ...]:
        return COVER_SEARCH_SOURCES

    def search_google_books(
        self,
        *,
        title: str = "",
        author: str = "",
        isbn: str = "",
        api_key: str = "",
    ) -> tuple[DirectCoverResult, ...]:
        """Search the public Google Books volume catalogue."""
        queries = _book_queries(title=title, author=author, isbn=isbn)
        if not queries:
            raise ValueError("Enter a title, author, or ISBN to search.")
        all_results: list[DirectCoverResult] = []
        for query in queries:
            parameters = {
                "q": query,
                "maxResults": "10",
                "printType": "books",
                "projection": "full",
            }
            if api_key.strip():
                parameters["key"] = api_key.strip()
            url = f"{GOOGLE_BOOKS_SEARCH_URL}?{urlencode(parameters)}"
            request = Request(
                url,
                headers={
                    "User-Agent": DIRECT_COVER_USER_AGENT,
                    "Accept": "application/json",
                    "Accept-Language": DIRECT_COVER_ACCEPT_LANGUAGE,
                },
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    if not 200 <= response.status < 300:
                        raise CoverSearchError(
                            "Google Books did not accept the cover search."
                        )
                    payload = json.loads(response.read())
            except HTTPError as error:
                if error.code in {403, 429} and not api_key.strip():
                    raise CoverSearchError(
                        "Google Books limited the request. Open Plugins, "
                        "select Google Books, and configure an optional API "
                        "key before trying again."
                    ) from error
                raise CoverSearchError(
                    _google_rejection_message(error)
                ) from error
            except (
                URLError,
                TimeoutError,
                socket.timeout,
                json.JSONDecodeError,
                UnicodeDecodeError,
                OSError,
            ) as error:
                raise CoverSearchError(
                    "Google Books could not be reached. Check the internet "
                    "connection and try again."
                ) from error

            items = (
                payload.get("items", ())
                if isinstance(payload, dict)
                else ()
            )
            items = sorted(items, key=_google_australian_result_order)
            results = tuple(
                result
                for item in items
                if (
                    result := _map_google_book(
                        item,
                        wanted_title=title,
                        wanted_author=author,
                        wanted_isbn=isbn,
                    )
                )
            )
            all_results.extend(results)
        return tuple(
            {
                (
                    result.title.casefold(),
                    result.author.casefold(),
                    result.isbn,
                    result.cover_url,
                ): result
                for result in all_results
            }.values()
        )

    def search_google_books_excerpt(
        self,
        *,
        excerpt: str,
        author: str = "",
        api_key: str = "",
    ) -> tuple[DirectCoverResult, ...]:
        """Identify a book from a short opening-text fingerprint."""
        words = re.findall(r"[\w'\u2019-]+", excerpt, flags=re.UNICODE)
        phrase = " ".join(words[:16]).strip()
        if len(phrase) < 40:
            return ()
        query = f'"{phrase}"'
        if author.strip():
            query += f' inauthor:"{author.strip()}"'
        payload = self._google_payload(query=query, api_key=api_key)
        items = payload.get("items", ()) if isinstance(payload, dict) else ()
        results: list[DirectCoverResult] = []
        for item in items:
            result = _map_google_book(
                item,
                wanted_title="",
                wanted_author=author,
                wanted_isbn="",
            )
            if result is None or (author and not _same_author(author, result.author)):
                continue
            results.append(
                replace(
                    result,
                    confidence=90,
                    confidence_reason="Opening text and author match",
                )
            )
        return tuple(results)

    def _google_payload(self, *, query: str, api_key: str = "") -> dict:
        """Run one bounded Google Books catalogue request."""
        parameters = {
            "q": query,
            "maxResults": "10",
            "printType": "books",
            "projection": "full",
        }
        if api_key.strip():
            parameters["key"] = api_key.strip()
        request = Request(
            f"{GOOGLE_BOOKS_SEARCH_URL}?{urlencode(parameters)}",
            headers={
                "User-Agent": DIRECT_COVER_USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": DIRECT_COVER_ACCEPT_LANGUAGE,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    raise CoverSearchError(
                        "Google Books did not accept the opening-text search."
                    )
                payload = json.loads(response.read())
        except HTTPError as error:
            if error.code in {403, 429} and not api_key.strip():
                raise CoverSearchError(
                    "Google Books limited the request. Open Plugins, select "
                    "Google Books, and configure an optional API key before "
                    "trying again."
                ) from error
            raise CoverSearchError(_google_rejection_message(error)) from error
        except (
            URLError,
            TimeoutError,
            socket.timeout,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
        ) as error:
            raise CoverSearchError(
                "Google Books could not be reached. Check the internet "
                "connection and try again."
            ) from error
        return payload if isinstance(payload, dict) else {}

    def search_apple_books(
        self,
        *,
        title: str = "",
        author: str = "",
        isbn: str = "",
        country: str = "au",
    ) -> tuple[DirectCoverResult, ...]:
        """Search the public Apple Books catalogue without a user key."""
        terms = tuple(
            dict.fromkeys(
                value
                for value in (
                    isbn.strip(),
                    " ".join(
                        part for part in (title, author) if part.strip()
                    ),
                    title.strip(),
                )
                if value
            )
        )
        if not terms:
            raise ValueError("Enter a title, author, or ISBN to search.")
        all_results: list[DirectCoverResult] = []
        for term in terms:
            parameters = {
                "term": term,
                "country": country.casefold() or "au",
                "media": "ebook",
                "entity": "ebook",
                "limit": "25",
            }
            request = Request(
                f"{APPLE_BOOKS_SEARCH_URL}?{urlencode(parameters)}",
                headers={
                    "User-Agent": DIRECT_COVER_USER_AGENT,
                    "Accept": "application/json",
                    "Accept-Language": DIRECT_COVER_ACCEPT_LANGUAGE,
                },
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    if not 200 <= response.status < 300:
                        raise CoverSearchError(
                            "Apple Books did not accept the search."
                        )
                    payload = json.loads(response.read())
            except HTTPError as error:
                raise CoverSearchError(
                    f"Apple Books rejected the request (HTTP {error.code})."
                ) from error
            except (
                URLError,
                TimeoutError,
                socket.timeout,
                json.JSONDecodeError,
                UnicodeDecodeError,
                OSError,
            ) as error:
                raise CoverSearchError(
                    "Apple Books could not be reached. Check the internet "
                    "connection and try again."
                ) from error
            items = (
                payload.get("results", ())
                if isinstance(payload, dict)
                else ()
            )
            results = tuple(
                result
                for item in items
                if (
                    result := _map_apple_book(
                        item,
                        wanted_title=title,
                        wanted_author=author,
                    )
                )
            )
            all_results.extend(results)
        return tuple(
            {
                (
                    result.title.casefold(),
                    result.author.casefold(),
                    result.isbn,
                    result.cover_url,
                ): result
                for result in all_results
            }.values()
        )

    def search_isbndb(
        self,
        *,
        title: str = "",
        author: str = "",
        isbn: str = "",
        api_key: str,
    ) -> tuple[DirectCoverResult, ...]:
        """Search ISBNdb using a user-supplied API subscription key."""
        if not api_key.strip():
            raise CoverSearchError(
                "ISBNdb needs an API key. Open Plugins, select ISBNdb, "
                "then choose Configure API Key."
            )
        query = " ".join(
            part for part in (title, author) if part.strip()
        )
        endpoints: list[str] = []
        if isbn.strip():
            endpoints.append(f"/book/{quote(isbn.strip(), safe='')}")
        if query:
            endpoints.append(
                f"/books/{quote(query, safe='')}"
                f"?{urlencode({'page': 1, 'pageSize': 20})}"
            )
        if not endpoints:
            raise ValueError("Enter a title, author, or ISBN to search.")

        results: list[DirectCoverResult] = []
        seen: set[tuple[str, str]] = set()
        for endpoint in dict.fromkeys(endpoints):
            request = Request(
                ISBNDB_API_URL + endpoint,
                headers={
                    "User-Agent": DIRECT_COVER_USER_AGENT,
                    "Accept": "application/json",
                    "Accept-Language": DIRECT_COVER_ACCEPT_LANGUAGE,
                    "Authorization": api_key.strip(),
                },
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    if not 200 <= response.status < 300:
                        raise CoverSearchError(
                            "ISBNdb did not accept the search."
                        )
                    payload = json.loads(response.read())
            except HTTPError as error:
                if error.code == 404 and len(endpoints) > 1:
                    continue
                if error.code in {401, 403}:
                    message = (
                        "ISBNdb rejected the saved API key. Check the key or "
                        "subscription, then replace it in Plugins."
                    )
                elif error.code == 429:
                    message = (
                        "ISBNdb has reached the request limit for this API "
                        "key. Try again later or review the subscription quota."
                    )
                else:
                    message = (
                        f"ISBNdb rejected the request (HTTP {error.code})."
                    )
                raise CoverSearchError(message) from error
            except (
                URLError,
                TimeoutError,
                socket.timeout,
                json.JSONDecodeError,
                UnicodeDecodeError,
                OSError,
            ) as error:
                raise CoverSearchError(
                    "ISBNdb could not be reached. Check the internet "
                    "connection and try again."
                ) from error
            if not isinstance(payload, dict):
                continue
            raw_items = payload.get("books")
            if not isinstance(raw_items, list):
                raw_book = payload.get("book")
                raw_items = [raw_book] if isinstance(raw_book, dict) else []
            for item in raw_items:
                result = _map_isbndb_book(
                    item,
                    wanted_title=title,
                    wanted_author=author,
                    wanted_isbn=isbn,
                )
                if result is None:
                    continue
                key = (result.isbn.casefold(), result.cover_url)
                if key in seen:
                    continue
                seen.add(key)
                results.append(result)
        return tuple(results)


def _book_queries(*, title: str, author: str, isbn: str) -> tuple[str, ...]:
    queries: list[str] = []
    if isbn.strip():
        queries.append(f"isbn:{isbn.strip()}")
    if title.strip() and author.strip():
        queries.append(
            f'intitle:"{title.strip()}" inauthor:"{author.strip()}"'
        )
    if title.strip():
        queries.append(f'intitle:"{title.strip()}"')
    if not queries and author.strip():
        queries.append(f'inauthor:"{author.strip()}"')
    return tuple(dict.fromkeys(queries))


def _google_rejection_message(error: HTTPError) -> str:
    """Translate common Google key failures without exposing key material."""
    provider_message = ""
    provider_reason = ""
    try:
        payload = json.loads(error.read(16_384))
        detail = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(detail, dict):
            provider_message = _text(detail.get("message"))
            errors = detail.get("errors")
            if isinstance(errors, list):
                provider_reason = " ".join(
                    _text(item.get("reason"))
                    for item in errors
                    if isinstance(item, dict)
                )
    except (
        OSError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        AttributeError,
        TypeError,
    ):
        pass
    detail_key = f"{provider_reason} {provider_message}".casefold()
    if "api key not valid" in detail_key or "keyinvalid" in detail_key:
        return (
            "Google Books rejected the saved API key as invalid. Create or "
            "copy the key again in Google Cloud, then replace it in Plugins."
        )
    if (
        "accessnotconfigured" in detail_key
        or "has not been used" in detail_key
        or "not enabled" in detail_key
    ):
        return (
            "Google Books API is not enabled for this key's Google Cloud "
            "project. Enable Books API, wait a few minutes, then try again."
        )
    if (
        "referer" in detail_key
        or "referrer" in detail_key
        or "ip address" in detail_key
        or "blocked" in detail_key
    ):
        return (
            "The Google API key restrictions do not allow this Windows "
            "application request. Restrict the key to Books API, but do not "
            "use an HTTP website-referrer restriction."
        )
    if error.code == 429 or "quota" in detail_key or "ratelimit" in detail_key:
        return (
            "Google Books has reached the API quota for this key. Review its "
            "quota in Google Cloud or try again later."
        )
    return (
        f"Google Books rejected the request (HTTP {error.code}). Check that "
        "Books API is enabled and the key restrictions allow this Windows "
        "application."
    )


def _map_apple_book(
    item: Any,
    *,
    wanted_title: str,
    wanted_author: str,
) -> DirectCoverResult | None:
    if not isinstance(item, dict):
        return None
    title = _text(item.get("trackName"))
    author = _text(item.get("artistName"))
    cover_url = _apple_artwork_url(_text(item.get("artworkUrl100")))
    if not title or not cover_url:
        return None
    exact_title = bool(
        _normalise(wanted_title)
        and _normalise(wanted_title) == _normalise(title)
    )
    author_match = _same_author(wanted_author, author)
    title_match = _related_title(wanted_title, title)
    if wanted_title and not title_match:
        return None
    if exact_title and author_match:
        confidence, reason = 90, "Exact title and author match"
    elif exact_title:
        confidence, reason = 75, "Exact title match"
    elif title_match and author_match:
        confidence, reason = 80, "Related title and author match"
    else:
        confidence, reason = 70, "Related title match"
    release_date = _text(item.get("releaseDate")).split("T", 1)[0]
    return DirectCoverResult(
        title=title,
        author=author,
        isbn="",
        publisher=_text(item.get("sellerName")),
        language="",
        published_date=release_date,
        cover_url=cover_url,
        source_url=_secure_url(_text(item.get("trackViewUrl"))),
        provider_name="Apple Books",
        confidence=confidence,
        confidence_reason=reason,
        description=_plain_text(_text(item.get("description"))),
        provider_rating=_provider_rating(item.get("averageUserRating")),
        rating_count=_rating_count(item.get("userRatingCount")),
    )


def _map_isbndb_book(
    item: Any,
    *,
    wanted_title: str,
    wanted_author: str,
    wanted_isbn: str,
) -> DirectCoverResult | None:
    if not isinstance(item, dict):
        return None
    title = _text(item.get("title_long")) or _text(item.get("title"))
    cover_url = _secure_url(_text(item.get("image")))
    if not title or not cover_url:
        return None
    authors = _texts(item.get("authors"))
    isbn = _text(item.get("isbn13")) or _text(item.get("isbn"))
    exact_isbn = bool(
        wanted_isbn.strip()
        and _isbn_key(wanted_isbn) == _isbn_key(isbn)
    )
    exact_title = bool(
        _normalise(wanted_title)
        and _normalise(wanted_title) == _normalise(title)
    )
    author_match = any(
        _same_author(wanted_author, value) for value in authors
    )
    if exact_isbn:
        confidence, reason = 100, "Exact ISBN match"
    elif exact_title and author_match:
        confidence, reason = 90, "Exact title and author match"
    elif exact_title:
        confidence, reason = 75, "Exact title match"
    else:
        confidence, reason = 60, "Possible title or author match"
    description = next(
        (
            _plain_text(_text(item.get(field)))
            for field in ("synopsis", "synopsys", "overview", "excerpt")
            if _text(item.get(field))
        ),
        "",
    )
    return DirectCoverResult(
        title=title,
        author=", ".join(authors),
        isbn=isbn,
        publisher=_text(item.get("publisher")),
        language=_text(item.get("language")),
        published_date=_text(item.get("date_published")),
        cover_url=cover_url,
        source_url=(
            f"https://isbndb.com/book/{quote(isbn, safe='')}" if isbn else ""
        ),
        provider_name="ISBNdb",
        confidence=confidence,
        confidence_reason=reason,
        description=description,
    )


def _map_google_book(
    item: Any,
    *,
    wanted_title: str,
    wanted_author: str,
    wanted_isbn: str,
) -> DirectCoverResult | None:
    if not isinstance(item, dict):
        return None
    info = item.get("volumeInfo")
    if not isinstance(info, dict):
        return None
    title, title_series, title_number = split_title_series(
        _text(info.get("title"))
    )
    images = info.get("imageLinks")
    if not title or not isinstance(images, dict):
        return None
    cover_url = next(
        (
            _secure_url(_text(images.get(size)))
            for size in (
                "extraLarge",
                "large",
                "medium",
                "small",
                "thumbnail",
                "smallThumbnail",
            )
            if _text(images.get(size))
        ),
        "",
    )
    if not cover_url:
        return None
    series, series_number = google_series_details(
        info.get("seriesInfo"),
        title_series=title_series,
        title_number=title_number,
    )
    authors = _texts(info.get("authors"))
    identifiers = info.get("industryIdentifiers")
    isbn = _google_isbn(identifiers)
    exact_isbn = bool(
        wanted_isbn.strip()
        and _isbn_key(wanted_isbn) == _isbn_key(isbn)
    )
    exact_title = bool(
        _normalise(wanted_title)
        and _normalise(wanted_title) == _normalise(title)
    )
    author_match = any(
        _same_author(wanted_author, value) for value in authors
    )
    if exact_isbn:
        confidence, reason = 100, "Exact ISBN match"
    elif exact_title and author_match:
        confidence, reason = 90, "Exact title and author match"
    elif exact_title:
        confidence, reason = 75, "Exact title match"
    else:
        confidence, reason = 60, "Possible title or author match"
    return DirectCoverResult(
        title=title,
        author=", ".join(authors),
        isbn=isbn,
        publisher=_text(info.get("publisher")),
        language=_text(info.get("language")),
        published_date=_text(info.get("publishedDate")),
        cover_url=cover_url,
        source_url=(
            _secure_url(_text(info.get("canonicalVolumeLink")))
            or _secure_url(_text(info.get("infoLink")))
        ),
        provider_name="Google Books",
        confidence=confidence,
        confidence_reason=reason,
        description=_plain_text(_text(info.get("description"))),
        series=series,
        series_number=series_number,
        provider_rating=_provider_rating(info.get("averageRating")),
        rating_count=_rating_count(info.get("ratingsCount")),
    )


def _google_australian_result_order(item: Any) -> int:
    """Prefer Australian Google editions without discarding global results."""
    if not isinstance(item, dict):
        return 1
    for section_name in ("saleInfo", "accessInfo"):
        section = item.get(section_name)
        if (
            isinstance(section, dict)
            and _text(section.get("country")).casefold() == "au"
        ):
            return 0
    return 1


def _google_isbn(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    candidates: dict[str, str] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        identifier_type = _text(item.get("type"))
        identifier = _text(item.get("identifier"))
        if identifier:
            candidates[identifier_type] = identifier
    return candidates.get("ISBN_13") or candidates.get("ISBN_10") or ""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _provider_rating(value: Any) -> float:
    """Return a provider's valid zero-to-five rating, or zero when absent."""
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(rating, 2) if 0.0 < rating <= 5.0 else 0.0


def _rating_count(value: Any) -> int:
    """Return a non-negative provider rating count."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, count)


def _plain_text(value: str) -> str:
    return " ".join(
        html.unescape(re.sub(r"<[^>]+>", " ", value)).split()
    )


def _texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def _secure_url(value: str) -> str:
    if value.startswith("http://"):
        return "https://" + value.removeprefix("http://")
    return value if value.startswith("https://") else ""


def _apple_artwork_url(value: str) -> str:
    secure = _secure_url(value)
    if not secure:
        return ""
    return re.sub(
        r"/\d+x\d+(?:bb|-\d+)?\.",
        "/600x600bb.",
        secure,
    )


def _normalise(value: str) -> str:
    return " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in value.casefold()
        ).split()
    )


def _same_author(wanted: str, actual: str) -> bool:
    wanted_tokens = set(_normalise(wanted).split())
    actual_tokens = set(_normalise(actual).split())
    return bool(wanted_tokens) and wanted_tokens == actual_tokens


def _related_title(wanted: str, actual: str) -> bool:
    wanted_tokens = tuple(_normalise(wanted).split())
    actual_tokens = set(_normalise(actual).split())
    return bool(wanted_tokens) and all(token in actual_tokens for token in wanted_tokens)


def _isbn_key(value: str) -> str:
    return "".join(
        character for character in value.casefold()
        if character.isdigit() or character == "x"
    )

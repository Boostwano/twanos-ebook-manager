"""Conservative Open Library metadata enrichment."""

import json
import logging
import re
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core.metadata import normalise_isbn
from metadata.models import MetadataResult
from metadata.provider import MetadataProvider


logger = logging.getLogger(__name__)
OPEN_LIBRARY_BASE_URL = "https://openlibrary.org"
USER_AGENT = "Twanos-eBook-Manager/10 (metadata enrichment)"
REQUEST_TIMEOUT_SECONDS = 10.0
HttpGet = Callable[[str, dict[str, str], float], bytes]

# Calibre prepends the series index to a book's title (e.g. "22 The
# Mystery of the Dead Mans Riddle"), which breaks exact title matching
# against Open Library. This pattern strips a leading series-index
# number so we can also try matching without it.
_SERIES_PREFIX_RE = re.compile(r"^\d{1,4}[.\s]+")


def _default_http_get(
    url: str,
    headers: dict[str, str],
    timeout: float,
) -> bytes:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise HTTPError(
                url,
                response.status,
                "Non-success response",
                response.headers,
                None,
            )
        return response.read()


class OpenLibraryProvider(MetadataProvider):
    """Enrich local values through Open Library's Search API."""

    def __init__(
        self,
        *,
        http_get: HttpGet = _default_http_get,
        base_url: str = OPEN_LIBRARY_BASE_URL,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        enabled: bool = True,
    ) -> None:
        self._http_get = http_get
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._enabled = enabled
        self._cache: dict[tuple[str, ...], MetadataResult | None] = {}

    @property
    def name(self) -> str:
        return "open_library"

    def supports(self, file_path: str | Path) -> bool:
        return self._enabled

    def extract(self, file_path: str | Path) -> MetadataResult:
        """Look up a filename-derived title when called without context."""
        title = Path(file_path).stem
        return self._lookup(title=title) or MetadataResult(
            extraction_status="unavailable",
            provider_name=self.name,
        )

    def enrich(
        self,
        file_path: str | Path,
        current: MetadataResult | None,
    ) -> MetadataResult | None:
        """Prefer ISBN, then conservatively fall back to title/author."""
        if not self._enabled:
            return None

        isbn = _valid_isbn(current.isbn if current else None)
        if isbn:
            result = self._lookup(isbn=isbn)
            if result is not None:
                return result

        title = current.title if current and current.title else Path(file_path).stem
        author = current.author if current else None
        return self._lookup(title=title, author=author)

    def _lookup(
        self,
        *,
        isbn: str | None = None,
        title: str | None = None,
        author: str | None = None,
    ) -> MetadataResult | None:
        query = (
            ("isbn", isbn)
            if isbn
            else ("title", title or "", "author", author or "")
        )
        cache_key = tuple(str(value) for value in query)
        if cache_key in self._cache:
            return self._cache[cache_key]

        parameters = {"isbn": isbn} if isbn else {"title": title or ""}
        if not isbn and author:
            parameters["author"] = author
        parameters["fields"] = (
            "title,author_name,isbn,publisher,language,"
            "first_publish_date,publish_date"
        )
        parameters["limit"] = "10"
        url = f"{self._base_url}/search.json?{urlencode(parameters)}"

        try:
            payload = self._http_get(
                url,
                {"User-Agent": USER_AGENT, "Accept": "application/json"},
                self._timeout,
            )
            data = json.loads(payload)
            documents = data.get("docs") if isinstance(data, dict) else None
            result = self._select_result(
                documents if isinstance(documents, list) else [],
                isbn=isbn,
                title=title,
                author=author,
            )
        except (
            HTTPError,
            URLError,
            TimeoutError,
            socket.timeout,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
            TypeError,
            ValueError,
        ) as error:
            logger.warning("Open Library lookup failed: %s", error)
            result = None

        self._cache[cache_key] = result
        return result

    def _select_result(
        self,
        documents: list[Any],
        *,
        isbn: str | None,
        title: str | None,
        author: str | None,
    ) -> MetadataResult | None:
        for document in documents:
            if not isinstance(document, dict):
                continue
            confidence = self._confidence(
                document,
                isbn=isbn,
                title=title,
                author=author,
            )
            if confidence:
                return self._map_document(
                    document,
                    confidence,
                    queried_isbn=isbn,
                )
        return None

    @staticmethod
    def _confidence(
        document: dict[str, Any],
        *,
        isbn: str | None,
        title: str | None,
        author: str | None,
    ) -> float:
        """Score exact ISBN 1.0, title+author .85, reliable title-only .70."""
        document_isbns = {
            value
            for raw in _strings(document.get("isbn"))
            if (value := _valid_isbn(raw))
        }
        if isbn:
            return 1.0 if isbn in document_isbns else 0.0

        wanted_titles = _title_candidates(title)
        actual_title = _normalise_text(_first_string(document.get("title")))
        if not wanted_titles or actual_title not in wanted_titles:
            return 0.0

        wanted_author = _normalise_text(author)
        actual_authors = {
            _normalise_text(value)
            for value in _strings(document.get("author_name"))
        }
        if wanted_author:
            return 0.85 if wanted_author in actual_authors else 0.0

        # Title-only matches are accepted only for distinctive titles.
        return 0.70 if len(actual_title) >= 8 else 0.0

    def _map_document(
        self,
        document: dict[str, Any],
        confidence: float,
        *,
        queried_isbn: str | None = None,
    ) -> MetadataResult:
        return MetadataResult(
            title=_first_string(document.get("title")),
            author=", ".join(_strings(document.get("author_name"))) or None,
            # Prefer the ISBN we actually searched for over the first ISBN
            # in Open Library's aggregated per-work list, which may belong
            # to a different edition (different publisher/date/cover) than
            # the one the caller asked about.
            isbn=queried_isbn or _first_valid_isbn(document.get("isbn")),
            publisher=_first_string(document.get("publisher")),
            language=_first_string(document.get("language")),
            published_date=(
                _first_string(document.get("first_publish_date"))
                or _first_string(document.get("publish_date"))
            ),
            extraction_status="external",
            confidence=confidence,
            provider_name=self.name,
        )


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [
            item.strip()
            for item in value
            if isinstance(item, str) and item.strip()
        ]
    return []


def _first_string(value: Any) -> str | None:
    values = _strings(value)
    return values[0] if values else None


def _first_valid_isbn(value: Any) -> str | None:
    for raw in _strings(value):
        if isbn := _valid_isbn(raw):
            return isbn
    return None


def _valid_isbn(value: str | None) -> str | None:
    """Return a normalised ISBN only when its check digit is valid."""
    isbn = normalise_isbn(value)
    if isbn is None:
        return None
    if len(isbn) == 10:
        total = sum(
            (10 - index) * (10 if character == "X" else int(character))
            for index, character in enumerate(isbn)
        )
        return isbn if total % 11 == 0 else None
    total = sum(
        int(character) * (1 if index % 2 == 0 else 3)
        for index, character in enumerate(isbn)
    )
    return isbn if total % 10 == 0 else None


def _normalise_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(
        re.sub(r"[^\w\s]", " ", value.casefold()).split()
    )


def _title_candidates(title: str | None) -> list[str]:
    """Normalised title variants to try matching against.

    Calibre prepends the series index to the title (e.g. "22 The Mystery
    of the Dead Mans Riddle"), so we also try the title with a leading
    series-index number stripped. Both variants are tried so real titles
    that legitimately start with a number (e.g. "1984") still match.
    """
    if not title:
        return []
    candidates = [_normalise_text(title)]
    stripped = _SERIES_PREFIX_RE.sub("", title, count=1)
    if stripped != title:
        stripped_normalised = _normalise_text(stripped)
        if stripped_normalised and stripped_normalised not in candidates:
            candidates.append(stripped_normalised)
    return candidates
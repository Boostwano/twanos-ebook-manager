"""Standalone metadata providers adapted for Twano's simple review flow."""

from __future__ import annotations

import html
import json
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from services.series_metadata import split_title_series


HARDCOVER_API_URL = "https://api.hardcover.app/v1/graphql"
COMIC_VINE_SEARCH_URL = "https://comicvine.gamespot.com/api/search/"
COMIC_VINE_ISSUES_URL = "https://comicvine.gamespot.com/api/issues/"
GUTENDEX_SEARCH_URL = "https://gutendex.com/books"
HARVARD_LIBRARYCLOUD_URL = "https://api.lib.harvard.edu/v2/items.dc.json"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"
BIG_BOOK_API_URL = "https://api.bigbookapi.com"
OPENWEB_NINJA_BOOKS_URL = (
    "https://api.openwebninja.com/realtime-books-data/search"
)
GOODREADS_SEARCH_URL = "https://www.goodreads.com/search"
GOODREADS_BASE_URL = "https://www.goodreads.com"
GOODREADS_MAX_DETAIL_FETCHES = 3
AMAZON_BOOK_SEARCH_URL = "https://www.amazon.com/s"
AMAZON_BOOK_MARKETPLACES = (
    ("AU", "https://www.amazon.com.au/s", "https://www.amazon.com.au"),
    ("US", "https://www.amazon.com/s", "https://www.amazon.com"),
    ("UK", "https://www.amazon.co.uk/s", "https://www.amazon.co.uk"),
    ("CA", "https://www.amazon.ca/s", "https://www.amazon.ca"),
)
PROVIDER_USER_AGENT = (
    "Twanos-eBook-Manager/4 (user-requested metadata lookup)"
)


@dataclass(frozen=True)
class RemoteMetadataResult:
    """Provider-neutral fields used by Metadata Studio."""

    title: str
    author: str = ""
    isbn: str = ""
    publisher: str = ""
    language: str = ""
    published_date: str = ""
    description: str = ""
    series: str = ""
    series_number: str = ""
    series_group: str = ""
    series_group_number: str = ""
    cover_url: str = ""
    source_url: str = ""
    provider_name: str = ""
    confidence: int = 60
    confidence_reason: str = "Possible title match"
    provider_rating: float = 0.0
    rating_count: int = 0


class RemoteProviderError(RuntimeError):
    """Readable provider or credential failure."""

    def __init__(
        self,
        message: str,
        *,
        health_status: str = "unavailable",
        diagnostic: str = "",
    ) -> None:
        super().__init__(message)
        self.health_status = health_status
        self.diagnostic = diagnostic or message


class RemoteMetadataProviderService:
    """Query optional, user-enabled providers without Calibre."""

    def __init__(self, *, timeout: float = 10.0) -> None:
        self.timeout = float(timeout)

    def search_hardcover(
        self,
        *,
        api_key: str,
        title: str = "",
        author: str = "",
        isbn: str = "",
    ) -> tuple[RemoteMetadataResult, ...]:
        query_text = " ".join(
            value.strip() for value in (title, author, isbn) if value.strip()
        )
        if not query_text:
            raise ValueError("Enter a title, author, or ISBN to search.")
        search_payload = self._hardcover_request(
            api_key,
            """
            query TwanoSearch($query: String!) {
              search(query: $query, query_type: "Book", per_page: 12) {
                ids
              }
            }
            """,
            {"query": query_text},
        )
        raw_ids = (
            search_payload.get("search", {}).get("ids", ())
            if isinstance(search_payload.get("search"), dict)
            else ()
        ) or ()
        ids = [
            int(value)
            for value in raw_ids
            if str(value).strip().isdigit()
        ][:12]
        if not ids:
            return ()
        payload = self._hardcover_request(
            api_key,
            """
            query TwanoBooks($ids: [Int!]) {
              books(where: {id: {_in: $ids}}) {
                id
                title
                slug
                description
                cached_featured_series
                editions(
                  where: {reading_format_id: {_in: [1, 4]}}
                  order_by: {users_count: desc_nulls_last}
                  limit: 4
                ) {
                  title
                  isbn_13
                  isbn_10
                  cached_contributors
                  cached_image
                  release_date
                  language { code3 }
                  publisher { name }
                  users_count
                }
              }
            }
            """,
            {"ids": ids},
        )
        books = payload.get("books", ())
        if not isinstance(books, list):
            return ()
        results = [
            result
            for item in books
            if isinstance(item, dict)
            if (
                result := _map_hardcover_book(
                    item,
                    wanted_title=title,
                    wanted_author=author,
                    wanted_isbn=isbn,
                )
            )
        ]
        return tuple(sorted(results, key=lambda item: item.confidence, reverse=True))

    def search_comic_vine(
        self,
        *,
        api_key: str,
        title: str = "",
        author: str = "",
        isbn: str = "",
        issue_number: str = "",
        publisher: str = "",
    ) -> tuple[RemoteMetadataResult, ...]:
        del isbn
        query_text = " ".join(
            value.strip() for value in (title, author) if value.strip()
        )
        if not query_text:
            raise ValueError("Enter a comic title to search.")
        url = f"{COMIC_VINE_SEARCH_URL}?{urlencode({
            'api_key': api_key.strip(),
            'format': 'json',
            'resources': 'volume',
            'query': query_text,
            'limit': '12',
            'field_list': (
                'id,name,publisher,start_year,image,site_detail_url,'
                'description,deck'
            ),
        })}"
        request = Request(
            url,
            headers={
                "User-Agent": PROVIDER_USER_AGENT,
                "Accept": "application/json",
            },
        )
        payload = self._read_json(
            request,
            provider_name="Comic Vine",
            invalid_key_statuses={401, 403},
        )
        status_code = int(payload.get("status_code", 1) or 1)
        if status_code != 1:
            message = _text(payload.get("error"))
            raise RemoteProviderError(
                "Comic Vine rejected the API key or request."
                + (f" {message}" if message and message != "OK" else "")
            )
        raw_results = payload.get("results", ())
        if not isinstance(raw_results, list):
            return ()
        if issue_number.strip():
            issue_results: list[RemoteMetadataResult] = []
            volumes = _comic_vine_volume_candidates(
                raw_results,
                wanted_title=title,
                wanted_publisher=publisher,
            )
            for volume in volumes[:6]:
                volume_id = _text(volume.get("id"))
                if not volume_id:
                    continue
                issue_url = f"{COMIC_VINE_ISSUES_URL}?{urlencode({
                    'api_key': api_key.strip(),
                    'format': 'json',
                    'filter': (
                        f'volume:{volume_id},'
                        f'issue_number:{_normalise_issue_number(issue_number)}'
                    ),
                    'limit': '10',
                    'field_list': (
                        'id,name,issue_number,volume,image,site_detail_url,'
                        'description,deck,cover_date,store_date,person_credits'
                    ),
                })}"
                issue_payload = self._read_json(
                    Request(
                        issue_url,
                        headers={
                            "User-Agent": PROVIDER_USER_AGENT,
                            "Accept": "application/json",
                        },
                    ),
                    provider_name="Comic Vine",
                    invalid_key_statuses={401, 403},
                )
                issue_status = int(
                    issue_payload.get("status_code", 1) or 1
                )
                if issue_status != 1:
                    message = _text(issue_payload.get("error"))
                    raise RemoteProviderError(
                        "Comic Vine rejected the API key or request."
                        + (
                            f" {message}"
                            if message and message != "OK"
                            else ""
                        )
                    )
                issues = issue_payload.get("results", ())
                if not isinstance(issues, list):
                    continue
                issue_results.extend(
                    result
                    for item in issues
                    if isinstance(item, dict)
                    if (
                        result := _map_comic_vine_issue(
                            item,
                            volume=volume,
                            wanted_title=title,
                            wanted_issue_number=issue_number,
                            wanted_publisher=publisher,
                        )
                    )
                )
            return tuple(
                sorted(
                    issue_results,
                    key=lambda item: item.confidence,
                    reverse=True,
                )
            )
        results = [
            result
            for item in raw_results
            if isinstance(item, dict)
            if (
                result := _map_comic_vine_volume(
                    item,
                    wanted_title=title,
                )
            )
        ]
        return tuple(sorted(results, key=lambda item: item.confidence, reverse=True))

    def search_amazon(
        self,
        *,
        title: str = "",
        author: str = "",
        isbn: str = "",
    ) -> tuple[RemoteMetadataResult, ...]:
        """Search English Amazon marketplaces without a user API key."""
        query_text = _query_text(title=title, author=author, isbn=isbn)
        results: list[RemoteMetadataResult] = []
        failures: list[RemoteProviderError] = []
        completed_marketplace = False
        for marketplace, search_url, base_url in _amazon_marketplaces():
            provider_name = f"Amazon {marketplace}"
            request = Request(
                f"{search_url}?{urlencode({
                    'k': query_text,
                    'i': 'stripbooks',
                })}",
                headers=_public_web_headers(),
            )
            try:
                page = self._read_public_page(
                    request,
                    provider_name=provider_name,
                )
                if _looks_blocked(page):
                    raise RemoteProviderError(
                        f"{provider_name} has blocked automated catalogue "
                        "access for now.",
                        health_status="blocked",
                        diagnostic=(
                            f"{provider_name} returned a robot, CAPTCHA, or "
                            "automated-access page."
                        ),
                    )
                blocks = re.findall(
                    r'(<div[^>]+data-component-type=["\']s-search-result'
                    r'["\'][\s\S]*?)(?=<div[^>]+data-component-type='
                    r'["\']s-search-result["\']|$)',
                    page,
                    flags=re.IGNORECASE,
                )
                if not blocks:
                    if _amazon_no_results(page):
                        completed_marketplace = True
                        continue
                    raise RemoteProviderError(
                        f"{provider_name}'s book-results page has changed. "
                        "This provider needs an application update before it "
                        "can safely use the page.",
                        health_status="layout_changed",
                        diagnostic=(
                            f"Expected {provider_name} s-search-result cards "
                            "were absent from a successful response."
                        ),
                    )
                completed_marketplace = True
                results.extend(
                    result
                    for block in blocks[:20]
                    if (
                        result := _map_amazon_result(
                            block,
                            wanted_title=title,
                            wanted_author=author,
                            wanted_isbn=isbn,
                            marketplace=marketplace,
                            base_url=base_url,
                        )
                    )
                )
            except RemoteProviderError as error:
                failures.append(error)

        unique: dict[tuple[str, str, str, str, str, str], RemoteMetadataResult] = {}
        for result in sorted(
            results,
            key=lambda item: item.confidence,
            reverse=True,
        ):
            key = (
                _normalise(result.title),
                _normalise(result.author),
                result.isbn.casefold(),
                result.cover_url,
                _normalise(result.series),
                result.series_number.casefold(),
            )
            unique.setdefault(key, result)
        if unique or completed_marketplace:
            return tuple(unique.values())
        if failures:
            raise failures[0]
        return ()

    def search_goodreads(
        self,
        *,
        title: str = "",
        author: str = "",
        isbn: str = "",
    ) -> tuple[RemoteMetadataResult, ...]:
        """Search Goodreads' public book pages for structured series data.

        Goodreads retired its public API years ago; this reads the same
        publicly served pages a browser would, the same way this service
        already reads Amazon's public listings above. Unlike a raw web
        search, Goodreads' own book page embeds its series name and
        position as a structured field, not prose to guess at -- that is
        the whole reason to prefer this source for series accuracy.

        Automated access is against Goodreads' Terms of Service. This
        provider must be turned on knowingly in Plugins; it is never
        enabled by default, and its description says so.
        """
        query_text = _query_text(title=title, author=author, isbn=isbn)
        search_request = Request(
            f"{GOODREADS_SEARCH_URL}?{urlencode({'q': query_text})}",
            headers=_public_web_headers(),
        )
        search_page = self._read_public_page(
            search_request, provider_name="Goodreads"
        )
        if _looks_blocked(search_page):
            raise RemoteProviderError(
                "Goodreads has blocked automated catalogue access for now.",
                health_status="blocked",
                diagnostic=(
                    "Goodreads returned a robot, CAPTCHA, or "
                    "automated-access page for the search request."
                ),
            )
        candidates = _goodreads_search_candidates(
            search_page,
            wanted_title=title,
            wanted_author=author,
        )
        if not candidates:
            return ()

        def fetch(book_url: str) -> RemoteMetadataResult | None:
            request = Request(book_url, headers=_public_web_headers())
            page = self._read_public_page(
                request, provider_name="Goodreads"
            )
            if _looks_blocked(page):
                raise RemoteProviderError(
                    "Goodreads has blocked automated catalogue access "
                    "for now.",
                    health_status="blocked",
                    diagnostic=(
                        "Goodreads returned a robot, CAPTCHA, or "
                        "automated-access page for a book page."
                    ),
                )
            return _map_goodreads_book(
                page,
                source_url=book_url,
                wanted_title=title,
                wanted_author=author,
                wanted_isbn=isbn,
            )

        urls = candidates[:GOODREADS_MAX_DETAIL_FETCHES]
        results: list[RemoteMetadataResult] = []
        blocked: RemoteProviderError | None = None
        with ThreadPoolExecutor(
            max_workers=len(urls),
            thread_name_prefix="twano-goodreads",
        ) as executor:
            futures = [executor.submit(fetch, url) for url in urls]
            for future in futures:
                try:
                    result = future.result()
                except RemoteProviderError as error:
                    blocked = error
                    continue
                if result is not None:
                    results.append(result)
        if not results and blocked is not None:
            raise blocked
        return tuple(results)

    def search_gutenberg(
        self,
        *,
        title: str = "",
        author: str = "",
        isbn: str = "",
    ) -> tuple[RemoteMetadataResult, ...]:
        """Search public-domain Project Gutenberg records through Gutendex."""
        query_text = _query_text(title=title, author=author, isbn=isbn)
        request = _json_get_request(
            GUTENDEX_SEARCH_URL,
            {"search": query_text},
        )
        payload = self._read_json(
            request,
            provider_name="Project Gutenberg",
            invalid_key_statuses=set(),
        )
        items = payload.get("results", ())
        if not isinstance(items, list):
            return ()
        return tuple(
            result
            for item in items[:12]
            if isinstance(item, dict)
            if (
                result := _map_gutenberg_book(
                    item,
                    wanted_title=title,
                    wanted_author=author,
                    wanted_isbn=isbn,
                )
            )
        )

    def search_harvard_librarycloud(
        self,
        *,
        title: str = "",
        author: str = "",
        isbn: str = "",
    ) -> tuple[RemoteMetadataResult, ...]:
        """Search Harvard's open LibraryCloud bibliographic catalogue."""
        parameters: dict[str, object] = {"limit": 12}
        if isbn.strip():
            parameters["identifier"] = isbn.strip()
        else:
            if title.strip():
                parameters["title"] = title.strip()
            if author.strip():
                parameters["name"] = author.strip()
        if len(parameters) == 1:
            raise ValueError("Enter a title, author, or ISBN to search.")
        request = _json_get_request(HARVARD_LIBRARYCLOUD_URL, parameters)
        payload = self._read_json(
            request,
            provider_name="Harvard LibraryCloud",
            invalid_key_statuses=set(),
        )
        items = _record_list(payload)
        return tuple(
            result
            for item in items[:12]
            if (
                result := _map_harvard_record(
                    item,
                    wanted_title=title,
                    wanted_author=author,
                    wanted_isbn=isbn,
                )
            )
        )

    def search_crossref(
        self,
        *,
        title: str = "",
        author: str = "",
        isbn: str = "",
    ) -> tuple[RemoteMetadataResult, ...]:
        """Search DOI-registered books and chapters through Crossref."""
        query_text = _query_text(title=title, author=author, isbn=isbn)
        request = _json_get_request(
            CROSSREF_WORKS_URL,
            {
                "query.bibliographic": query_text,
                "rows": 12,
            },
        )
        payload = self._read_json(
            request,
            provider_name="Crossref",
            invalid_key_statuses=set(),
        )
        message = payload.get("message")
        items = message.get("items", ()) if isinstance(message, dict) else ()
        if not isinstance(items, list):
            return ()
        supported_types = {
            "book",
            "book-chapter",
            "book-part",
            "book-section",
            "edited-book",
            "monograph",
            "reference-book",
        }
        return tuple(
            result
            for item in items
            if isinstance(item, dict)
            if _text(item.get("type")).casefold() in supported_types
            if (
                result := _map_crossref_work(
                    item,
                    wanted_title=title,
                    wanted_author=author,
                    wanted_isbn=isbn,
                )
            )
        )

    def search_big_book(
        self,
        *,
        api_key: str,
        title: str = "",
        author: str = "",
        isbn: str = "",
    ) -> tuple[RemoteMetadataResult, ...]:
        """Search Big Book API while conserving its small free daily quota."""
        token = api_key.strip()
        if not token:
            raise RemoteProviderError(
                "Big Book API needs an API key. Configure it on Plugins."
            )
        query_text = _query_text(title=title, author=author, isbn=isbn)
        request = _json_get_request(
            f"{BIG_BOOK_API_URL}/search-books",
            {"query": query_text, "number": 5},
            api_key=token,
        )
        payload = self._read_json(
            request,
            provider_name="Big Book API",
            invalid_key_statuses={401, 403},
            quota_statuses={402, 429},
        )
        summary_items = _flatten_dicts(payload.get("books"))
        results: list[RemoteMetadataResult] = []
        # One search plus at most three detail calls keeps the free plan useful.
        for summary in summary_items[:3]:
            identifier = _text(summary.get("id"))
            detail = summary
            if identifier:
                detail_request = _json_get_request(
                    f"{BIG_BOOK_API_URL}/{identifier}",
                    {},
                    api_key=token,
                )
                detail = self._read_json(
                    detail_request,
                    provider_name="Big Book API",
                    invalid_key_statuses={401, 403},
                    quota_statuses={402, 429},
                )
            result = _map_big_book(
                detail,
                fallback=summary,
                wanted_title=title,
                wanted_author=author,
                wanted_isbn=isbn,
            )
            if result is not None:
                results.append(result)
        return tuple(results)

    def search_openweb_ninja(
        self,
        *,
        api_key: str,
        title: str = "",
        author: str = "",
        isbn: str = "",
    ) -> tuple[RemoteMetadataResult, ...]:
        """Search OpenWeb Ninja's quota-limited Google Books proxy."""
        token = api_key.strip()
        if not token:
            raise RemoteProviderError(
                "OpenWeb Ninja needs an API key. Configure it on Plugins."
            )
        query_text = _query_text(title=title, author=author, isbn=isbn)
        request = _json_get_request(
            OPENWEB_NINJA_BOOKS_URL,
            {"query": query_text},
            api_key=token,
        )
        payload = self._read_json(
            request,
            provider_name="OpenWeb Ninja",
            invalid_key_statuses={401, 403},
            quota_statuses={402, 429},
        )
        items = _record_list(payload)
        return tuple(
            result
            for item in items[:12]
            if (
                result := _map_openweb_book(
                    item,
                    wanted_title=title,
                    wanted_author=author,
                    wanted_isbn=isbn,
                )
            )
        )

    def search_booktopia(self, *, title: str = "", author: str = "", isbn: str = "") -> tuple[RemoteMetadataResult, ...]:
        return self._search_structured_book_site(
            provider_name="Booktopia",
            search_url="https://www.booktopia.com.au/search.ep?" + urlencode({"keywords": _query_text(title=title, author=author, isbn=isbn)}),
            title=title, author=author, isbn=isbn,
        )

    def _search_structured_book_site(
        self, *, provider_name: str, search_url: str, title: str, author: str, isbn: str
    ) -> tuple[RemoteMetadataResult, ...]:
        page = self._read_public_page(
            Request(search_url, headers=_public_web_headers()), provider_name=provider_name
        )
        return _structured_book_results(
            page, provider_name=provider_name, page_url=search_url,
            wanted_title=title, wanted_author=author, wanted_isbn=isbn,
        )

    def _hardcover_request(
        self,
        api_key: str,
        query: str,
        variables: dict[str, object],
    ) -> dict[str, Any]:
        token = api_key.strip()
        if not token:
            raise RemoteProviderError(
                "Hardcover needs an API token. Configure it on Plugins."
            )
        authorization = token if token.lower().startswith("bearer ") else (
            f"Bearer {token}"
        )
        request = Request(
            HARDCOVER_API_URL,
            data=json.dumps(
                {"query": query, "variables": variables}
            ).encode("utf-8"),
            headers={
                "User-Agent": PROVIDER_USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": authorization,
            },
            method="POST",
        )
        payload = self._read_json(
            request,
            provider_name="Hardcover",
            invalid_key_statuses={401, 403},
        )
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0] if isinstance(errors[0], dict) else {}
            message = _text(first.get("message"))
            raise RemoteProviderError(
                "Hardcover could not complete the search."
                + (f" {message}" if message else "")
            )
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def _read_public_page(
        self,
        request: Request,
        *,
        provider_name: str,
    ) -> str:
        """Read a public provider page while preserving failure categories."""
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(4 * 1024 * 1024)
                encoding = response.headers.get_content_charset() or "utf-8"
        except HTTPError as error:
            if error.code in {401, 403, 429, 503}:
                raise RemoteProviderError(
                    f"{provider_name} has blocked or limited automated access "
                    "for now.",
                    health_status="blocked",
                    diagnostic=f"{provider_name} returned HTTP {error.code}.",
                ) from error
            raise RemoteProviderError(
                f"{provider_name} could not complete the search.",
                diagnostic=f"{provider_name} returned HTTP {error.code}.",
            ) from error
        except (URLError, TimeoutError, socket.timeout, OSError) as error:
            raise RemoteProviderError(
                f"{provider_name} could not be reached. Check the internet "
                "connection and try again.",
                diagnostic=f"{provider_name} connection failed: {type(error).__name__}.",
            ) from error
        try:
            return raw.decode(encoding, errors="replace")
        except LookupError:
            return raw.decode("utf-8", errors="replace")

    def _read_json(
        self,
        request: Request,
        *,
        provider_name: str,
        invalid_key_statuses: set[int],
        quota_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    raise RemoteProviderError(
                        f"{provider_name} did not accept the search."
                    )
                payload = json.loads(response.read())
        except HTTPError as error:
            if error.code in invalid_key_statuses:
                raise RemoteProviderError(
                    f"{provider_name} rejected the saved API key. Open "
                    "Plugins and configure it again."
                ) from error
            if error.code in (quota_statuses or set()):
                raise RemoteProviderError(
                    f"{provider_name} has reached the saved key's free-plan "
                    "or subscription quota. Try again after it resets."
                ) from error
            raise RemoteProviderError(
                f"{provider_name} could not complete the search."
            ) from error
        except (
            URLError,
            TimeoutError,
            socket.timeout,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
        ) as error:
            raise RemoteProviderError(
                f"{provider_name} could not be reached. Check the internet "
                "connection and try again."
            ) from error
        if not isinstance(payload, dict):
            raise RemoteProviderError(
                f"{provider_name} returned an unreadable response."
            )
        return payload


def _json_get_request(
    base_url: str,
    parameters: dict[str, object],
    *,
    api_key: str = "",
) -> Request:
    url = base_url
    if parameters:
        url = f"{base_url}?{urlencode(parameters)}"
    headers = {
        "User-Agent": PROVIDER_USER_AGENT,
        "Accept": "application/json",
    }
    if api_key:
        headers["x-api-key"] = api_key
    return Request(url, headers=headers)


def _public_web_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36 "
            "Twanos-eBook-Manager/4"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-AU,en;q=0.8",
    }


def _looks_blocked(page: str) -> bool:
    lowered = page.casefold()
    markers = (
        "captcha",
        "robot check",
        "not a robot",
        "unusual traffic",
        "automated access",
        "validatecaptcha",
        "sorry, we just need to make sure",
        "enter the characters you see below",
        "access denied",
    )
    return any(marker in lowered for marker in markers)


def _amazon_no_results(page: str) -> bool:
    lowered = _plain_text(page).casefold()
    return (
        "no results for" in lowered
        or "try checking your spelling" in lowered
        or "need help?" in lowered and "search" in lowered
    )


def _map_amazon_result(
    block: str,
    *,
    wanted_title: str,
    wanted_author: str,
    wanted_isbn: str,
    marketplace: str = "US",
    base_url: str = "https://www.amazon.com",
) -> RemoteMetadataResult | None:
    title_link = _amazon_title_link(block)
    image_match = re.search(
        r"<img\b[^>]*class=[\"'][^\"']*\bs-image\b[^\"']*[\"'][^>]*"
        r"src=[\"']([^\"']+)[\"']",
        block,
        flags=re.IGNORECASE,
    )
    if image_match is None:
        image_match = re.search(
            r"<img\b[^>]*src=[\"']([^\"']+)[\"'][^>]*class=[\"']"
            r"[^\"']*\bs-image\b",
            block,
            flags=re.IGNORECASE,
        )
    if title_link is None or image_match is None:
        return None
    href, raw_title = title_link
    title, series, series_number = split_title_series(
        raw_title
    )
    series_match = re.search(
        r"\bBook\s+(\d+(?:\.\d+)?)\s+of\s+\d+\s*:\s*([^<|]+)",
        block,
        flags=re.IGNORECASE,
    )
    if series_match is not None and not series:
        parenthetical = re.fullmatch(r"(.+?)\s*\(([^()]+)\)\s*", title)
        if parenthetical is not None:
            title = parenthetical.group(1).strip()
            series = parenthetical.group(2).strip()
    if series_match is not None:
        series_number = series_number or _plain_text(series_match.group(1))
        series = series or _plain_text(series_match.group(2))
    cover_url = _amazon_large_image(_secure_url(html.unescape(image_match.group(1))))
    if not title or not cover_url:
        return None
    author_match = re.search(
        r"\bby\s*</span>[\s\S]{0,800}?<a\b[^>]*>([\s\S]*?)</a>",
        block,
        flags=re.IGNORECASE,
    )
    author = _plain_text(author_match.group(1)) if author_match else ""
    confidence, reason = _confidence(
        title=title,
        authors=[author] if author else [],
        isbn="",
        wanted_title=wanted_title,
        wanted_author=wanted_author,
        wanted_isbn=wanted_isbn,
    )
    if confidence < 75 and not (
        _title_is_related(wanted_title, title)
        and _author_is_related(wanted_author, author)
    ):
        return None
    if confidence < 75:
        confidence, reason = 70, "Related title and author match"
    source_url = (
        base_url + href
        if href.startswith("/")
        else _secure_url(href)
    )
    return RemoteMetadataResult(
        title=title,
        author=author,
        cover_url=cover_url,
        source_url=source_url,
        provider_name=f"Amazon {marketplace}",
        confidence=confidence,
        confidence_reason=reason,
        series=series,
        series_number=series_number,
    )


def _amazon_marketplaces() -> tuple[tuple[str, str, str], ...]:
    """Return AU-first marketplaces while respecting an approved URL update."""
    configured = AMAZON_BOOK_SEARCH_URL.rstrip("/")
    marketplaces = list(AMAZON_BOOK_MARKETPLACES)
    configured_host = re.sub(r"^https?://", "", configured).split("/", 1)[0]
    configured_base = f"https://{configured_host}"
    for index, (label, _search_url, base_url) in enumerate(marketplaces):
        if configured_host == re.sub(r"^https?://", "", base_url):
            marketplaces[index] = (label, configured, configured_base)
            break
    return tuple(marketplaces)


def _amazon_title_link(block: str) -> tuple[str, str] | None:
    """Return the product link and title from old or current Amazon cards."""
    current = re.search(
        r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>\s*"
        r"<h2\b([^>]*)>([\s\S]*?)</h2>",
        block,
        flags=re.IGNORECASE,
    )
    if current is not None:
        aria_label = re.search(
            r"\baria-label=[\"']([^\"']+)[\"']",
            current.group(2),
            flags=re.IGNORECASE,
        )
        raw_title = (
            html.unescape(aria_label.group(1))
            if aria_label is not None
            else _plain_text(current.group(3))
        )
        return html.unescape(current.group(1)), raw_title
    legacy = re.search(
        r"<h2\b[^>]*>[\s\S]*?<a\b[^>]*href=[\"']([^\"']+)[\"']"
        r"[^>]*>[\s\S]*?<span\b[^>]*>([\s\S]*?)</span>",
        block,
        flags=re.IGNORECASE,
    )
    if legacy is None:
        return None
    return html.unescape(legacy.group(1)), _plain_text(legacy.group(2))


def _title_is_related(wanted: str, actual: str) -> bool:
    wanted_words = tuple(_normalise(wanted).split())
    actual_words = set(_normalise(actual).split())
    return bool(wanted_words) and all(word in actual_words for word in wanted_words)


def _author_is_related(wanted: str, actual: str) -> bool:
    wanted_words = set(_normalise(wanted).split())
    actual_words = set(_normalise(actual).split())
    return not wanted_words or wanted_words <= actual_words


def _amazon_large_image(url: str) -> str:
    if not url:
        return ""
    return re.sub(r"\._[A-Z0-9_,.-]+_\.(?=[A-Za-z]+(?:\?|$))", ".", url)


_GOODREADS_ROW_SPLIT_RE = re.compile(
    r'(<tr\b[^>]*itemscope[^>]*itemtype=["\']http://schema\.org/Book["\']'
    r'[\s\S]*?)(?=<tr\b[^>]*itemscope[^>]*itemtype=["\']http://schema\.org/'
    r'Book["\']|</table>)',
    re.IGNORECASE,
)
_GOODREADS_TITLE_RE = re.compile(
    r'<a\b[^>]*class=["\']bookTitle["\'][^>]*href=["\']([^"\']+)["\']'
    r'[^>]*>\s*<span[^>]*>([\s\S]*?)</span>',
    re.IGNORECASE,
)
_GOODREADS_AUTHOR_RE = re.compile(
    r'itemprop=["\']author["\'][\s\S]{0,400}?itemprop=["\']name["\']>'
    r'([^<]*)<',
    re.IGNORECASE,
)
_GOODREADS_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>([\s\S]*?)</script>',
    re.IGNORECASE,
)
_GOODREADS_LEGACY_ID_RE = re.compile(r"/show/(\d+)")


def _goodreads_search_candidates(
    page: str,
    *,
    wanted_title: str,
    wanted_author: str,
) -> list[str]:
    """Return plausible book-page URLs from a Goodreads search results page."""
    urls: list[str] = []
    seen: set[str] = set()
    for row in _GOODREADS_ROW_SPLIT_RE.findall(page):
        title_match = _GOODREADS_TITLE_RE.search(row)
        if title_match is None:
            continue
        href = html.unescape(title_match.group(1))
        raw_title = _plain_text(title_match.group(2))
        title, _series, _number = split_title_series(raw_title)
        title = title or raw_title
        author_match = _GOODREADS_AUTHOR_RE.search(row)
        author = (
            html.unescape(author_match.group(1).strip())
            if author_match
            else ""
        )
        if wanted_title and not (
            _title_is_related(wanted_title, title)
            or _normalise(wanted_title) in _normalise(raw_title)
        ):
            continue
        if wanted_author and author and not _author_is_related(
            wanted_author, author
        ):
            continue
        url = (
            GOODREADS_BASE_URL + href if href.startswith("/") else href
        ).split("?", 1)[0]
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _goodreads_apollo_state(page: str) -> dict[str, Any] | None:
    """Return the Next.js Apollo cache embedded in a Goodreads page, if any."""
    match = _GOODREADS_NEXT_DATA_RE.search(page)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    try:
        apollo_state = payload["props"]["pageProps"]["apolloState"]
    except (KeyError, TypeError):
        return None
    return (
        apollo_state
        if isinstance(apollo_state, dict) and apollo_state
        else None
    )


def _goodreads_book_node(
    apollo_state: dict[str, Any],
    *,
    source_url: str,
) -> dict[str, Any] | None:
    """Return this page's own Book node, not an unrelated one on the page.

    The same cache also holds "similar books" nodes. Matching the numeric
    id from the page's own URL against each candidate's ``legacyId`` picks
    the right one deterministically, without depending on the exact
    wording of the root query key.
    """
    id_match = _GOODREADS_LEGACY_ID_RE.search(source_url)
    legacy_id = id_match.group(1) if id_match else ""
    fallback: dict[str, Any] | None = None
    for key, value in apollo_state.items():
        if not (key.startswith("Book:") and isinstance(value, dict)):
            continue
        if "title" not in value:
            continue
        fallback = value
        if legacy_id and str(value.get("legacyId", "")) == legacy_id:
            return value
    return fallback


def _goodreads_ref(
    apollo_state: dict[str, Any],
    node: dict[str, Any] | None,
    *keys: str,
) -> dict[str, Any] | None:
    """Follow a chain of Apollo ``{"__ref": ...}`` normalised-cache pointers."""
    current: Any = node
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if isinstance(current, dict) and "__ref" in current:
        target = apollo_state.get(current["__ref"])
        return target if isinstance(target, dict) else None
    return current if isinstance(current, dict) else None


def _map_goodreads_book(
    page: str,
    *,
    source_url: str,
    wanted_title: str,
    wanted_author: str,
    wanted_isbn: str,
) -> RemoteMetadataResult | None:
    """Build a result from Goodreads' own structured book-page data.

    Unlike a general web search, the series name and position come from
    Goodreads' own explicit fields (``bookSeries[0]``), not prose that has
    to be guessed at -- this is what makes this source reliable for
    series data specifically.
    """
    apollo_state = _goodreads_apollo_state(page)
    if apollo_state is None:
        return None
    book = _goodreads_book_node(apollo_state, source_url=source_url)
    if book is None:
        return None
    title = _text(book.get("title"))

    author = ""
    contributor = _goodreads_ref(
        apollo_state, book, "primaryContributorEdge", "node"
    )
    if contributor is not None:
        author = _text(contributor.get("name"))

    if not title or not author:
        return None

    details = book.get("details")
    details = details if isinstance(details, dict) else {}
    isbn = _text(details.get("isbn13") or details.get("isbn"))
    publisher = _text(details.get("publisher"))
    language_node = details.get("language")
    language = _text(
        language_node.get("name") if isinstance(language_node, dict) else ""
    )
    published_date = ""
    publication_time = details.get("publicationTime")
    if publication_time:
        try:
            published_date = str(
                datetime.fromtimestamp(
                    int(publication_time) / 1000, tz=timezone.utc
                ).date()
            )
        except (TypeError, ValueError, OverflowError, OSError):
            published_date = ""

    series = ""
    series_number = ""
    book_series = book.get("bookSeries")
    if isinstance(book_series, list) and book_series:
        first_series = book_series[0]
        if isinstance(first_series, dict):
            series_node = _goodreads_ref(
                apollo_state, first_series, "series"
            )
            if series_node is not None:
                series = _text(series_node.get("title"))
            series_number = _text(first_series.get("userPosition"))

    description = _plain_text(_text(book.get("description")))
    cover_url = _secure_url(_text(book.get("imageUrl")))

    provider_rating = 0.0
    rating_count = 0
    work = _goodreads_ref(apollo_state, book, "work")
    if work is not None:
        stats = work.get("stats")
        stats = stats if isinstance(stats, dict) else {}
        try:
            provider_rating = round(float(stats.get("averageRating") or 0), 2)
        except (TypeError, ValueError):
            provider_rating = 0.0
        try:
            rating_count = int(stats.get("ratingsCount") or 0)
        except (TypeError, ValueError):
            rating_count = 0

    confidence, reason = _confidence(
        title=title,
        authors=[author],
        isbn=isbn,
        wanted_title=wanted_title,
        wanted_author=wanted_author,
        wanted_isbn=wanted_isbn,
    )
    if confidence < 75 and not (
        _title_is_related(wanted_title, title)
        and _author_is_related(wanted_author, author)
    ):
        return None
    if confidence < 75:
        confidence, reason = 70, "Related title and author match"

    return RemoteMetadataResult(
        title=title,
        author=author,
        isbn=isbn,
        publisher=publisher,
        language=language,
        published_date=published_date,
        description=description,
        series=series,
        series_number=series_number,
        cover_url=cover_url,
        source_url=source_url,
        provider_name="Goodreads",
        confidence=confidence,
        confidence_reason=reason,
        provider_rating=provider_rating,
        rating_count=rating_count,
    )


def _query_text(*, title: str, author: str, isbn: str) -> str:
    value = " ".join(
        part.strip() for part in (isbn, title, author) if part.strip()
    )
    if not value:
        raise ValueError("Enter a title, author, or ISBN to search.")
    return value


def _record_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Find records across the small wrapper variations used by providers."""
    for key in ("items", "records", "results", "books", "docs"):
        value = payload.get(key)
        flattened = _flatten_dicts(value)
        if flattened:
            return flattened
    for value in payload.values():
        if isinstance(value, dict):
            nested = _record_list(value)
            if nested:
                return nested
    return []


def _flatten_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, list):
        return []
    flattened: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            flattened.append(item)
        elif isinstance(item, list):
            flattened.extend(_flatten_dicts(item))
    return flattened


def _map_gutenberg_book(
    item: dict[str, Any],
    *,
    wanted_title: str,
    wanted_author: str,
    wanted_isbn: str,
) -> RemoteMetadataResult | None:
    title = _text(item.get("title"))
    if not title:
        return None
    authors = [
        _text(value.get("name"))
        for value in _flatten_dicts(item.get("authors"))
        if _text(value.get("name"))
    ]
    formats = item.get("formats")
    cover_url = ""
    if isinstance(formats, dict):
        cover_url = _secure_url(_text(formats.get("image/jpeg")))
    summaries = item.get("summaries")
    description = (
        _plain_text(_text(summaries[0]))
        if isinstance(summaries, list) and summaries
        else ""
    )
    languages = item.get("languages")
    language = (
        _text(languages[0])
        if isinstance(languages, list) and languages
        else ""
    )
    confidence, reason = _confidence(
        title=title,
        authors=authors,
        isbn="",
        wanted_title=wanted_title,
        wanted_author=wanted_author,
        wanted_isbn=wanted_isbn,
    )
    gutenberg_id = _text(item.get("id"))
    return RemoteMetadataResult(
        title=title,
        author=", ".join(authors),
        publisher="Project Gutenberg",
        language=language,
        description=description,
        cover_url=cover_url,
        source_url=(
            f"https://www.gutenberg.org/ebooks/{gutenberg_id}"
            if gutenberg_id
            else ""
        ),
        provider_name="Project Gutenberg",
        confidence=confidence,
        confidence_reason=reason,
    )


def _map_harvard_record(
    item: dict[str, Any],
    *,
    wanted_title: str,
    wanted_author: str,
    wanted_isbn: str,
) -> RemoteMetadataResult | None:
    titles = _field_values(item, {"title", "dc:title"})
    title = titles[0] if titles else ""
    if not title:
        return None
    authors = _field_values(
        item,
        {"creator", "dc:creator", "name", "personalname"},
    )
    identifiers = _field_values(item, {"identifier", "dc:identifier", "isbn"})
    isbn = next(
        (
            match.group(0)
            for value in identifiers
            if (
                match := re.search(
                    r"(?<!\d)(?:97[89][\d -]{10,16}|[\dXx][\dXx -]{8,15})",
                    value,
                )
            )
        ),
        "",
    )
    isbn = _isbn_key(isbn)
    confidence, reason = _confidence(
        title=title,
        authors=authors,
        isbn=isbn,
        wanted_title=wanted_title,
        wanted_author=wanted_author,
        wanted_isbn=wanted_isbn,
    )
    source_url = next(
        (
            _secure_url(value)
            for value in identifiers
            if _secure_url(value)
        ),
        "",
    )
    return RemoteMetadataResult(
        title=title,
        author=", ".join(dict.fromkeys(authors[:4])),
        isbn=isbn,
        publisher=_first_field(item, {"publisher", "dc:publisher"}),
        language=_first_field(item, {"language", "dc:language"}),
        published_date=_first_field(
            item,
            {"date", "dc:date", "dateissued", "copyrightdate"},
        ),
        description=_plain_text(
            _first_field(
                item,
                {"description", "dc:description", "abstract", "abstracttoc"},
            )
        ),
        source_url=source_url,
        provider_name="Harvard LibraryCloud",
        confidence=confidence,
        confidence_reason=reason,
    )


def _map_crossref_work(
    item: dict[str, Any],
    *,
    wanted_title: str,
    wanted_author: str,
    wanted_isbn: str,
) -> RemoteMetadataResult | None:
    titles = item.get("title")
    title = (
        _text(titles[0])
        if isinstance(titles, list) and titles
        else _text(titles)
    )
    if not title:
        return None
    authors = []
    for value in _flatten_dicts(item.get("author")):
        name = " ".join(
            part
            for part in (
                _text(value.get("given")),
                _text(value.get("family")),
            )
            if part
        )
        if name:
            authors.append(name)
    identifiers = item.get("ISBN")
    isbn = (
        next((_text(value) for value in identifiers if _text(value)), "")
        if isinstance(identifiers, list)
        else _text(identifiers)
    )
    confidence, reason = _confidence(
        title=title,
        authors=authors,
        isbn=isbn,
        wanted_title=wanted_title,
        wanted_author=wanted_author,
        wanted_isbn=wanted_isbn,
    )
    published_date = _crossref_date(item)
    doi = _text(item.get("DOI"))
    return RemoteMetadataResult(
        title=title,
        author=", ".join(authors),
        isbn=isbn,
        publisher=_text(item.get("publisher")),
        published_date=published_date,
        description=_plain_text(_text(item.get("abstract"))),
        source_url=(
            _secure_url(_text(item.get("URL")))
            or (f"https://doi.org/{doi}" if doi else "")
        ),
        provider_name="Crossref",
        confidence=confidence,
        confidence_reason=reason,
    )


def _map_big_book(
    item: dict[str, Any],
    *,
    fallback: dict[str, Any],
    wanted_title: str,
    wanted_author: str,
    wanted_isbn: str,
) -> RemoteMetadataResult | None:
    title = _text(item.get("title")) or _text(fallback.get("title"))
    if not title:
        return None
    authors = [
        _text(value.get("name"))
        for value in _flatten_dicts(
            item.get("authors") or fallback.get("authors")
        )
        if _text(value.get("name"))
    ]
    identifiers = item.get("identifiers")
    isbn = ""
    if isinstance(identifiers, dict):
        isbn = (
            _text(identifiers.get("isbn_13"))
            or _text(identifiers.get("isbn_10"))
        )
    confidence, reason = _confidence(
        title=title,
        authors=authors,
        isbn=isbn,
        wanted_title=wanted_title,
        wanted_author=wanted_author,
        wanted_isbn=wanted_isbn,
    )
    identifier = _text(item.get("id")) or _text(fallback.get("id"))
    return RemoteMetadataResult(
        title=title,
        author=", ".join(authors),
        isbn=isbn,
        published_date=_text(item.get("publish_date")),
        description=_plain_text(_text(item.get("description"))),
        cover_url=_secure_url(
            _text(item.get("image")) or _text(fallback.get("image"))
        ),
        source_url=(
            f"https://bigbookapi.com/books/{identifier}"
            if identifier
            else ""
        ),
        provider_name="Big Book API",
        confidence=confidence,
        confidence_reason=reason,
    )


def _map_openweb_book(
    item: dict[str, Any],
    *,
    wanted_title: str,
    wanted_author: str,
    wanted_isbn: str,
) -> RemoteMetadataResult | None:
    title = _text(item.get("title"))
    if not title:
        return None
    authors = [
        _text(value.get("name"))
        for value in _flatten_dicts(
            item.get("book_authors") or item.get("authors")
        )
        if _text(value.get("name"))
    ]
    isbn = _text(item.get("isbn_13")) or _text(item.get("isbn"))
    confidence, reason = _confidence(
        title=title,
        authors=authors,
        isbn=isbn,
        wanted_title=wanted_title,
        wanted_author=wanted_author,
        wanted_isbn=wanted_isbn,
    )
    return RemoteMetadataResult(
        title=title,
        author=", ".join(authors),
        isbn=isbn,
        publisher=_text(item.get("publisher")),
        language=_text(item.get("language")),
        published_date=_text(
            item.get("publication_year") or item.get("published_date")
        ),
        description=_plain_text(_text(item.get("description"))),
        cover_url=_secure_url(
            _text(item.get("image_url")) or _text(item.get("image"))
        ),
        source_url=_secure_url(
            _text(item.get("view_url")) or _text(item.get("url"))
        ),
        provider_name="OpenWeb Ninja",
        confidence=confidence,
        confidence_reason=reason,
    )


def _field_values(item: Any, keys: set[str]) -> list[str]:
    wanted = {key.casefold() for key in keys}
    values: list[str] = []
    if isinstance(item, dict):
        for key, value in item.items():
            if str(key).casefold() in wanted:
                values.extend(_scalar_values(value))
            elif isinstance(value, (dict, list)):
                values.extend(_field_values(value, keys))
    elif isinstance(item, list):
        for value in item:
            values.extend(_field_values(value, keys))
    return list(dict.fromkeys(value for value in values if value))


def _scalar_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        return [
            result
            for item in value
            for result in _scalar_values(item)
        ]
    if isinstance(value, dict):
        preferred = []
        for key in ("value", "#text", "text", "name", "label"):
            if key in value:
                preferred.extend(_scalar_values(value[key]))
        return preferred or [
            result
            for item in value.values()
            for result in _scalar_values(item)
        ]
    return []


def _first_field(item: dict[str, Any], keys: set[str]) -> str:
    values = _field_values(item, keys)
    return values[0] if values else ""


def _crossref_date(item: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "published", "issued"):
        value = item.get(key)
        if not isinstance(value, dict):
            continue
        parts = value.get("date-parts")
        if (
            isinstance(parts, list)
            and parts
            and isinstance(parts[0], list)
        ):
            return "-".join(str(part) for part in parts[0] if str(part))
    return ""


def _map_hardcover_book(
    item: dict[str, Any],
    *,
    wanted_title: str,
    wanted_author: str,
    wanted_isbn: str,
) -> RemoteMetadataResult | None:
    book_title = _text(item.get("title"))
    editions = item.get("editions")
    if not book_title or not isinstance(editions, list):
        return None
    edition = next(
        (value for value in editions if isinstance(value, dict)),
        {},
    )
    edition_title = _text(edition.get("title")) or book_title
    contributors = edition.get("cached_contributors")
    authors = _hardcover_authors(contributors)
    isbn = _text(edition.get("isbn_13")) or _text(edition.get("isbn_10"))
    confidence, reason = _confidence(
        title=edition_title,
        authors=authors,
        isbn=isbn,
        wanted_title=wanted_title,
        wanted_author=wanted_author,
        wanted_isbn=wanted_isbn,
    )
    image = edition.get("cached_image")
    cover_url = (
        _secure_url(_text(image.get("url")))
        if isinstance(image, dict)
        else _secure_url(_text(image))
    )
    language = edition.get("language")
    publisher = edition.get("publisher")
    series = item.get("cached_featured_series")
    series_name = ""
    series_number = ""
    if isinstance(series, dict):
        nested = series.get("series")
        if isinstance(nested, dict):
            series_name = _text(nested.get("name"))
        series_number = _text(series.get("position"))
    slug = _text(item.get("slug"))
    return RemoteMetadataResult(
        title=edition_title,
        author=", ".join(authors),
        isbn=isbn,
        publisher=(
            _text(publisher.get("name"))
            if isinstance(publisher, dict)
            else ""
        ),
        language=(
            _text(language.get("code3"))
            if isinstance(language, dict)
            else ""
        ),
        published_date=_text(edition.get("release_date")),
        description=_plain_text(_text(item.get("description"))),
        series=series_name,
        series_number=series_number,
        cover_url=cover_url,
        source_url=(
            f"https://hardcover.app/books/{slug}" if slug else ""
        ),
        provider_name="Hardcover",
        confidence=confidence,
        confidence_reason=reason,
    )


def _map_comic_vine_volume(
    item: dict[str, Any],
    *,
    wanted_title: str,
) -> RemoteMetadataResult | None:
    title = _text(item.get("name"))
    if not title:
        return None
    publisher = item.get("publisher")
    image = item.get("image")
    cover_url = ""
    if isinstance(image, dict):
        cover_url = next(
            (
                _secure_url(_text(image.get(key)))
                for key in ("original_url", "super_url", "screen_url")
                if _text(image.get(key))
            ),
            "",
        )
    exact_title = bool(
        _normalise(wanted_title)
        and _normalise(wanted_title) == _normalise(title)
    )
    return RemoteMetadataResult(
        title=title,
        publisher=(
            _text(publisher.get("name"))
            if isinstance(publisher, dict)
            else ""
        ),
        published_date=_text(item.get("start_year")),
        description=_plain_text(
            _text(item.get("description")) or _text(item.get("deck"))
        ),
        cover_url=cover_url,
        source_url=_secure_url(_text(item.get("site_detail_url"))),
        provider_name="Comic Vine",
        confidence=90 if exact_title else 60,
        confidence_reason=(
            "Exact comic title match"
            if exact_title
            else "Possible comic title match"
        ),
    )


def _comic_vine_volume_candidates(
    items: list[Any],
    *,
    wanted_title: str,
    wanted_publisher: str,
) -> list[dict[str, Any]]:
    """Prefer the exact series and publisher before querying issue records."""
    candidates = [
        item
        for item in items
        if isinstance(item, dict)
        and _text(item.get("id"))
        and _text(item.get("name"))
    ]
    exact = [
        item
        for item in candidates
        if _normalise(_text(item.get("name"))) == _normalise(wanted_title)
    ]
    if exact:
        candidates = exact
    publisher_matches = [
        item
        for item in candidates
        if _publisher_matches(
            _comic_vine_publisher(item),
            wanted_publisher,
        )
    ]
    if publisher_matches:
        candidates = publisher_matches
    return sorted(
        candidates,
        key=lambda item: (
            not _publisher_matches(
                _comic_vine_publisher(item),
                wanted_publisher,
            ),
            _normalise(_text(item.get("name"))) != _normalise(wanted_title),
            -_integer_or_zero(item.get("start_year")),
        ),
    )


def _map_comic_vine_issue(
    item: dict[str, Any],
    *,
    volume: dict[str, Any],
    wanted_title: str,
    wanted_issue_number: str,
    wanted_publisher: str,
) -> RemoteMetadataResult | None:
    issue_number = _text(item.get("issue_number"))
    if (
        not issue_number
        or _normalise_issue_number(issue_number)
        != _normalise_issue_number(wanted_issue_number)
    ):
        return None
    volume_data = item.get("volume")
    volume_name = (
        _text(volume_data.get("name"))
        if isinstance(volume_data, dict)
        else ""
    ) or _text(volume.get("name")) or wanted_title
    publisher = _comic_vine_publisher(volume) or wanted_publisher
    issue_name = _text(item.get("name"))
    title = f"{volume_name} #{issue_number}"
    if issue_name and _normalise(issue_name) != _normalise(volume_name):
        title = f"{title}: {issue_name}"

    image = item.get("image")
    cover_url = ""
    if isinstance(image, dict):
        cover_url = next(
            (
                _secure_url(_text(image.get(key)))
                for key in ("original_url", "super_url", "screen_url")
                if _text(image.get(key))
            ),
            "",
        )
    writers = []
    credits = item.get("person_credits")
    if isinstance(credits, list):
        writers = [
            _text(credit.get("name"))
            for credit in credits
            if isinstance(credit, dict)
            and "writer" in _text(credit.get("role")).casefold()
            and _text(credit.get("name"))
        ]
    exact_series = _normalise(volume_name) == _normalise(wanted_title)
    publisher_match = _publisher_matches(publisher, wanted_publisher)
    return RemoteMetadataResult(
        title=title,
        author=", ".join(dict.fromkeys(writers)),
        publisher=publisher,
        published_date=(
            _text(item.get("cover_date"))
            or _text(item.get("store_date"))
        ),
        description=_plain_text(
            _text(item.get("description")) or _text(item.get("deck"))
        ),
        series=volume_name,
        series_number=issue_number,
        cover_url=cover_url,
        source_url=_secure_url(_text(item.get("site_detail_url"))),
        provider_name="Comic Vine",
        confidence=(
            100 if exact_series and publisher_match else 95
            if exact_series else 85
        ),
        confidence_reason=(
            f"Exact {volume_name} issue #{issue_number} match"
        ),
    )


def _comic_vine_publisher(item: dict[str, Any]) -> str:
    publisher = item.get("publisher")
    return (
        _text(publisher.get("name"))
        if isinstance(publisher, dict)
        else ""
    )


def _publisher_matches(first: str, second: str) -> bool:
    if not second.strip():
        return True
    first_words = set(_publisher_words(first))
    second_words = set(_publisher_words(second))
    return bool(first_words and second_words and first_words & second_words)


def _publisher_words(value: str) -> tuple[str, ...]:
    ignored = {"comic", "comics", "publication", "publications", "publishing"}
    return tuple(
        word
        for word in _normalise(value).split()
        if word not in ignored
    )


def _normalise_issue_number(value: str) -> str:
    cleaned = re.sub(r"[^0-9a-z.]", "", str(value).casefold())
    match = re.fullmatch(r"0*(\d+)(.*)", cleaned)
    if match is None:
        return cleaned
    return f"{int(match.group(1))}{match.group(2)}"


def _integer_or_zero(value: Any) -> int:
    try:
        return int(_text(value))
    except ValueError:
        return 0


def _hardcover_authors(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for contributor in value:
        if not isinstance(contributor, dict):
            continue
        author = contributor.get("author")
        name = (
            _text(author.get("name"))
            if isinstance(author, dict)
            else _text(contributor.get("name"))
        )
        contribution = _text(contributor.get("contribution")).casefold()
        if name and contribution in {"", "author"}:
            authors.append(name)
    return authors


def _confidence(
    *,
    title: str,
    authors: list[str],
    isbn: str,
    wanted_title: str,
    wanted_author: str,
    wanted_isbn: str,
) -> tuple[int, str]:
    if wanted_isbn and _isbn_key(wanted_isbn) == _isbn_key(isbn):
        return 100, "Exact ISBN match"
    exact_title = bool(
        _normalise(wanted_title)
        and _normalise(wanted_title) == _normalise(title)
    )
    author_match = bool(
        _normalise(wanted_author)
        and any(
            _normalise(wanted_author) in _normalise(author)
            for author in authors
        )
    )
    if exact_title and author_match:
        return 90, "Exact title and author match"
    if exact_title:
        return 75, "Exact title match"
    return 60, "Possible title or author match"


def _structured_book_results(
    page: str,
    *,
    provider_name: str,
    page_url: str,
    wanted_title: str,
    wanted_author: str,
    wanted_isbn: str,
) -> tuple[RemoteMetadataResult, ...]:
    """Extract book metadata and covers from public JSON-LD search pages."""

    objects: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            object_type = value.get("@type", "")
            types = object_type if isinstance(object_type, list) else [object_type]
            if any(str(item).casefold() in {"book", "product", "creativework"} for item in types):
                objects.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        try:
            visit(json.loads(html.unescape(match.group(1)).strip()))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    def named(value: Any) -> str:
        if isinstance(value, dict):
            return _text(value.get("name"))
        if isinstance(value, list):
            return ", ".join(filter(None, (named(item) for item in value)))
        return _text(value)

    def image_url(value: Any) -> str:
        if isinstance(value, dict):
            return _text(value.get("url") or value.get("contentUrl"))
        if isinstance(value, list):
            return next((image_url(item) for item in value if image_url(item)), "")
        return _text(value)

    results: list[RemoteMetadataResult] = []
    seen: set[tuple[str, str, str]] = set()
    for item in objects:
        title = _text(item.get("name") or item.get("headline"))
        authors = [part.strip() for part in named(item.get("author") or item.get("creator")).split(",") if part.strip()]
        isbn = _text(item.get("isbn") or item.get("sku"))
        confidence, reason = _confidence(
            title=title,
            authors=authors,
            isbn=isbn,
            wanted_title=wanted_title,
            wanted_author=wanted_author,
            wanted_isbn=wanted_isbn,
        )
        if not title or confidence < 60:
            continue
        series = named(item.get("isPartOf"))
        rating = item.get("aggregateRating")
        rating_value = 0.0
        rating_count = 0
        if isinstance(rating, dict):
            try:
                rating_value = float(rating.get("ratingValue") or 0)
            except (TypeError, ValueError):
                rating_value = 0.0
            try:
                rating_count = int(rating.get("ratingCount") or rating.get("reviewCount") or 0)
            except (TypeError, ValueError):
                rating_count = 0
        source = urljoin(page_url, _text(item.get("url"))) or page_url
        raw_cover = image_url(item.get("image"))
        cover = urljoin(page_url, raw_cover) if raw_cover else ""
        key = (_normalise(title), _normalise(named(item.get("author") or item.get("creator"))), cover)
        if key in seen:
            continue
        seen.add(key)
        results.append(RemoteMetadataResult(
            title=title,
            author=named(item.get("author") or item.get("creator")),
            isbn=isbn,
            publisher=named(item.get("publisher") or item.get("brand")),
            language=named(item.get("inLanguage")),
            published_date=_text(item.get("datePublished")),
            description=_plain_text(_text(item.get("description"))),
            series=series,
            cover_url=_secure_url(cover),
            source_url=source,
            provider_name=provider_name,
            confidence=confidence,
            confidence_reason=reason,
            provider_rating=rating_value,
            rating_count=rating_count,
        ))
    return tuple(results)


def _plain_text(value: str) -> str:
    return " ".join(
        html.unescape(re.sub(r"<[^>]+>", " ", value)).split()
    )


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _secure_url(value: str) -> str:
    if value.startswith("http://"):
        return "https://" + value.removeprefix("http://")
    return value if value.startswith("https://") else ""


def _normalise(value: str) -> str:
    return " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in value.casefold()
        ).split()
    )


def _isbn_key(value: str) -> str:
    return "".join(
        character
        for character in value.casefold()
        if character.isdigit() or character == "x"
    )

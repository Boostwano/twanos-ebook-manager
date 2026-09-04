"""Metadata lookup, cover search, and protected catalogue application."""

from __future__ import annotations

import json
import html
import re
import socket
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from database.database import DatabaseManager
from core.metadata import extract_epub_opening_excerpt, normalise_isbn
from services.cover_search_service import (
    CoverSearchError,
    CoverSearchSource,
    CoverSearchService,
    DirectCoverResult,
)
from services.library_service import LibraryRecord, LibraryService
from services.plugin_service import PluginService
from services.protection_models import OperationRecord, PlanConfirmation
from services.protection_service import BackupPolicy, ProtectionService
from services.remote_metadata_provider_service import (
    RemoteMetadataProviderService,
    RemoteMetadataResult,
    RemoteProviderError,
)
from services.series_metadata import (
    canonical_series_details,
    clean_series_name,
    known_series_group,
    parse_series_label,
    series_from_description,
    split_title_series,
)
from preferences import ProtectionMode


OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
OPEN_LIBRARY_ISBN_URL = "https://openlibrary.org/isbn"
OPEN_LIBRARY_COVER_URL = "https://covers.openlibrary.org/b/id"
OPEN_LIBRARY_TIMEOUT_SECONDS = 20.0
OPEN_LIBRARY_USER_AGENT = "Twanos-eBook-Manager/4 (manual lookup)"
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
# A stable, always-available probe book used only to confirm a provider
# responds -- never shown to the user, and never a real catalogue book.
PROVIDER_CHECK_PROBE_TITLE = "Pride and Prejudice"
PROVIDER_CHECK_PROBE_AUTHOR = "Jane Austen"
PROVIDER_CHECK_PROBE_ISBN = "9780141439518"
PROVIDER_CHECK_COMIC_FILE_NAME = "Sandman 001.cbz"
_WIKIDATA_BOOK_TYPES = frozenset(
    {
        "Q571",  # book
        "Q7725634",  # literary work
        "Q47461344",  # written work
        "Q8261",  # novel
        "Q1667921",  # book series
    }
)
SERPAPI_SEARCH_URL = "https://serpapi.com/search"
METADATA_CACHE_SCHEMA_VERSION = 7
COMIC_FILE_EXTENSIONS = frozenset({".cbr", ".cbz"})


def _is_comic_file(file_name: str) -> bool:
    """Return whether the selected catalogue item is a comic archive."""
    return Path(str(file_name or "").strip()).suffix.casefold() in (
        COMIC_FILE_EXTENSIONS
    )


@dataclass(frozen=True)
class MetadataCandidate:
    """One provider-neutral result offered for field-level review."""

    title: str
    author: str
    isbn: str
    publisher: str
    language: str
    published_date: str
    cover_id: int | None
    work_key: str
    confidence: int
    confidence_reason: str
    provider_name: str = "Open Library"
    remote_cover_url: str = ""
    source_url: str = ""
    description: str = ""
    series: str = ""
    series_number: str = ""
    series_group: str = ""
    series_group_number: str = ""
    provider_rating: float = 0.0
    rating_count: int = 0

    @property
    def cover_url(self) -> str:
        if self.remote_cover_url:
            return self.remote_cover_url
        if self.cover_id is None:
            return ""
        return (
            f"{OPEN_LIBRARY_COVER_URL}/{self.cover_id}-L.jpg"
            "?default=false"
        )


class MetadataLookupError(RuntimeError):
    """Readable failure from a human-requested provider lookup."""


@dataclass(frozen=True)
class MetadataSearchTerms:
    """Provider query terms prepared from catalogue and filename metadata."""

    title: str
    author: str
    isbn: str
    from_filename: bool = False
    comic_issue_number: str = ""
    comic_publisher: str = ""


@dataclass(frozen=True)
class ProviderSearchReport:
    """Explain which direct providers participated in the last search."""

    searched_providers: tuple[str, ...] = ()
    failed_providers: tuple[str, ...] = ()
    cover_providers: tuple[str, ...] = ()
    failure_details: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetadataSourceAssessment:
    """Summarise independent evidence for a selected metadata candidate."""

    summary: str = ""
    agreeing_sources: tuple[str, ...] = ()
    conflict_sources: tuple[str, ...] = ()
    needs_manual_review: bool = False


class MetadataStudioService:
    """Coordinate low-volume lookup and protected metadata application."""

    def __init__(
        self,
        database: DatabaseManager | None = None,
        *,
        library_service: LibraryService | None = None,
        protection_service: ProtectionService | None = None,
        plugin_service: PluginService | None = None,
        cover_search_service: CoverSearchService | None = None,
        remote_provider_service: RemoteMetadataProviderService | None = None,
        cache_path: str | Path | None = None,
        timeout: float = OPEN_LIBRARY_TIMEOUT_SECONDS,
    ) -> None:
        inferred_database = (
            protection_service.database
            if protection_service is not None
            else None
        )
        self.database = database or inferred_database or DatabaseManager()
        self.library_service = library_service or LibraryService(self.database)
        self.protection_service = (
            protection_service or ProtectionService(self.database)
        )
        self.plugin_service = plugin_service
        self.cover_search_service = (
            cover_search_service or CoverSearchService(timeout=timeout)
        )
        self.remote_provider_service = (
            remote_provider_service
            or RemoteMetadataProviderService(timeout=timeout)
        )
        self.cache_path = Path(
            cache_path or self.database.database_path.parent / "metadata-cache.json"
        )
        self.timeout = float(timeout)
        self._lookup_cache: dict[
            tuple[str, str, str], tuple[MetadataCandidate, ...]
        ] = {}
        self._wikipedia_series_cache: dict[tuple[str, str], tuple[str, str]] = {}
        self._wikidata_series_cache: dict[tuple[str, str], tuple[str, str]] = {}
        self._serpapi_series_cache: dict[tuple[str, str], tuple[str, str]] = {}
        self.last_search_report = ProviderSearchReport()

    def list_books(self, search_text: str = "") -> tuple[LibraryRecord, ...]:
        """Return unfinished active books for the metadata review queue."""
        unfinished: list[LibraryRecord] = []
        for record in self.library_service.get_library(
            search_text=search_text
        ).records:
            if record.metadata_workflow_complete:
                continue
            if record.metadata_workflow_state < 0:
                unfinished.append(record)
                continue
            candidate = {
                "id": record.book_id,
                "title": record.title,
                "author": record.author,
                "isbn": record.isbn,
                "series": record.series,
                "series_number": record.series_number,
                "series_group": record.series_group,
                "series_group_number": record.series_group_number,
                "description": record.description,
                "cover_path": record.cover_path,
                "file_path": record.file_path,
                "library_folder": record.library_folder,
            }
            if self.protection_service.metadata_workflow_record_is_complete(
                candidate
            ):
                self.database.set_metadata_workflow_complete(
                    record.book_id,
                    True,
                )
                continue
            unfinished.append(record)
        return tuple(unfinished)

    def list_all_books(self, search_text: str = "") -> tuple[LibraryRecord, ...]:
        """Return all active books for an explicitly requested rescan."""
        return tuple(
            self.library_service.get_library(search_text=search_text).records
        )

    def assess_candidate_sources(
        self,
        record: LibraryRecord,
        selected: MetadataCandidate,
        candidates: Sequence[MetadataCandidate],
    ) -> MetadataSourceAssessment:
        """Compare a result with the filename, catalogue, and other providers.

        This is deliberately advisory.  Existing embedded/catalogue metadata is
        preserved as evidence rather than treated as automatically correct.
        """
        filename_title, filename_author = _filename_search_terms(
            Path(record.file_path).name,
        )
        agreeing: list[str] = []
        conflicts: list[str] = []
        evidence: list[str] = []

        def add_unique(values: list[str], value: str) -> None:
            value = str(value or "").strip()
            if value and value not in values:
                values.append(value)

        filename_agrees = _title_matches(filename_title, selected.title) and (
            not filename_author
            or _author_is_compatible(filename_author, selected.author)
        )
        if filename_agrees:
            add_unique(agreeing, "Filename")
            evidence.append("filename agrees")
        elif filename_title:
            add_unique(conflicts, "Filename")
            evidence.append("filename conflicts")

        catalogue_agrees = _title_matches(record.title, selected.title) and (
            not record.author
            or _author_is_compatible(record.author, selected.author)
        )
        if catalogue_agrees:
            add_unique(agreeing, "Current catalogue")
            evidence.append("catalogue agrees")
        elif record.title:
            add_unique(conflicts, "Current catalogue")
            evidence.append("catalogue conflicts")

        selected_isbn = _normalise(selected.isbn)
        seen_providers: set[str] = set()
        if selected.provider_name:
            add_unique(agreeing, selected.provider_name)
            seen_providers.add(selected.provider_name)
        for candidate in candidates:
            provider = str(candidate.provider_name or "").strip()
            if not provider or provider in seen_providers:
                continue
            seen_providers.add(provider)
            candidate_isbn = _normalise(candidate.isbn)
            same_isbn = bool(
                selected_isbn
                and candidate_isbn
                and selected_isbn == candidate_isbn
            )
            same_work = _title_matches(candidate.title, selected.title) and (
                not candidate.author
                or not selected.author
                or _author_is_compatible(candidate.author, selected.author)
            )
            if same_isbn or same_work:
                add_unique(agreeing, provider)
            elif (
                candidate.confidence >= 80
                and selected.author
                and candidate.author
                and _author_is_compatible(candidate.author, selected.author)
            ):
                add_unique(conflicts, provider)

        provider_agreements = tuple(
            source
            for source in agreeing
            if source not in {"Filename", "Current catalogue"}
        )
        provider_conflicts = tuple(
            source
            for source in conflicts
            if source not in {"Filename", "Current catalogue"}
        )
        if provider_agreements:
            evidence.append(
                f"{len(provider_agreements)} provider"
                f"{'s' if len(provider_agreements) != 1 else ''} agree"
            )
        if provider_conflicts:
            evidence.append(
                f"{len(provider_conflicts)} provider"
                f"{'s' if len(provider_conflicts) != 1 else ''} conflict"
            )

        independent_agreements = len(agreeing) - int(bool(selected.provider_name))
        needs_review = (
            selected.confidence < 80
            or bool(provider_conflicts)
            or (bool(conflicts) and independent_agreements < 2)
        )
        conclusion = (
            "Manual review recommended."
            if needs_review
            else "Evidence supports this match."
        )
        summary = "Evidence: " + "; ".join(evidence or ["one provider result"])
        summary += f". {conclusion}"
        return MetadataSourceAssessment(
            summary=summary,
            agreeing_sources=tuple(agreeing),
            conflict_sources=tuple(conflicts),
            needs_manual_review=needs_review,
        )

    def mark_book_complete_if_ready(self, book_id: int) -> bool:
        """Persist completion when a previously applied book is fully ready."""
        complete = self.protection_service.metadata_workflow_is_complete(
            int(book_id)
        )
        if complete:
            self.database.set_metadata_workflow_complete(int(book_id), True)
        return complete

    def move_book_to_manual_review(self, book_id: int):
        """Move an invalid result out of the active watched catalogue."""
        return self.library_service.move_book_to_manual_review(book_id)

    def delete_book(self, book_id: int):
        """Move a book the user no longer wants tracked to -=deleted=-."""
        return self.library_service.move_book_to_deleted(book_id)

    def cover_sources(self) -> tuple[CoverSearchSource, ...]:
        """Return simple Calibre-independent cover search choices."""
        sources = self.cover_search_service.sources()
        if self.plugin_service is None:
            return sources
        return tuple(
            source
            for source in sources
            if (
                source.source_id == "automatic"
                or not source.plugin_id
                or self.plugin_service.is_enabled(source.plugin_id)
            )
        )

    def metadata_provider_choices(self) -> tuple[tuple[str, str], ...]:
        """Return active online metadata providers for the page selector."""
        if self.plugin_service is None:
            return (
                ("", "All active providers"),
                ("open_library_metadata", "Open Library only"),
            )
        providers = [
            (plugin.plugin_id, f"{plugin.name} only")
            for plugin in self.plugin_service.list_plugins()
            if plugin.enabled
            and plugin.plugin_id != "local_metadata"
            and "metadata_provider" in plugin.capabilities
        ]
        return (
            ("", "All active providers"),
            *sorted(providers, key=lambda item: item[1].casefold()),
        )

    @staticmethod
    def prepare_search_terms(
        *,
        title: str | None = "",
        author: str | None = "",
        isbn: str | None = "",
        file_name: str = "",
    ) -> MetadataSearchTerms:
        """Prefer a clear ``Title - Author`` filename for online searches."""
        cleaned_title = " ".join(str(title or "").split())
        cleaned_title, _embedded_series, _embedded_number = (
            split_title_series(cleaned_title)
        )
        cleaned_title = _collapse_accidental_character_repeats(cleaned_title)
        cleaned_author = " ".join(str(author or "").split())
        cleaned_isbn = normalise_isbn(str(isbn or "")) or ""
        comic_terms = _comic_filename_search_terms(file_name)
        if comic_terms is not None:
            comic_title, comic_issue_number, comic_publisher = comic_terms
            return MetadataSearchTerms(
                comic_title,
                "",
                cleaned_isbn,
                True,
                comic_issue_number,
                comic_publisher,
            )
        if cleaned_isbn:
            return MetadataSearchTerms(
                cleaned_title,
                cleaned_author,
                cleaned_isbn,
            )

        filename_title, filename_author = _filename_search_terms(
            file_name,
            wanted_title=cleaned_title,
            wanted_author=cleaned_author,
        )
        filename_title = _collapse_accidental_character_repeats(filename_title)
        embedded_order_title = _embedded_title_without_file_order_prefix(
            cleaned_title,
            file_name,
        )
        if embedded_order_title and cleaned_author:
            # A numbered collection filename can contain a typo while the
            # ebook's embedded title is correct.  Keep the embedded wording
            # and remove only the explicit ``21 -`` ordering prefix shared by
            # the filename and title.
            return MetadataSearchTerms(
                embedded_order_title,
                cleaned_author,
                "",
                True,
            )
        filename_pair_is_credible = bool(
            filename_title
            and filename_author
            and (
                _author_likelihood(filename_author) >= 2
                or not cleaned_author
                or _author_matches(filename_author, cleaned_author)
            )
        )
        if filename_pair_is_credible:
            return MetadataSearchTerms(
                filename_title,
                filename_author,
                "",
                True,
            )
        if (
            filename_title
            and (
                not cleaned_title
                or cleaned_title.casefold() in {"unknown", "unknown title"}
                or _has_leading_sequence_number(cleaned_title)
            )
        ):
            return MetadataSearchTerms(
                filename_title,
                cleaned_author,
                "",
                True,
            )
        return MetadataSearchTerms(
            cleaned_title,
            cleaned_author,
            "",
        )

    def search_candidates(
        self,
        *,
        title: str = "",
        author: str = "",
        isbn: str = "",
        cache_days: int = 30,
        provider_plugin_id: str = "open_library_metadata",
    ) -> tuple[MetadataCandidate, ...]:
        """Return up to eight distinct Open Library matches."""
        if (
            self.plugin_service is not None
            and not self.plugin_service.is_enabled(provider_plugin_id)
        ):
            raise MetadataLookupError(
                "Open Library Metadata & Covers is not enabled. Open "
                "Plugins, select it, then choose Install Approved Plugin."
            )
        key = (
            " ".join(title.split()).casefold(),
            " ".join(author.split()).casefold(),
            "".join(isbn.split()),
        )
        if not any(key):
            raise ValueError("Enter a title, author, or ISBN to search.")
        if key in self._lookup_cache:
            cached = self._lookup_cache[key]
            if cached:
                return cached
            # A temporary provider failure or an earlier miss must not make a
            # corrected title look permanently unavailable for this session.
            self._lookup_cache.pop(key, None)
        persisted = self._load_persistent_cache(key, cache_days=cache_days)
        if persisted:
            self._lookup_cache[key] = persisted
            return persisted

        parameters: dict[str, str] = {
            "limit": "8",
            "fields": (
                "key,title,author_name,isbn,publisher,language,"
                "first_publish_year,first_publish_date,cover_i,"
                "first_sentence,series"
            ),
        }
        if key[2]:
            parameters["isbn"] = key[2]
        else:
            parameters["title"] = title.strip()
            if author.strip():
                parameters["author"] = author.strip()
        url = f"{OPEN_LIBRARY_SEARCH_URL}?{urlencode(parameters)}"
        request = Request(
            url,
            headers={
                "User-Agent": OPEN_LIBRARY_USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    raise MetadataLookupError(
                        "Open Library did not accept the lookup."
                    )
                payload = json.loads(response.read())
        except (TimeoutError, socket.timeout) as error:
            raise MetadataLookupError(
                "Open Library is responding slowly right now. Try again "
                "in a moment."
            ) from error
        except (
            HTTPError,
            URLError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
        ) as error:
            raise MetadataLookupError(
                "Open Library could not be reached. Check the internet "
                "connection and try again."
            ) from error

        documents = payload.get("docs", ()) if isinstance(payload, dict) else ()
        edition = self._open_library_isbn_edition(key[2]) if key[2] else None
        if edition:
            documents = tuple(
                _merge_open_library_edition(document, edition)
                if isinstance(document, dict)
                else document
                for document in documents
            )
        candidates = tuple(
            candidate
            for document in documents
            if isinstance(document, dict)
            if (
                candidate := self._map_candidate(
                    document,
                    wanted_title=title,
                    wanted_author=author,
                    wanted_isbn=isbn,
                )
            )
        )
        if candidates:
            self._lookup_cache[key] = candidates
            self._save_persistent_cache(
                key,
                candidates,
                cache_days=cache_days,
            )
        return candidates

    def _open_library_isbn_edition(
        self,
        isbn: str,
    ) -> dict[str, Any] | None:
        """Return edition-only fields that Open Library search can omit.

        The ISBN endpoint commonly carries the jacket and series label even
        when the general search document does not. Failure here is deliberately
        non-fatal because the broad search result is still useful metadata.
        """
        cleaned_isbn = normalise_isbn(isbn) or ""
        if not cleaned_isbn:
            return None
        request = Request(
            f"{OPEN_LIBRARY_ISBN_URL}/{cleaned_isbn}.json",
            headers={
                "User-Agent": OPEN_LIBRARY_USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    return None
                payload = json.loads(response.read())
        except (
            HTTPError,
            URLError,
            TimeoutError,
            socket.timeout,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
        ):
            return None
        return payload if isinstance(payload, dict) else None

    def _wikipedia_series_hint(
        self,
        *,
        title: str,
        author: str,
    ) -> tuple[str, str]:
        """Return an explicit numbered series statement for an exact title.

        This deliberately narrow, non-fatal fallback runs only after an exact
        ISBN provider has established that the book belongs to a series but
        omitted its position. It accepts only an explicit ordinal statement
        in the matching public Wikipedia article.
        """
        key = (_normalise(title), _normalise(author))
        if not key[0]:
            return "", ""
        cached = self._wikipedia_series_cache.get(key)
        if cached is not None:
            return cached
        parameters = {
            "action": "query",
            "prop": "extracts",
            "explaintext": "1",
            "redirects": "1",
            "titles": title.strip(),
            "format": "json",
            "utf8": "1",
        }
        request = Request(
            f"{WIKIPEDIA_API_URL}?{urlencode(parameters)}",
            headers={
                "User-Agent": OPEN_LIBRARY_USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    return "", ""
                payload = json.loads(response.read())
        except (
            HTTPError,
            URLError,
            TimeoutError,
            socket.timeout,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
        ):
            return "", ""

        result = ("", "")
        query = payload.get("query", {}) if isinstance(payload, dict) else {}
        pages = query.get("pages", {}) if isinstance(query, dict) else {}
        page = next(iter(pages.values()), {}) if isinstance(pages, dict) else {}
        article_title = str(page.get("title", "")) if isinstance(page, dict) else ""
        extract = str(page.get("extract", "")) if isinstance(page, dict) else ""
        if _normalise(article_title) == key[0]:
            match = _SERIES_ORDINAL_COMPOUND_RE.search(
                extract
            ) or _SERIES_ORDINAL_SIMPLE_RE.search(extract)
            if match is not None:
                ordinal = (
                    match.groupdict().get("novel")
                    or match.groupdict().get("number")
                    or ""
                )
                number = _ordinal_number(ordinal)
                series = " ".join(match.group("series").split()).strip(" ,-:")
                if series and number:
                    result = (series, number)
        self._wikipedia_series_cache[key] = result
        return result

    def _wikidata_series_hint(
        self,
        *,
        title: str,
        author: str,
    ) -> tuple[str, str]:
        """Return an explicit series name and order from Wikidata's free API.

        Many books with no dedicated Wikipedia article still have a
        Wikidata item recording a structured "part of the series" (P179)
        claim with a "series ordinal" (P1545) qualifier. Only an item whose
        label matches the title exactly and whose "instance of" (P31) marks
        it as a book/literary work is accepted, so this cannot silently
        substitute an unrelated same-titled item. No API key is required.
        """
        key = (_normalise(title), _normalise(author))
        if not key[0]:
            return "", ""
        cached = self._wikidata_series_cache.get(key)
        if cached is not None:
            return cached
        result = ("", "")

        matched_qid = self._wikidata_matching_item(title, key[0])
        if not matched_qid:
            self._wikidata_series_cache[key] = result
            return result

        claims = self._wikidata_entity_claims(matched_qid)
        if claims is None:
            self._wikidata_series_cache[key] = result
            return result

        instance_ids = {
            _wikidata_claim_target_id(claim)
            for claim in claims.get("P31", ())
            if isinstance(claim, dict)
        }
        if not instance_ids & _WIKIDATA_BOOK_TYPES:
            self._wikidata_series_cache[key] = result
            return result

        series_qid = ""
        ordinal = ""
        for claim in claims.get("P179", ()):
            if not isinstance(claim, dict):
                continue
            target_id = _wikidata_claim_target_id(claim)
            if not target_id:
                continue
            qualifiers = claim.get("qualifiers", {})
            for ordinal_claim in (
                qualifiers.get("P1545", ()) if isinstance(qualifiers, dict) else ()
            ):
                value = (
                    ordinal_claim.get("datavalue", {}).get("value", "")
                    if isinstance(ordinal_claim, dict)
                    else ""
                )
                if isinstance(value, str) and value.strip():
                    ordinal = value.strip()
                    break
            if ordinal:
                series_qid = target_id
                break
        if series_qid and ordinal:
            series_name = self._wikidata_entity_label(series_qid)
            if series_name:
                result = (series_name, ordinal)
        self._wikidata_series_cache[key] = result
        return result

    def _wikidata_matching_item(self, title: str, normalised_title: str) -> str:
        """Return the QID of a Wikidata item whose label exactly matches."""
        parameters = {
            "action": "wbsearchentities",
            "search": title.strip(),
            "language": "en",
            "type": "item",
            "format": "json",
            "limit": "5",
        }
        request = Request(
            f"{WIKIDATA_API_URL}?{urlencode(parameters)}",
            headers={
                "User-Agent": OPEN_LIBRARY_USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    return ""
                payload = json.loads(response.read())
        except (
            HTTPError,
            URLError,
            TimeoutError,
            socket.timeout,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
        ):
            return ""
        entries = payload.get("search", ()) if isinstance(payload, dict) else ()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if _normalise(str(entry.get("label", ""))) == normalised_title:
                return str(entry.get("id", ""))
        return ""

    def _wikidata_entity_claims(
        self,
        qid: str,
    ) -> dict[str, Any] | None:
        """Return one Wikidata item's claims, or None on any failure."""
        parameters = {
            "action": "wbgetentities",
            "ids": qid,
            "props": "claims",
            "format": "json",
        }
        request = Request(
            f"{WIKIDATA_API_URL}?{urlencode(parameters)}",
            headers={
                "User-Agent": OPEN_LIBRARY_USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    return None
                payload = json.loads(response.read())
        except (
            HTTPError,
            URLError,
            TimeoutError,
            socket.timeout,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
        ):
            return None
        entities = payload.get("entities", {}) if isinstance(payload, dict) else {}
        entity = entities.get(qid, {}) if isinstance(entities, dict) else {}
        claims = entity.get("claims", {}) if isinstance(entity, dict) else {}
        return claims if isinstance(claims, dict) else {}

    def _wikidata_entity_label(self, qid: str) -> str:
        """Return one Wikidata item's English label, or "" on any failure."""
        parameters = {
            "action": "wbgetentities",
            "ids": qid,
            "props": "labels",
            "languages": "en",
            "format": "json",
        }
        request = Request(
            f"{WIKIDATA_API_URL}?{urlencode(parameters)}",
            headers={
                "User-Agent": OPEN_LIBRARY_USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    return ""
                payload = json.loads(response.read())
        except (
            HTTPError,
            URLError,
            TimeoutError,
            socket.timeout,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
        ):
            return ""
        entities = payload.get("entities", {}) if isinstance(payload, dict) else {}
        entity = entities.get(qid, {}) if isinstance(entities, dict) else {}
        labels = entity.get("labels", {}) if isinstance(entity, dict) else {}
        english = labels.get("en", {}) if isinstance(labels, dict) else {}
        return str(english.get("value", "")) if isinstance(english, dict) else ""

    def _serpapi_series_hint(
        self,
        *,
        title: str,
        author: str,
    ) -> tuple[str, str]:
        """Return a series name and order mined from real SerpApi results.

        This is a paid-API fallback used only when the free Wikipedia and
        Wikidata lookups found nothing. A result is only accepted when its
        own title or snippet contains the exact query title, the author's
        surname, and an explicit "Series Name #Number" pattern, so this
        cannot silently substitute an unrelated same-author book.
        """
        if self.plugin_service is None or not self.plugin_service.is_enabled(
            "serpapi_book_resolver"
        ):
            return "", ""
        api_key = self.plugin_service.get_api_key("serpapi_book_resolver")
        if not api_key:
            return "", ""
        cleaned_title = _normalise(title)
        cleaned_author = _normalise(author)
        if len(cleaned_title.split()) < 2 or not cleaned_author:
            return "", ""
        cached_key = (cleaned_title, cleaned_author)
        cached = self._serpapi_series_cache.get(cached_key)
        if cached is not None:
            return cached
        result = ("", "")
        parameters = {
            "engine": "google",
            # Quoting the title as an exact phrase keeps Google from
            # semantically re-interpreting a loosely-worded query; see the
            # matching note in resolve_serpapi_containing_work.
            "q": f'"{title.strip()}" {author.strip()} book series number',
            "num": "5",
            "api_key": api_key,
        }
        request = Request(
            f"{SERPAPI_SEARCH_URL}?{urlencode(parameters)}",
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    self._serpapi_series_cache[cached_key] = result
                    return result
                payload = json.loads(response.read())
        except (
            HTTPError,
            URLError,
            TimeoutError,
            socket.timeout,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
        ):
            self._serpapi_series_cache[cached_key] = result
            return result

        results = (
            payload.get("organic_results", ())
            if isinstance(payload, dict)
            else ()
        )
        surname = cleaned_author.split()[-1] if cleaned_author.split() else ""
        cleaned_title_core = _strip_stopwords(cleaned_title)
        for item in results:
            if not isinstance(item, dict):
                continue
            result_title = " ".join(str(item.get("title", "")).split())
            snippet = str(item.get("snippet", ""))
            evidence_raw = f"{result_title} {snippet}"
            evidence = _normalise(evidence_raw)
            if (
                cleaned_title_core not in _strip_stopwords(evidence)
                or not surname
                or surname not in evidence.split()
            ):
                continue
            # Only accept an explicit, structured statement of series and
            # order (a "(Series, N)" style annotation, or prose stating
            # "is the Nth book in the X series"). A bare "#N" floating in a
            # snippet is too easy to confuse with an unrelated number (a
            # page's own item count, review tally, and so on).
            paren_match = _SERIES_PARENTHETICAL_RE.search(evidence_raw)
            if paren_match is not None:
                series = paren_match.group("series").strip(" ,-:")
                series = _TRAILING_SERIES_WORD_RE.sub("", series).strip()
                number = paren_match.group("number").strip()
                if series and number:
                    result = (series, number)
                    break
                continue
            prose_match = _SERIES_ORDINAL_COMPOUND_RE.search(
                evidence_raw
            ) or _SERIES_ORDINAL_SIMPLE_RE.search(evidence_raw)
            if prose_match is None:
                continue
            ordinal = (
                prose_match.groupdict().get("novel")
                or prose_match.groupdict().get("number")
                or ""
            )
            number = _ordinal_number(ordinal)
            series = " ".join(
                prose_match.group("series").split()
            ).strip(" ,-:")
            if series and number:
                result = (series, number)
                break
        self._serpapi_series_cache[cached_key] = result
        return result

    def search_open_library_excerpt(
        self,
        *,
        excerpt: str,
        author: str,
    ) -> tuple[MetadataCandidate, ...]:
        """Identify a weak match from an author's Open Library bibliography."""
        cleaned_author = author.strip()
        if not cleaned_author or len(_normalise(excerpt).split()) < 10:
            return ()
        parameters = {
            "author": cleaned_author,
            "limit": "50",
            "fields": (
                "key,title,author_name,isbn,publisher,language,"
                "first_publish_year,first_publish_date,cover_i,"
                "first_sentence,series"
            ),
        }
        request = Request(
            f"{OPEN_LIBRARY_SEARCH_URL}?{urlencode(parameters)}",
            headers={
                "User-Agent": OPEN_LIBRARY_USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    raise MetadataLookupError(
                        "Open Library did not accept the excerpt fallback."
                    )
                payload = json.loads(response.read())
        except (TimeoutError, socket.timeout) as error:
            raise MetadataLookupError(
                "Open Library is responding slowly right now. Try again "
                "in a moment."
            ) from error
        except (
            HTTPError,
            URLError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
        ) as error:
            raise MetadataLookupError(
                "Open Library could not be reached for the excerpt fallback."
            ) from error

        matches: list[MetadataCandidate] = []
        documents = payload.get("docs", ()) if isinstance(payload, dict) else ()
        for document in documents:
            if not isinstance(document, dict) or not _passage_matches(
                excerpt,
                _open_library_description(document),
            ):
                continue
            candidate = self._map_candidate(
                document,
                wanted_title=_first_text(document.get("title")),
                wanted_author=cleaned_author,
                wanted_isbn="",
            )
            if candidate is not None:
                matches.append(
                    replace(
                        candidate,
                        confidence=95,
                        confidence_reason="Opening text and author match",
                    )
                )
        return tuple(matches)

    def resolve_wikipedia_containing_work(
        self,
        *,
        title: str,
        author: str,
    ) -> str:
        """Resolve a short work to its containing book using Wikipedia search."""
        cleaned_title = _normalise(title)
        cleaned_author = _normalise(author)
        if len(cleaned_title.split()) < 2 or not cleaned_author:
            return ""
        parameters = {
            "action": "query",
            "list": "search",
            "srsearch": f"{title.strip()} {author.strip()}",
            "srlimit": "5",
            "format": "json",
            "utf8": "1",
        }
        request = Request(
            f"{WIKIPEDIA_API_URL}?{urlencode(parameters)}",
            headers={
                "User-Agent": OPEN_LIBRARY_USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    return ""
                payload = json.loads(response.read())
        except (
            HTTPError,
            URLError,
            TimeoutError,
            socket.timeout,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
        ):
            return ""

        query = payload.get("query", {}) if isinstance(payload, dict) else {}
        results = query.get("search", ()) if isinstance(query, dict) else ()
        author_tokens = cleaned_author.split()
        surname = author_tokens[-1] if author_tokens else ""
        for result in results:
            if not isinstance(result, dict):
                continue
            page_title = " ".join(str(result.get("title", "")).split())
            snippet = html.unescape(
                re.sub(r"<[^>]+>", " ", str(result.get("snippet", "")))
            )
            evidence = _normalise(f"{page_title} {snippet}")
            if (
                cleaned_title in evidence
                and surname
                and surname in evidence.split()
                and _normalise(page_title) != cleaned_title
            ):
                return page_title
        return ""

    def resolve_serpapi_containing_work(
        self,
        *,
        title: str,
        author: str,
    ) -> str:
        """Resolve an uncertain title using real Google results via SerpApi.

        Mirrors ``resolve_wikipedia_containing_work``'s conservatism: a
        result is only accepted when its own page title contains the exact
        query title and the author's surname, so this cannot silently
        substitute an unrelated same-author book. The web search is used
        only to identify the work; metadata and covers still come from the
        other configured providers.
        """
        if self.plugin_service is None or not self.plugin_service.is_enabled(
            "serpapi_book_resolver"
        ):
            return ""
        api_key = self.plugin_service.get_api_key("serpapi_book_resolver")
        if not api_key:
            return ""
        cleaned_title = _normalise(title)
        cleaned_author = _normalise(author)
        if len(cleaned_title.split()) < 2 or not cleaned_author:
            return ""
        parameters = {
            "engine": "google",
            # Quoting the title as an exact phrase keeps Google from
            # semantically re-interpreting a loosely-worded query — for a
            # title that happens to contain only common words (e.g. an
            # extra "the"), an unquoted query has been observed to return
            # results about the word "the" itself rather than the book.
            "q": f'"{title.strip()}" {author.strip()} book',
            "num": "5",
            "api_key": api_key,
        }
        request = Request(
            f"{SERPAPI_SEARCH_URL}?{urlencode(parameters)}",
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    return ""
                payload = json.loads(response.read())
        except (
            HTTPError,
            URLError,
            TimeoutError,
            socket.timeout,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OSError,
        ):
            return ""

        results = (
            payload.get("organic_results", ())
            if isinstance(payload, dict)
            else ()
        )
        author_tokens = cleaned_author.split()
        surname = author_tokens[-1] if author_tokens else ""
        cleaned_title_core = _strip_stopwords(cleaned_title)
        for result in results:
            if not isinstance(result, dict):
                continue
            page_title = _strip_trailing_author_attribution(
                _clean_search_result_title(
                    " ".join(str(result.get("title", "")).split())
                ),
                author,
            )
            snippet = str(result.get("snippet", ""))
            evidence = _normalise(f"{page_title} {snippet}")
            if (
                cleaned_title_core
                and cleaned_title_core in _strip_stopwords(evidence)
                and surname
                and surname in evidence.split()
                and _normalise(page_title) != cleaned_title
                and len(_normalise(page_title).split()) >= 2
            ):
                return page_title
        return ""

    def _enrich_series_from_isbn(
        self,
        candidates: list[MetadataCandidate],
        *,
        title: str,
        author: str,
        provider_title: str,
        provider_author: str,
        cache_days: int,
        provider_selected: Callable[[str], bool],
        failures: list[str],
        searched_providers: list[str],
    ) -> list[MetadataCandidate]:
        """Fill series name/order from the best exact-ISBN candidate.

        Safe to call more than once as the candidate list grows through
        later fallbacks: an earlier call may find no ISBN at all (a
        mistyped title returns nothing from Open Library on the first
        pass), while a later call — after a title-identification fallback
        has corrected the search — sees the real edition and its ISBN.
        Each pass only fills series fields still missing on an exact-ISBN
        match; it never overwrites data already found.
        """
        if self.plugin_service is None or not (
            provider_selected("open_library_metadata")
            and self.plugin_service.is_enabled("open_library_metadata")
        ):
            return candidates
        discovered_isbn = next(
            (
                candidate.isbn
                for candidate in sorted(
                    candidates,
                    key=lambda item: item.confidence,
                    reverse=True,
                )
                if candidate.confidence >= 75 and candidate.isbn
            ),
            "",
        )
        if not discovered_isbn or not (
            not any(
                candidate.confidence >= 75 and candidate.series
                for candidate in candidates
            )
            or not any(
                candidate.confidence >= 75 and candidate.series_number
                for candidate in candidates
            )
        ):
            return candidates

        # A provider such as Harvard can discover an exact ISBN while
        # omitting series data. Re-query Open Library by that ISBN so its
        # edition record can safely fill series and jacket fields.
        try:
            candidates.extend(
                self.search_candidates(
                    title=provider_title or title,
                    author=provider_author or author,
                    isbn=discovered_isbn,
                    cache_days=cache_days,
                )
            )
        except (MetadataLookupError, ValueError) as error:
            failures.append(str(error))

        candidates = _enrich_exact_isbn_series(
            candidates,
            isbn=discovered_isbn,
        )
        # Cached Open Library search results and provider-specific author
        # formatting can still prevent the general candidate merge from
        # carrying the edition's series onto the selected record.  An
        # exact ISBN is a stronger identity than title punctuation or
        # author-name order, so make one final edition-only enrichment.
        needs_series = not any(
            candidate.confidence >= 75 and candidate.series
            for candidate in candidates
        )
        needs_series_number = not any(
            candidate.confidence >= 75 and candidate.series_number
            for candidate in candidates
        )
        edition = (
            self._open_library_isbn_edition(discovered_isbn)
            if needs_series or needs_series_number
            else None
        )
        if edition:
            candidates = _enrich_exact_isbn_series(
                candidates,
                isbn=discovered_isbn,
                edition=edition,
            )
        exact_series_source = next(
            (
                candidate
                for candidate in candidates
                if (
                    candidate.confidence >= 75
                    and not (candidate.series and candidate.series_number)
                    and _normalised_isbn(candidate.isbn)
                    == _normalised_isbn(discovered_isbn)
                )
            ),
            None,
        )
        if exact_series_source is not None:
            # Try free, keyless sources before the paid SerpApi fallback:
            # Wikipedia's own prose, then Wikidata's structured "part of
            # the series" claim. Each is tried only if the previous one
            # found nothing.
            searched_providers.append("Wikipedia Series Resolver")
            hint_series, hint_number = self._wikipedia_series_hint(
                title=exact_series_source.title,
                author=exact_series_source.author,
            )
            if not hint_number:
                searched_providers.append("Wikidata Series Resolver")
                hint_series, hint_number = self._wikidata_series_hint(
                    title=exact_series_source.title,
                    author=exact_series_source.author,
                )
            if (
                not hint_number
                and self.plugin_service is not None
                and self.plugin_service.is_enabled("serpapi_book_resolver")
            ):
                searched_providers.append("SerpApi Series Resolver")
                hint_series, hint_number = self._serpapi_series_hint(
                    title=exact_series_source.title,
                    author=exact_series_source.author,
                )
            if hint_number:
                candidates = _enrich_exact_isbn_series(
                    candidates,
                    isbn=discovered_isbn,
                    series_hint=(hint_series, hint_number),
                )
        return candidates

    def search_enabled_candidates(
        self,
        *,
        title: str = "",
        author: str = "",
        isbn: str = "",
        file_name: str = "",
        cache_days: int = 30,
        include_open_library: bool = True,
        provider_plugin_id: str = "",
    ) -> tuple[MetadataCandidate, ...]:
        """Search all active metadata plugins behind one beginner action."""
        local_title, local_series, local_series_number = split_title_series(
            title
        )
        terms = self.prepare_search_terms(
            title=title,
            author=author,
            isbn=isbn,
            file_name=file_name,
        )
        title, author, isbn = terms.title, terms.author, terms.isbn
        comic_issue_number = terms.comic_issue_number
        comic_publisher = terms.comic_publisher
        is_comic_file = _is_comic_file(file_name)
        if provider_plugin_id == "comic_vine_metadata" and not is_comic_file:
            raise MetadataLookupError(
                "Comic Vine is only used for CBR and CBZ comic files."
            )
        if self.plugin_service is None:
            if provider_plugin_id not in {"", "open_library_metadata"}:
                raise MetadataLookupError(
                    "That metadata provider is not available."
                )
            candidates = self.search_candidates(
                title=title,
                author=author,
                isbn=isbn,
                cache_days=cache_days,
            )
            self.last_search_report = ProviderSearchReport(
                searched_providers=("Open Library",),
                cover_providers=tuple(
                    dict.fromkeys(
                        candidate.provider_name
                        for candidate in candidates
                        if candidate.cover_url
                    )
                ),
            )
            return tuple(
                _apply_local_series_hint(
                    list(candidates),
                    title=local_title,
                    series=local_series,
                    series_number=local_series_number,
                )
            )

        if provider_plugin_id:
            chosen = next(
                (
                    plugin
                    for plugin in self.plugin_service.list_plugins()
                    if plugin.plugin_id == provider_plugin_id
                ),
                None,
            )
            if (
                chosen is None
                or not chosen.enabled
                or "metadata_provider" not in chosen.capabilities
            ):
                raise MetadataLookupError(
                    "The selected metadata provider is not active. Open "
                    "Plugins and enable it, or choose All active providers."
                )

        def provider_selected(plugin_id: str) -> bool:
            return not provider_plugin_id or provider_plugin_id == plugin_id

        candidates: list[MetadataCandidate] = []
        failures: list[str] = []
        searched_providers: list[str] = []
        failed_providers: list[str] = []
        searched = 0
        if (
            include_open_library
            and provider_selected("open_library_metadata")
            and self.plugin_service.is_enabled("open_library_metadata")
        ):
            searched += 1
            searched_providers.append("Open Library")
            try:
                open_library_candidates = list(
                    self.search_candidates(
                        title=title,
                        author=author,
                        isbn=isbn,
                        cache_days=cache_days,
                    )
                )
                if isbn and title and not open_library_candidates:
                    open_library_candidates.extend(
                        self.search_candidates(
                            title=title,
                            author=author,
                            isbn="",
                            cache_days=cache_days,
                        )
                    )
                candidates.extend(open_library_candidates)
            except MetadataLookupError as error:
                failures.append(str(error))
                failed_providers.append("Open Library")
        provider_title, provider_author, provider_isbn = (
            _refined_provider_terms(
                title=title,
                author=author,
                isbn=isbn,
                candidates=candidates,
            )
        )
        provider_jobs: list[
            tuple[
                str,
                str,
                Callable[[], tuple[MetadataCandidate, ...]],
            ]
        ] = []

        def queue_provider(
            provider_name: str,
            plugin_id: str,
            search: Callable[[], tuple[MetadataCandidate, ...]],
        ) -> None:
            nonlocal searched
            searched += 1
            searched_providers.append(provider_name)
            provider_jobs.append((provider_name, plugin_id, search))

        if (
            provider_selected("google_books_covers")
            and self.plugin_service.is_enabled("google_books_covers")
        ):
            google_key = self.plugin_service.get_api_key(
                "google_books_covers"
            )
            queue_provider(
                "Google Books",
                "",
                lambda: tuple(
                    self._map_direct_cover(result)
                    for result in self.cover_search_service.search_google_books(
                        title=provider_title,
                        author=provider_author,
                        isbn=provider_isbn,
                        api_key=google_key,
                    )
                ),
            )
        if (
            provider_selected("apple_books_metadata")
            and self.plugin_service.is_enabled("apple_books_metadata")
        ):
            queue_provider(
                "Apple Books",
                "",
                lambda: tuple(
                    self._map_direct_cover(result)
                    for result in self.cover_search_service.search_apple_books(
                        title=provider_title,
                        author=provider_author,
                        isbn=provider_isbn,
                    )
                ),
            )
        if (
            provider_selected("isbndb_metadata")
            and self.plugin_service.is_enabled("isbndb_metadata")
        ):
            isbndb_key = self.plugin_service.get_api_key("isbndb_metadata")
            queue_provider(
                "ISBNdb",
                "",
                lambda: tuple(
                    self._map_direct_cover(result)
                    for result in self.cover_search_service.search_isbndb(
                        title=provider_title,
                        author=provider_author,
                        isbn=provider_isbn,
                        api_key=isbndb_key,
                    )
                ),
            )
        if (
            provider_selected("hardcover_metadata")
            and self.plugin_service.is_enabled("hardcover_metadata")
        ):
            queue_provider(
                "Hardcover",
                "",
                lambda: self._search_hardcover(
                    title=provider_title,
                    author=provider_author,
                    isbn=provider_isbn,
                ),
            )
        if (
            provider_selected("comic_vine_metadata")
            and self.plugin_service.is_enabled("comic_vine_metadata")
            and is_comic_file
        ):
            queue_provider(
                "Comic Vine",
                "",
                lambda: self._search_comic_vine(
                    title=provider_title,
                    author=provider_author,
                    isbn=provider_isbn,
                    issue_number=comic_issue_number,
                    publisher=comic_publisher,
                ),
            )
        extra_providers = (
            (
                "amazon_metadata",
                "Amazon",
                "search_amazon",
                False,
            ),
            (
                "goodreads_metadata",
                "Goodreads",
                "search_goodreads",
                False,
            ),
            (
                "gutenberg_metadata",
                "Project Gutenberg",
                "search_gutenberg",
                False,
            ),
            (
                "harvard_librarycloud_metadata",
                "Harvard LibraryCloud",
                "search_harvard_librarycloud",
                False,
            ),
            (
                "crossref_metadata",
                "Crossref",
                "search_crossref",
                False,
            ),
            (
                "booktopia_metadata",
                "Booktopia",
                "search_booktopia",
                False,
            ),
            (
                "big_book_metadata",
                "Big Book API",
                "search_big_book",
                True,
            ),
            (
                "openweb_ninja_metadata",
                "OpenWeb Ninja",
                "search_openweb_ninja",
                True,
            ),
        )
        for plugin_id, provider_name, method_name, uses_key in extra_providers:
            if (
                not provider_selected(plugin_id)
                or not self.plugin_service.is_enabled(plugin_id)
            ):
                continue
            health_plugin_id = plugin_id
            queue_provider(
                provider_name,
                health_plugin_id,
                lambda method_name=method_name,
                plugin_id=plugin_id,
                uses_key=uses_key: self._search_remote_provider(
                        method_name=method_name,
                        plugin_id=plugin_id if uses_key else "",
                        title=provider_title,
                        author=provider_author,
                        isbn=provider_isbn,
                    ),
            )

        if provider_jobs:
            # Each provider already has a bounded socket timeout. Running the
            # independent calls together prevents one unavailable site from
            # delaying every provider behind it.
            outcomes: dict[
                int,
                tuple[tuple[MetadataCandidate, ...], Exception | None],
            ] = {}
            with ThreadPoolExecutor(
                max_workers=len(provider_jobs),
                thread_name_prefix="twano-metadata",
            ) as executor:
                futures = {
                    executor.submit(search): index
                    for index, (_name, _plugin, search) in enumerate(
                        provider_jobs
                    )
                }
                for future, index in (
                    (future, futures[future]) for future in futures
                ):
                    try:
                        provider_results = future.result()
                        outcomes[index] = (
                            tuple(provider_results) if provider_results is not None else (),
                            None,
                        )
                    except (
                        CoverSearchError,
                        MetadataLookupError,
                        RemoteProviderError,
                        TypeError,
                        ValueError,
                    ) as error:
                        outcomes[index] = ((), error)

            for index, (provider_name, health_plugin_id, _search) in enumerate(
                provider_jobs
            ):
                results, error = outcomes[index]
                if error is None:
                    candidates.extend(results)
                    if health_plugin_id:
                        self.plugin_service.report_provider_health(
                            health_plugin_id,
                            "healthy",
                            "The provider responded and its expected result format was readable.",
                        )
                    continue
                failures.append(str(error))
                failed_providers.append(provider_name)
                if health_plugin_id:
                    self.plugin_service.report_provider_health(
                        health_plugin_id,
                        getattr(error, "health_status", "unavailable"),
                        getattr(error, "diagnostic", str(error)),
                    )

        candidates = self._enrich_series_from_isbn(
            candidates,
            title=title,
            author=author,
            provider_title=provider_title,
            provider_author=provider_author,
            cache_days=cache_days,
            provider_selected=provider_selected,
            failures=failures,
            searched_providers=searched_providers,
        )

        if searched == 0:
            self.last_search_report = ProviderSearchReport()
            raise MetadataLookupError(
                "No online metadata plugins are active. Open Plugins, "
                "install a metadata provider, then enable it."
            )
        if not any(
            _candidate_is_reviewable(candidate, title=title, author=author)
            for candidate in candidates
        ):
            # Older catalogue records sometimes credit the underlying writer
            # instead of the house name shown on the ebook.  Retry Open
            # Library once with the exact cleaned title and no author, then
            # retain the ebook's known author only when the returned title is
            # exact.  This keeps the fallback narrow enough to avoid accepting
            # similarly named books.
            if (
                author
                and provider_selected("open_library_metadata")
                and self.plugin_service.is_enabled("open_library_metadata")
            ):
                try:
                    title_only_candidates = self.search_candidates(
                        title=title,
                        author="",
                        isbn="",
                        cache_days=cache_days,
                    )
                except (MetadataLookupError, ValueError) as error:
                    failures.append(str(error))
                else:
                    for candidate in title_only_candidates:
                        if _normalise(title) != _normalise(candidate.title):
                            continue
                        author_matches = _author_is_compatible(
                            author,
                            candidate.author,
                        )
                        candidates.append(
                            replace(
                                candidate,
                                author=(
                                    candidate.author
                                    if author_matches
                                    else author
                                ),
                                confidence=max(candidate.confidence, 85),
                                confidence_reason=(
                                    "Exact title match; preserved the known author"
                                    if not author_matches
                                    else "Exact title and author match"
                                ),
                            )
                        )
            alternate_titles = (
                ()
                if any(
                    _candidate_is_reviewable(
                        candidate,
                        title=title,
                        author=author,
                    )
                    for candidate in candidates
                )
                else _bounded_title_aliases(title)
            )
            for alternate_title in alternate_titles:
                alternate_candidates: list[MetadataCandidate] = []
                if (
                    provider_selected("open_library_metadata")
                    and self.plugin_service.is_enabled("open_library_metadata")
                ):
                    try:
                        alternate_candidates.extend(
                            self.search_candidates(
                                title=alternate_title,
                                author=author,
                                isbn="",
                                cache_days=cache_days,
                            )
                        )
                    except (MetadataLookupError, ValueError) as error:
                        failures.append(str(error))
                if (
                    provider_selected("google_books_covers")
                    and self.plugin_service.is_enabled("google_books_covers")
                ):
                    try:
                        alternate_candidates.extend(
                            self._map_direct_cover(result)
                            for result in self.cover_search_service.search_google_books(
                                title=alternate_title,
                                author=author,
                                isbn="",
                                api_key=self.plugin_service.get_api_key(
                                    "google_books_covers"
                                ),
                            )
                        )
                    except (CoverSearchError, ValueError) as error:
                        failures.append(str(error))
                for candidate in alternate_candidates:
                    if not _title_matches(alternate_title, candidate.title):
                        continue
                    author_matches = _author_is_compatible(
                        author,
                        candidate.author,
                    )
                    exact_alternate_title = (
                        _normalise(alternate_title)
                        == _normalise(candidate.title)
                    )
                    if author and not author_matches and not exact_alternate_title:
                        continue
                    # Catalogues sometimes credit the underlying author or
                    # series creator where the ebook uses a pen name. An exact
                    # result from this deliberately bounded title retry is
                    # strong enough to retain the user's known author instead
                    # of discarding the correct edition and cover.
                    candidates.append(
                        replace(
                            candidate,
                            author=(
                                author
                                if author and not author_matches
                                else candidate.author
                            ),
                            confidence=max(candidate.confidence, 85),
                            confidence_reason=(
                                "Exact alternate published title match; "
                                "preserved the known author"
                                if author and not author_matches
                                else "Alternate published title and author match"
                            ),
                        )
                    )

            excerpt = (
                extract_epub_opening_excerpt(file_name)
                if not any(
                    _candidate_is_reviewable(
                        candidate,
                        title=title,
                        author=author,
                    )
                    for candidate in candidates
                )
                else ""
            )
            if (
                excerpt
                and provider_selected("google_books_covers")
                and self.plugin_service.is_enabled("google_books_covers")
            ):
                try:
                    excerpt_results = (
                        self.cover_search_service.search_google_books_excerpt(
                            excerpt=excerpt,
                            author=author,
                            api_key=self.plugin_service.get_api_key(
                                "google_books_covers"
                            ),
                        )
                    )
                    candidates.extend(
                        self._map_direct_cover(result)
                        for result in excerpt_results
                    )
                except (CoverSearchError, ValueError) as error:
                    failures.append(str(error))
            if (
                excerpt
                and provider_selected("open_library_metadata")
                and self.plugin_service.is_enabled("open_library_metadata")
            ):
                try:
                    candidates.extend(
                        self.search_open_library_excerpt(
                            excerpt=excerpt,
                            author=author,
                        )
                    )
                except (MetadataLookupError, ValueError) as error:
                    failures.append(str(error))
            if (
                not any(
                    _candidate_is_reviewable(
                        candidate,
                        title=title,
                        author=author,
                    )
                    for candidate in candidates
                )
                and provider_selected("open_library_metadata")
                and self.plugin_service.is_enabled("open_library_metadata")
                and self.plugin_service.is_enabled("serpapi_book_resolver")
            ):
                resolved_title = self.resolve_serpapi_containing_work(
                    title=title,
                    author=author,
                )
                searched_providers.append("SerpApi Search Resolver")
                if resolved_title:
                    try:
                        candidates.extend(
                            self.search_candidates(
                                title=resolved_title,
                                author=author,
                                cache_days=cache_days,
                            )
                        )
                    except (MetadataLookupError, ValueError) as error:
                        failures.append(str(error))
            if (
                not any(
                    _candidate_is_reviewable(
                        candidate,
                        title=title,
                        author=author,
                    )
                    for candidate in candidates
                )
                and provider_selected("open_library_metadata")
                and self.plugin_service.is_enabled("open_library_metadata")
            ):
                containing_title = self.resolve_wikipedia_containing_work(
                    title=title,
                    author=author,
                )
                searched_providers.append("Wikipedia Work Resolver")
                if containing_title:
                    try:
                        candidates.extend(
                            self.search_candidates(
                                title=containing_title,
                                author=author,
                                cache_days=cache_days,
                            )
                        )
                    except (MetadataLookupError, ValueError) as error:
                        failures.append(str(error))

            # A title-identification fallback above may have just
            # discovered the real edition (and its ISBN) for the first
            # time, since this whole branch only runs when nothing was
            # reviewable yet. Series enrichment gets one more chance using
            # the now-complete list, rather than the empty one it saw
            # before any fallback ran.
            candidates = self._enrich_series_from_isbn(
                candidates,
                title=title,
                author=author,
                provider_title=provider_title,
                provider_author=provider_author,
                cache_days=cache_days,
                provider_selected=provider_selected,
                failures=failures,
                searched_providers=searched_providers,
            )

        candidates = [
            candidate
            for candidate in candidates
            if _candidate_is_reviewable(
                candidate,
                title=title,
                author=author,
            )
        ]
        unique = _apply_local_series_hint(
            _enrich_matching_candidates(
                self._unique_candidates(candidates, require_cover=False)
            ),
            title=local_title,
            series=local_series,
            series_number=local_series_number,
        )
        if unique and not any(
            candidate.cover_url and candidate.confidence >= 75
            for candidate in unique
        ):
            # A provider can identify a book from broad search terms while its
            # cover endpoint needs the corrected title/author/ISBN returned by
            # that metadata match. Repeat only the cover phase with those
            # reviewed-quality terms so users do not have to press Find Covers
            # Only after every successful metadata lookup.
            cover_source_by_plugin = {
                "open_library_metadata": "open_library",
                "google_books_covers": "google_books",
                "hardcover_metadata": "hardcover",
                "comic_vine_metadata": "comic_vine",
                "apple_books_metadata": "apple_books",
                "amazon_metadata": "amazon",
                "isbndb_metadata": "isbndb",
                "gutenberg_metadata": "gutenberg",
                "big_book_metadata": "big_book",
                "openweb_ninja_metadata": "openweb_ninja",
            }
            cover_source = (
                cover_source_by_plugin.get(provider_plugin_id, "")
                if provider_plugin_id
                else "automatic"
            )
            if cover_source:
                best_match = max(unique, key=lambda item: item.confidence)
                try:
                    fallback_covers = self.search_cover_candidates(
                        source_id=cover_source,
                        title=best_match.title,
                        author=best_match.author,
                        isbn=best_match.isbn,
                        # These are already corrected provider terms. Do not
                        # let the original weak filename override them again.
                        file_name="",
                        cache_days=cache_days,
                        include_open_library=include_open_library,
                    )
                except (MetadataLookupError, ValueError):
                    fallback_covers = ()
                if fallback_covers:
                    unique = _apply_local_series_hint(
                        _enrich_matching_candidates(
                            self._unique_candidates(
                                [*unique, *fallback_covers],
                                require_cover=False,
                            )
                        ),
                        title=local_title,
                        series=local_series,
                        series_number=local_series_number,
                    )
        self.last_search_report = ProviderSearchReport(
            searched_providers=tuple(searched_providers),
            failed_providers=tuple(failed_providers),
            cover_providers=tuple(
                dict.fromkeys(
                    candidate.provider_name
                    for candidate in unique
                    if candidate.cover_url and candidate.confidence >= 75
                )
            ),
            failure_details=tuple(dict.fromkeys(failures)),
        )
        attempted_provider_names = set(searched_providers)
        failed_provider_names = set(failed_providers)
        if (
            not unique
            and failures
            and attempted_provider_names
            and attempted_provider_names <= failed_provider_names
        ):
            raise MetadataLookupError(" ".join(dict.fromkeys(failures)))
        return tuple(
            sorted(unique, key=lambda item: item.confidence, reverse=True)
        )

    def search_cover_candidates(
        self,
        *,
        source_id: str,
        title: str = "",
        author: str = "",
        isbn: str = "",
        file_name: str = "",
        cache_days: int = 30,
        include_open_library: bool = True,
        _retry_without_isbn: bool = True,
        _retry_without_author: bool = True,
    ) -> tuple[MetadataCandidate, ...]:
        """Search direct cover providers without relying on Calibre."""
        terms = self.prepare_search_terms(
            title=title,
            author=author,
            isbn=isbn,
            file_name=file_name,
        )
        title, author, isbn = terms.title, terms.author, terms.isbn
        comic_issue_number = terms.comic_issue_number
        comic_publisher = terms.comic_publisher
        is_comic_file = _is_comic_file(file_name)
        provider_plugins = {
            "open_library": "open_library_metadata",
            "google_books": "google_books_covers",
            "hardcover": "hardcover_metadata",
            "comic_vine": "comic_vine_metadata",
            "apple_books": "apple_books_metadata",
            "amazon": "amazon_metadata",
            "goodreads": "goodreads_metadata",
            "isbndb": "isbndb_metadata",
            "gutenberg": "gutenberg_metadata",
            "big_book": "big_book_metadata",
            "openweb_ninja": "openweb_ninja_metadata",
            "booktopia": "booktopia_metadata",
        }
        if source_id not in {"automatic", *provider_plugins}:
            raise ValueError("Choose an automatic cover source.")

        candidates: list[MetadataCandidate] = []
        failures: list[str] = []
        if source_id == "automatic":
            selected_sources = [
                provider_id
                for provider_id, plugin_id in provider_plugins.items()
                if include_open_library or provider_id != "open_library"
                if provider_id != "comic_vine" or is_comic_file
                if (
                    self.plugin_service is None
                    and provider_id in {"open_library", "google_books"}
                )
                or (
                    self.plugin_service is not None
                    and self.plugin_service.is_enabled(plugin_id)
                )
            ]
            if not selected_sources:
                raise MetadataLookupError(
                    "No automatic cover plugins are active. Open Plugins, "
                    "install a cover provider, then enable it."
                )
        else:
            if source_id == "comic_vine" and not is_comic_file:
                raise MetadataLookupError(
                    "Comic Vine is only used for CBR and CBZ comic files."
                )
            selected_sources = [source_id]
            plugin_id = provider_plugins[source_id]
            if (
                self.plugin_service is not None
                and not self.plugin_service.is_enabled(plugin_id)
            ):
                raise MetadataLookupError(
                    "That cover plugin is not active. Open Plugins, install "
                    "it, then choose Enable."
                )

        if "open_library" in selected_sources:
            try:
                candidates.extend(
                    self.search_candidates(
                        title=title,
                        author=author,
                        isbn=isbn,
                        cache_days=cache_days,
                        provider_plugin_id="open_library_metadata",
                    )
                )
            except MetadataLookupError as error:
                failures.append(str(error))
                if source_id != "automatic":
                    raise

        if "google_books" in selected_sources:
            try:
                direct_results = self.cover_search_service.search_google_books(
                    title=title,
                    author=author,
                    isbn=isbn,
                    api_key=(
                        self.plugin_service.get_api_key(
                            "google_books_covers"
                        )
                        if self.plugin_service is not None
                        else ""
                    ),
                )
                candidates.extend(
                    self._map_direct_cover(result)
                    for result in direct_results
                )
            except CoverSearchError as error:
                failures.append(str(error))
                if source_id != "automatic":
                    raise MetadataLookupError(str(error)) from error

        if "apple_books" in selected_sources:
            try:
                direct_results = (
                    self.cover_search_service.search_apple_books(
                        title=title,
                        author=author,
                        isbn=isbn,
                    )
                )
                candidates.extend(
                    self._map_direct_cover(result)
                    for result in direct_results
                )
            except CoverSearchError as error:
                failures.append(str(error))
                if source_id != "automatic":
                    raise MetadataLookupError(str(error)) from error

        if "isbndb" in selected_sources:
            try:
                direct_results = self.cover_search_service.search_isbndb(
                    title=title,
                    author=author,
                    isbn=isbn,
                    api_key=(
                        self.plugin_service.get_api_key("isbndb_metadata")
                        if self.plugin_service is not None
                        else ""
                    ),
                )
                candidates.extend(
                    self._map_direct_cover(result)
                    for result in direct_results
                )
            except CoverSearchError as error:
                failures.append(str(error))
                if source_id != "automatic":
                    raise MetadataLookupError(str(error)) from error

        if "hardcover" in selected_sources:
            try:
                candidates.extend(
                    self._search_hardcover(
                        title=title,
                        author=author,
                        isbn=isbn,
                    )
                )
            except (RemoteProviderError, ValueError) as error:
                failures.append(str(error))
                if source_id != "automatic":
                    raise MetadataLookupError(str(error)) from error

        if "comic_vine" in selected_sources:
            try:
                candidates.extend(
                    self._search_comic_vine(
                        title=title,
                        author=author,
                        isbn=isbn,
                        issue_number=comic_issue_number,
                        publisher=comic_publisher,
                    )
                )
            except (RemoteProviderError, ValueError) as error:
                failures.append(str(error))
                if source_id != "automatic":
                    raise MetadataLookupError(str(error)) from error

        for (
            provider_id,
            method_name,
            plugin_id,
            uses_key,
        ) in (
            (
                "amazon",
                "search_amazon",
                "amazon_metadata",
                False,
            ),
            (
                "goodreads",
                "search_goodreads",
                "goodreads_metadata",
                False,
            ),
            (
                "gutenberg",
                "search_gutenberg",
                "gutenberg_metadata",
                False,
            ),
            (
                "big_book",
                "search_big_book",
                "big_book_metadata",
                True,
            ),
            (
                "openweb_ninja",
                "search_openweb_ninja",
                "openweb_ninja_metadata",
                True,
            ),
            ("booktopia", "search_booktopia", "booktopia_metadata", False),
        ):
            if provider_id not in selected_sources:
                continue
            try:
                candidates.extend(
                    self._search_remote_provider(
                        method_name=method_name,
                        plugin_id=plugin_id if uses_key else "",
                        title=title,
                        author=author,
                        isbn=isbn,
                    )
                )
                if self.plugin_service is not None:
                    self.plugin_service.report_provider_health(
                        plugin_id,
                        "healthy",
                        "The provider responded and its expected result format was readable.",
                    )
            except (RemoteProviderError, ValueError) as error:
                failures.append(str(error))
                if self.plugin_service is not None:
                    self.plugin_service.report_provider_health(
                        plugin_id,
                        getattr(error, "health_status", "unavailable"),
                        getattr(error, "diagnostic", str(error)),
                    )
                if source_id != "automatic":
                    raise MetadataLookupError(str(error)) from error

        unique = self._unique_candidates(candidates, require_cover=True)
        has_usable_cover = any(
            candidate.cover_url and candidate.confidence >= 75
            for candidate in unique
        )
        if not has_usable_cover and isbn and _retry_without_isbn:
            # An exact edition can have useful metadata but no jacket image.
            # Low-confidence distractors are not usable covers and must not
            # suppress this retry. Search the already-cleaned title and author
            # across the same active providers so another edition can supply
            # the cover.
            try:
                return self.search_cover_candidates(
                    source_id=source_id,
                    title=title,
                    author=author,
                    isbn="",
                    file_name="",
                    cache_days=cache_days,
                        include_open_library=include_open_library,
                        _retry_without_isbn=False,
                        _retry_without_author=_retry_without_author,
                    )
            except MetadataLookupError:
                pass
        if not has_usable_cover and author and _retry_without_author:
            # Older catalogues can credit the underlying writer while the
            # ebook and another provider use a house name or pen name. A final
            # exact-title cover pass avoids letting that author discrepancy
            # hide an otherwise valid jacket image.
            try:
                return self.search_cover_candidates(
                    source_id=source_id,
                    title=title,
                    author="",
                    isbn="",
                    file_name="",
                    cache_days=cache_days,
                    include_open_library=include_open_library,
                    _retry_without_isbn=False,
                    _retry_without_author=False,
                )
            except MetadataLookupError:
                pass
        if not unique and failures and len(failures) == len(selected_sources):
            raise MetadataLookupError(
                " ".join(dict.fromkeys(failures))
            )
        return tuple(unique)

    def _search_hardcover(
        self,
        *,
        title: str,
        author: str,
        isbn: str,
    ) -> tuple[MetadataCandidate, ...]:
        plugin_id = "hardcover_metadata"
        api_key = (
            self.plugin_service.get_api_key(plugin_id)
            if self.plugin_service is not None
            else ""
        )
        try:
            results = self.remote_provider_service.search_hardcover(
                api_key=api_key,
                title=title,
                author=author,
                isbn=isbn,
            )
        except (RemoteProviderError, ValueError) as error:
            self._report_api_provider_failure(plugin_id, error)
            raise
        self._report_api_provider_success(plugin_id)
        return tuple(self._map_remote_candidate(result) for result in results)

    def _search_comic_vine(
        self,
        *,
        title: str,
        author: str,
        isbn: str,
        issue_number: str = "",
        publisher: str = "",
    ) -> tuple[MetadataCandidate, ...]:
        plugin_id = "comic_vine_metadata"
        api_key = (
            self.plugin_service.get_api_key(plugin_id)
            if self.plugin_service is not None
            else ""
        )
        try:
            results = self.remote_provider_service.search_comic_vine(
                api_key=api_key,
                title=title,
                author=author,
                isbn=isbn,
                issue_number=issue_number,
                publisher=publisher,
            )
        except (RemoteProviderError, ValueError) as error:
            self._report_api_provider_failure(plugin_id, error)
            raise
        self._report_api_provider_success(plugin_id)
        return tuple(self._map_remote_candidate(result) for result in results)

    def _report_api_provider_success(self, plugin_id: str) -> None:
        if self.plugin_service is not None:
            self.plugin_service.report_provider_health(
                plugin_id,
                "healthy",
                "The provider API responded successfully.",
            )

    def _report_api_provider_failure(
        self,
        plugin_id: str,
        error: RemoteProviderError | ValueError,
    ) -> None:
        if self.plugin_service is not None:
            self.plugin_service.report_provider_health(
                plugin_id,
                getattr(error, "health_status", "unavailable"),
                getattr(error, "diagnostic", str(error)),
            )

    def check_provider_connection(self, plugin_id: str) -> tuple[str, str]:
        """Run one discardable probe search to check a single provider now.

        Several providers (Open Library, Google Books, Apple Books,
        ISBNdb) previously only had their Provider Check status updated
        as a side effect of a real book search; this always reports a
        result, using the same well-known probe title every time so a
        real catalogue book is never needed. The probe result itself is
        never returned or shown -- only whether the provider responded.
        """
        if self.plugin_service is None:
            raise MetadataLookupError("No plugin service is configured.")
        plugin = next(
            (
                record
                for record in self.plugin_service.list_plugins()
                if record.plugin_id == plugin_id
            ),
            None,
        )
        if plugin is None:
            raise MetadataLookupError("Unknown plugin.")
        if not {"metadata_provider", "cover_provider"} & set(
            plugin.capabilities
        ):
            raise MetadataLookupError(
                "This plugin does not offer a metadata or cover search to "
                "check."
            )
        if not plugin.installed or not plugin.enabled:
            raise MetadataLookupError(
                "Enable this plugin before checking its connection."
            )
        checked_before = plugin.provider_health_checked_at
        error_status = ""
        error_message = ""
        try:
            if plugin_id == "comic_vine_metadata":
                self.search_enabled_candidates(
                    file_name=PROVIDER_CHECK_COMIC_FILE_NAME,
                    provider_plugin_id=plugin_id,
                )
            else:
                self.search_enabled_candidates(
                    title=PROVIDER_CHECK_PROBE_TITLE,
                    author=PROVIDER_CHECK_PROBE_AUTHOR,
                    isbn=PROVIDER_CHECK_PROBE_ISBN,
                    provider_plugin_id=plugin_id,
                )
        except (
            MetadataLookupError,
            RemoteProviderError,
            CoverSearchError,
        ) as error:
            error_status = getattr(error, "health_status", "unavailable")
            error_message = getattr(error, "diagnostic", str(error))

        # Several providers already self-report their real status deep
        # inside search_enabled_candidates (a per-marketplace or
        # per-provider failure there is far more specific than whatever
        # exception, if any, ends up propagating out of the whole
        # multi-provider search). Trust that self-report when present
        # instead of overwriting it with a less specific guess.
        refreshed = next(
            (
                record
                for record in self.plugin_service.list_plugins()
                if record.plugin_id == plugin_id
            ),
            None,
        )
        if (
            refreshed is not None
            and refreshed.provider_health_checked_at
            and refreshed.provider_health_checked_at != checked_before
        ):
            return (
                refreshed.provider_health,
                refreshed.provider_health_message,
            )
        if error_status:
            self.plugin_service.report_provider_health(
                plugin_id, error_status, error_message
            )
            return error_status, error_message
        message = "The provider responded to a manual connection check."
        self.plugin_service.report_provider_health(
            plugin_id, "healthy", message
        )
        return "healthy", message

    def _search_remote_provider(
        self,
        *,
        method_name: str,
        plugin_id: str,
        title: str,
        author: str,
        isbn: str,
    ) -> tuple[MetadataCandidate, ...]:
        method = getattr(self.remote_provider_service, method_name)
        arguments = {
            "title": title,
            "author": author,
            "isbn": isbn,
        }
        if plugin_id:
            arguments["api_key"] = (
                self.plugin_service.get_api_key(plugin_id)
                if self.plugin_service is not None
                else ""
            )
        return tuple(
            self._map_remote_candidate(result)
            for result in method(**arguments)
        )

    @staticmethod
    def _map_remote_candidate(
        result: RemoteMetadataResult,
    ) -> MetadataCandidate:
        return MetadataCandidate(
            title=result.title,
            author=result.author,
            isbn=result.isbn,
            publisher=result.publisher,
            language=result.language,
            published_date=result.published_date,
            cover_id=None,
            work_key=result.source_url,
            confidence=result.confidence,
            confidence_reason=result.confidence_reason,
            provider_name=result.provider_name,
            remote_cover_url=result.cover_url,
            source_url=result.source_url,
            description=result.description,
            series=result.series,
            series_number=result.series_number,
            series_group=result.series_group,
            series_group_number=result.series_group_number,
            provider_rating=result.provider_rating,
            rating_count=result.rating_count,
        )

    @staticmethod
    def _unique_candidates(
        candidates: list[MetadataCandidate],
        *,
        require_cover: bool,
    ) -> list[MetadataCandidate]:
        unique: list[MetadataCandidate] = []
        seen: set[tuple[str, ...]] = set()
        for candidate in candidates:
            if require_cover and not candidate.cover_url:
                continue
            key = (
                (candidate.cover_url,)
                if require_cover
                else (
                    candidate.provider_name.casefold(),
                    candidate.title.casefold(),
                    candidate.isbn.casefold(),
                    candidate.cover_url,
                )
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique

    def download_cover(
        self,
        candidate: MetadataCandidate,
        *,
        book_id: int,
    ) -> Path:
        """Download one explicitly selected cover into Twano-owned storage."""
        return self._download_cover_to(
            candidate,
            folder_name="covers",
            file_stem=f"book-{int(book_id)}",
        )

    def download_cover_preview(
        self,
        candidate: MetadataCandidate,
        *,
        book_id: int,
    ) -> Path:
        """Cache a found cover for display without selecting it for Apply."""
        digest = sha256(candidate.cover_url.encode("utf-8")).hexdigest()[:12]
        folder = self.database.database_path.parent / "cover-previews"
        for suffix in (".jpg", ".png"):
            cached = folder / f"book-{int(book_id)}-{digest}{suffix}"
            if cached.is_file() and cached.stat().st_size:
                return cached
        return self._download_cover_to(
            candidate,
            folder_name="cover-previews",
            file_stem=f"book-{int(book_id)}-{digest}",
        )

    def _download_cover_to(
        self,
        candidate: MetadataCandidate,
        *,
        folder_name: str,
        file_stem: str,
    ) -> Path:
        """Download and validate one provider cover into app-owned storage."""
        provider_plugins = {
            "Open Library": "open_library_metadata",
            "Google Books": "google_books_covers",
            "Hardcover": "hardcover_metadata",
            "Comic Vine": "comic_vine_metadata",
            "Apple Books": "apple_books_metadata",
            "ISBNdb": "isbndb_metadata",
            "Project Gutenberg": "gutenberg_metadata",
            "Big Book API": "big_book_metadata",
            "OpenWeb Ninja": "openweb_ninja_metadata",
            "Amazon AU": "amazon_metadata",
            "Amazon US": "amazon_metadata",
            "Amazon UK": "amazon_metadata",
            "Amazon CA": "amazon_metadata",
            "Booktopia": "booktopia_metadata",
        }
        plugin_id = provider_plugins.get(candidate.provider_name)
        if (
            plugin_id
            and self.plugin_service is not None
            and not self.plugin_service.is_enabled(plugin_id)
        ):
            raise MetadataLookupError(
                f"{candidate.provider_name} is not enabled. Open Plugins, "
                "install the provider, then choose Enable."
            )
        if not candidate.cover_url:
            raise ValueError("That result does not include a cover.")
        request = Request(
            candidate.cover_url,
            headers={
                "User-Agent": OPEN_LIBRARY_USER_AGENT,
                "Accept": "image/jpeg,image/png",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                content_type = str(response.headers.get("Content-Type", ""))
                data = response.read(10 * 1024 * 1024 + 1)
        except (
            HTTPError,
            URLError,
            TimeoutError,
            socket.timeout,
            OSError,
        ) as error:
            raise MetadataLookupError(
                f"{candidate.provider_name} could not download that cover. "
                "Choose another result or select a cover from this computer."
            ) from error
        if len(data) > 10 * 1024 * 1024:
            raise MetadataLookupError("The selected cover is unexpectedly large.")
        if not data or not content_type.casefold().startswith("image/"):
            raise MetadataLookupError(
                f"{candidate.provider_name} returned no usable cover."
            )

        cover_folder = self.database.database_path.parent / folder_name
        cover_folder.mkdir(parents=True, exist_ok=True)
        suffix = ".png" if "png" in content_type.casefold() else ".jpg"
        target = cover_folder / f"{file_stem}{suffix}"
        temporary = target.with_suffix(target.suffix + ".partial")
        try:
            temporary.write_bytes(data)
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    @staticmethod
    def _map_direct_cover(
        result: DirectCoverResult,
    ) -> MetadataCandidate:
        return MetadataCandidate(
            title=result.title,
            author=result.author,
            isbn=result.isbn,
            publisher=result.publisher,
            language=result.language,
            published_date=result.published_date,
            cover_id=None,
            work_key=result.source_url,
            confidence=result.confidence,
            confidence_reason=result.confidence_reason,
            provider_name=result.provider_name,
            remote_cover_url=result.cover_url,
            source_url=result.source_url,
            description=result.description,
            series=result.series,
            series_number=result.series_number,
            series_group=result.series_group,
            series_group_number=result.series_group_number,
            provider_rating=result.provider_rating,
            rating_count=result.rating_count,
        )

    def _load_persistent_cache(
        self,
        key: tuple[str, str, str],
        *,
        cache_days: int,
    ) -> tuple[MetadataCandidate, ...] | None:
        """Read one unexpired provider result without writing at startup."""
        if cache_days <= 0:
            return None
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("_schema_version")
                != METADATA_CACHE_SCHEMA_VERSION
            ):
                return None
            entry = payload.get(_cache_key(key), {})
            stored_at = datetime.fromisoformat(str(entry["stored_at"]))
            if stored_at.tzinfo is None:
                stored_at = stored_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - stored_at > timedelta(
                days=min(int(cache_days), 365)
            ):
                return None
            candidates = tuple(
                MetadataCandidate(**item)
                for item in entry.get("candidates", ())
                if isinstance(item, dict)
            )
        except (
            FileNotFoundError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ):
            return None
        # Do not treat an earlier no-result response as authoritative. Online
        # catalogues and transient provider availability change, and spelling
        # corrections must be allowed to reach the provider immediately.
        return candidates or None

    def _save_persistent_cache(
        self,
        key: tuple[str, str, str],
        candidates: tuple[MetadataCandidate, ...],
        *,
        cache_days: int,
    ) -> None:
        """Atomically store a completed lookup when retention is enabled."""
        if cache_days <= 0 or not candidates:
            return
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            payload = {}
        if (
            not isinstance(payload, dict)
            or payload.get("_schema_version")
            != METADATA_CACHE_SCHEMA_VERSION
        ):
            payload = {"_schema_version": METADATA_CACHE_SCHEMA_VERSION}
        payload[_cache_key(key)] = {
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "candidates": [asdict(candidate) for candidate in candidates],
        }
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(".json.partial")
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary.replace(self.cache_path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def build_plan(
        self,
        book_id: int,
        values: dict[str, object],
        *,
        organise_file: bool = False,
    ) -> OperationRecord:
        """Persist a human-readable preview without changing the catalogue."""
        plan = self.protection_service.build_metadata_update_plan(
            book_id,
            values,
            organise_file=organise_file,
        )
        return self.protection_service.record_change_plan(plan)

    def proposed_file_path(
        self,
        book_id: int,
        values: dict[str, object],
        *,
        organise_file: bool,
    ) -> Path:
        """Return the physical path that Apply would use, without changing it."""
        row = self.database.get_book_by_id(int(book_id))
        if row is None:
            raise ValueError(f"Unknown book ID: {book_id}")
        if not organise_file:
            return Path(str(row["file_path"])).resolve()
        return self.protection_service.preview_metadata_destination(
            book_id,
            values,
        )

    def approve_and_apply(
        self,
        operation_id: int,
        *,
        policy: BackupPolicy,
        protection_mode: ProtectionMode,
    ) -> OperationRecord:
        """Approve and execute the exact visible metadata preview."""
        operation = self.protection_service.get_operation(operation_id)
        confirmation = PlanConfirmation(
            plan_token=operation.plan.plan_token,
            approved=True,
            confirmer="metadata_studio",
        )
        approved = self.protection_service.approve_change_plan(
            operation_id,
            confirmation,
            current_basis_token=self.protection_service.current_basis_token(
                operation
            ),
        )
        return self.protection_service.apply_approved_operation(
            approved.operation_id,
            policy,
            protection_mode,
        )

    @staticmethod
    def _map_candidate(
        document: dict[str, Any],
        *,
        wanted_title: str,
        wanted_author: str,
        wanted_isbn: str,
    ) -> MetadataCandidate | None:
        title, title_series, title_number = split_title_series(
            _first_text(document.get("title"))
        )
        if not title:
            return None
        authors = _texts(document.get("author_name"))
        isbns = _texts(document.get("isbn"))
        publishers = _texts(document.get("publisher"))
        languages = _texts(document.get("language"))
        wanted_title_key = _normalise(wanted_title)
        wanted_author_key = _normalise(wanted_author)
        exact_isbn = bool(
            wanted_isbn
            and "".join(wanted_isbn.split()) in {
                "".join(value.split()) for value in isbns
            }
        )
        exact_title = bool(
            wanted_title_key and _normalise(title) == wanted_title_key
        )
        author_match = bool(
            wanted_author_key
            and any(wanted_author_key in _normalise(value) for value in authors)
        )
        if exact_isbn:
            confidence, reason = 100, "Exact ISBN match"
        elif exact_title and author_match:
            confidence, reason = 90, "Exact title and author match"
        elif exact_title:
            confidence, reason = 75, "Exact title match"
        else:
            confidence, reason = 60, "Possible title or author match"
        raw_cover = document.get("cover_i")
        try:
            cover_id = int(raw_cover) if raw_cover is not None else None
        except (TypeError, ValueError):
            cover_id = None
        published = (
            _first_text(document.get("first_publish_date"))
            or _first_text(document.get("first_publish_year"))
        )
        series, series_number = title_series, title_number
        for value in _texts(document.get("series")):
            parsed_series, parsed_number = parse_series_label(value)
            if parsed_series:
                series, series_number = parsed_series, parsed_number
                break
        return MetadataCandidate(
            title=title,
            author=", ".join(authors),
            isbn=_preferred_isbn(isbns, wanted_isbn),
            publisher=publishers[0] if publishers else "",
            language=languages[0] if languages else "",
            published_date=published,
            cover_id=cover_id,
            work_key=_first_text(document.get("key")),
            confidence=confidence,
            confidence_reason=reason,
            description=_open_library_description(document),
            series=series,
            series_number=series_number,
        )


def _texts(value: Any) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple)):
        return [
            cleaned
            for item in value
            if (cleaned := str(item).strip())
        ]
    if value is None:
        return []
    cleaned = str(value).strip()
    return [cleaned] if cleaned else []


def _merge_open_library_edition(
    document: dict[str, Any],
    edition: dict[str, Any],
) -> dict[str, Any]:
    """Fill search-document gaps from an exact Open Library ISBN edition."""
    merged = dict(document)
    if not _texts(merged.get("series")):
        merged["series"] = _texts(edition.get("series"))
    if merged.get("cover_i") in (None, ""):
        covers = _texts(edition.get("covers"))
        if covers:
            merged["cover_i"] = covers[0]
    if not _texts(merged.get("publisher")):
        merged["publisher"] = _texts(edition.get("publishers"))
    if not _first_text(merged.get("first_publish_date")):
        merged["first_publish_date"] = _first_text(
            edition.get("publish_date")
        )
    if not _texts(merged.get("language")):
        language_codes = []
        for language in edition.get("languages", ()):
            if not isinstance(language, dict):
                continue
            key = str(language.get("key") or "").strip()
            if key:
                language_codes.append(key.rsplit("/", 1)[-1])
        if language_codes:
            merged["language"] = language_codes
    return merged


def _enrich_exact_isbn_series(
    candidates: list[MetadataCandidate],
    *,
    isbn: str,
    edition: dict[str, Any] | None = None,
    series_hint: tuple[str, str] | None = None,
) -> list[MetadataCandidate]:
    """Fill series across exact-ISBN records before normal result filtering."""
    wanted_isbn = _normalised_isbn(isbn)
    if not wanted_isbn:
        return candidates
    series_source = next(
        (
            candidate
            for candidate in candidates
            if (
                candidate.series
                and _normalised_isbn(candidate.isbn) == wanted_isbn
            )
        ),
        None,
    )
    series = series_source.series if series_source is not None else ""
    series_number = (
        series_source.series_number if series_source is not None else ""
    )
    if series_hint:
        hinted_series, hinted_number = series_hint
        series = series or hinted_series
        series_number = series_number or hinted_number
    if not series and edition:
        for label in _texts(edition.get("series")):
            series, series_number = parse_series_label(label)
            if series:
                break
    if not series:
        return candidates
    return [
        (
            replace(
                candidate,
                series=candidate.series or series,
                series_number=candidate.series_number or series_number,
            )
            if (
                (not candidate.series or not candidate.series_number)
                and _normalised_isbn(candidate.isbn) == wanted_isbn
            )
            else candidate
        )
        for candidate in candidates
    ]


def _first_text(value: Any) -> str:
    values = _texts(value)
    return values[0] if values else ""


def _ordinal_number(value: str) -> str:
    """Convert a small explicit ordinal from provider prose to digits."""
    cleaned = str(value or "").strip().lower()
    digit_match = re.fullmatch(r"(?P<number>\d+)(?:st|nd|rd|th)?", cleaned)
    if digit_match is not None:
        return digit_match.group("number")
    return {
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
        "thirteenth": "13",
        "fourteenth": "14",
        "fifteenth": "15",
        "sixteenth": "16",
        "seventeenth": "17",
        "eighteenth": "18",
        "nineteenth": "19",
        "twentieth": "20",
    }.get(cleaned, "")


def _open_library_description(document: dict[str, Any]) -> str:
    """Return Open Library's short synopsis when search results provide it."""
    value = document.get("first_sentence")
    if isinstance(value, dict):
        value = value.get("value")
    return " ".join(_first_text(value).split())


def _normalise(value: str) -> str:
    return " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in value.casefold()
        ).split()
    )


_SERIES_ORDINAL_COMPOUND_RE = re.compile(
    r"\bis\s+the\s+(?P<book>[a-z0-9-]+)\s+book\s+and\s+"
    r"(?P<novel>[a-z0-9-]+)\s+novel(?:\s+published)?\s+in\s+the\s+"
    r"(?P<series>[^.]{2,100}?)\s+series\b",
    flags=re.IGNORECASE,
)
_SERIES_ORDINAL_SIMPLE_RE = re.compile(
    r"\bis\s+the\s+(?P<number>[a-z0-9-]+)\s+(?:book|novel)"
    r"(?:\s+published)?\s+in\s+the\s+"
    r"(?P<series>[^.]{2,100}?)\s+series\b",
    flags=re.IGNORECASE,
)
_SERIES_PARENTHETICAL_RE = re.compile(
    r"\((?P<series>[A-Z][A-Za-z0-9&'’.\- ]{2,60}?)"
    r"(?:,|\s+(?:No\.?|Number|#))\s*(?P<number>\d{1,3})\)",
    flags=re.IGNORECASE,
)
# A "(Series Name series, #N)" style annotation names the series and then
# redundantly restates the word "series" before the number marker — unlike
# the two prose regexes below, the parenthetical pattern's boundary can't
# exclude that word up front, so it is stripped afterwards. Left in, it
# would organise this one book into its own "X series" folder instead of
# the shared "X" folder every other volume uses.
_TRAILING_SERIES_WORD_RE = re.compile(r"\s+series$", flags=re.IGNORECASE)


def _wikidata_claim_target_id(claim: Any) -> str:
    """Return the target item id a Wikidata claim points to, if any."""
    mainsnak = claim.get("mainsnak", {}) if isinstance(claim, dict) else {}
    datavalue = mainsnak.get("datavalue", {}) if isinstance(mainsnak, dict) else {}
    value = datavalue.get("value", {}) if isinstance(datavalue, dict) else {}
    return str(value.get("id", "")) if isinstance(value, dict) else ""


_SEARCH_RESULT_TITLE_SUFFIX_RE = re.compile(
    r"\s*[-|:–—]\s*"
    r"(Goodreads|Amazon(?:\.com)?|Barnes\s*&\s*Noble|Book\s*Depository|"
    r"Wikipedia|Everand|Scribd|Kobo|Google\s*Books|Apple\s*Books)\b.*$",
    flags=re.IGNORECASE,
)


_TITLE_STOPWORDS = frozenset({"a", "an", "the"})


def _strip_stopwords(value: str) -> str:
    """Drop stray articles so a single a/an/the difference still matches.

    A catalogue title can carry one extra or missing article compared to
    the officially published title (e.g. "The Mystery of the Death Trap
    Mine" vs the real "The Mystery of Death Trap Mine"). Comparing with
    these words removed lets that kind of near-exact title still be
    recognised without loosening the match enough to accept an
    unrelated book.
    """
    return " ".join(
        word for word in value.split() if word not in _TITLE_STOPWORDS
    )


_SEARCH_RESULT_COUNT_SUFFIX_RE = re.compile(
    r"\s*\(\d+\s*results?\)\s*$",
    flags=re.IGNORECASE,
)


def _clean_search_result_title(value: str) -> str:
    """Strip a trailing site name or listing-count a search result adds.

    A page title from a general web index commonly looks like ``The
    Mystery of the Death Trap Mine - Goodreads`` or a listing site's own
    ``Title (27 results)`` pagination marker. Only these known patterns
    are stripped so real title punctuation is not damaged.
    """
    cleaned = _SEARCH_RESULT_TITLE_SUFFIX_RE.sub("", value).strip()
    return _SEARCH_RESULT_COUNT_SUFFIX_RE.sub("", cleaned).strip()


def _strip_trailing_author_attribution(title: str, author: str) -> str:
    """Strip a trailing "by <author>" a search result title often adds.

    Only the exact author being searched for is matched, so this cannot
    accidentally truncate a real title that happens to contain "by".
    """
    author_tokens = [token for token in _normalise(author).split() if token]
    if not author_tokens:
        return title
    token_pattern = r"[\s.]*".join(
        re.escape(token) for token in author_tokens
    )
    pattern = re.compile(
        rf"\s*[-|:]?\s*by\s+{token_pattern}\.?\s*$",
        flags=re.IGNORECASE,
    )
    return pattern.sub("", title).strip()


def _passage_matches(excerpt: str, sentence: str) -> bool:
    """Return true only for a distinctive ordered phrase shared by both."""
    excerpt_tokens = _normalise(excerpt).split()
    sentence_tokens = _normalise(sentence).split()
    if len(excerpt_tokens) < 10 or len(sentence_tokens) < 10:
        return False
    window = min(16, len(sentence_tokens))
    return " ".join(sentence_tokens[:window]) in " ".join(excerpt_tokens)


def _preferred_isbn(values: list[str], wanted_isbn: str = "") -> str:
    """Prefer the requested identifier, then an ISBN-13, then an ISBN-10."""
    cleaned = [
        "".join(
            character
            for character in value
            if character.isdigit() or character.casefold() == "x"
        )
        for value in values
    ]
    cleaned = [value for value in cleaned if value]
    wanted_key = "".join(
        character
        for character in wanted_isbn
        if character.isdigit() or character.casefold() == "x"
    )
    if wanted_key and wanted_key in cleaned:
        return wanted_key
    isbn_13 = next((value for value in cleaned if len(value) == 13), "")
    if isbn_13:
        return isbn_13
    isbn_10 = next((value for value in cleaned if len(value) == 10), "")
    if isbn_10:
        return _isbn_10_to_13(isbn_10) or isbn_10
    return cleaned[0] if cleaned else ""


def _isbn_10_to_13(isbn: str) -> str:
    """Convert a valid-looking ISBN-10 to its ISBN-13 equivalent."""
    cleaned = "".join(
        character
        for character in str(isbn)
        if character.isdigit() or character.casefold() == "x"
    )
    if len(cleaned) != 10 or not cleaned[:9].isdigit():
        return ""
    body = f"978{cleaned[:9]}"
    total = sum(
        int(character) * (1 if index % 2 == 0 else 3)
        for index, character in enumerate(body)
    )
    return f"{body}{(10 - total % 10) % 10}"


def _refined_provider_terms(
    *,
    title: str,
    author: str,
    isbn: str,
    candidates: list[MetadataCandidate],
) -> tuple[str, str, str]:
    """Use a strong first result to improve every later cover search."""
    strong = [
        candidate
        for candidate in candidates
        if candidate.confidence >= 75
    ]
    if not strong:
        return title, author, isbn
    best = max(strong, key=lambda candidate: candidate.confidence)
    return (
        best.title or title,
        best.author or author,
        isbn or best.isbn,
    )


def _enrich_matching_candidates(
    candidates: list[MetadataCandidate],
) -> list[MetadataCandidate]:
    """Fill blank fields from other strong results for the same book."""
    candidates = [_normalise_candidate_metadata(item) for item in candidates]
    enriched: list[MetadataCandidate] = []
    for candidate in candidates:
        related = [
            other
            for other in candidates
            if other.confidence >= 75
            and _same_candidate_work(candidate, other)
        ]
        ranked = sorted(
            related,
            key=lambda item: item.confidence,
            reverse=True,
        )

        def first_value(field: str) -> str:
            current = str(getattr(candidate, field) or "").strip()
            if current:
                return current
            return next(
                (
                    str(getattr(other, field) or "").strip()
                    for other in ranked
                    if str(getattr(other, field) or "").strip()
                ),
                "",
            )

        descriptions = [
            str(other.description or "").strip()
            for other in related
            if str(other.description or "").strip()
        ]
        enriched.append(
            replace(
                candidate,
                author=first_value("author"),
                isbn=first_value("isbn"),
                publisher=first_value("publisher"),
                language=first_value("language"),
                published_date=first_value("published_date"),
                description=(
                    max(descriptions, key=len)
                    if descriptions
                    else candidate.description
                ),
                series=first_value("series"),
                series_number=first_value("series_number"),
                series_group=first_value("series_group"),
                series_group_number=first_value("series_group_number"),
            )
        )
    return enriched


def _normalise_candidate_metadata(
    candidate: MetadataCandidate,
) -> MetadataCandidate:
    """Repair explicit provider metadata without making speculative guesses."""
    series, series_number = canonical_series_details(
        candidate.series,
        title=candidate.title,
        number=candidate.series_number,
    )
    inferred_series, inferred_number = series_from_description(
        candidate.description
    )
    if inferred_series and (
        not series or _normalise(series) == _normalise(inferred_series)
    ):
        series = series or inferred_series
        series_number = series_number or inferred_number
    series_group = str(candidate.series_group or "").strip()
    series_group_number = str(candidate.series_group_number or "").strip()
    if series and not series_group:
        series_group, known_group_number = known_series_group(series)
        series_group_number = series_group_number or known_group_number
    return replace(
        candidate,
        author=_clean_provider_author(candidate.author),
        published_date=clean_published_date(candidate.published_date),
        series=series,
        series_number=series_number,
        series_group=series_group,
        series_group_number=series_group_number,
    )


def _clean_provider_author(value: str) -> str:
    """Remove a duplicated trailing initials-only provider author fragment."""
    author = " ".join(str(value or "").split())
    match = re.fullmatch(
        r"(?P<name>.+?),\s*(?P<initials>(?:[A-Za-z][.]?\s*){1,4})",
        author,
    )
    if match is None:
        return author
    name = match.group("name").strip()
    initials = "".join(character for character in match.group("initials") if character.isalpha()).casefold()
    name_key = "".join(character for character in name if character.isalpha()).casefold()
    return name if len(initials) >= 2 and name_key.startswith(initials) else author


def _apply_local_series_hint(
    candidates: list[MetadataCandidate],
    *,
    title: str,
    series: str,
    series_number: str,
) -> list[MetadataCandidate]:
    """Keep an explicit embedded series/order when providers omit both."""
    if not title or not series or not series_number:
        return candidates
    title_key = _normalise(title)
    return [
        (
            replace(
                candidate,
                series=series,
                series_number=series_number,
            )
            if (
                not candidate.series.strip()
                and _normalise(candidate.title) == title_key
            )
            else candidate
        )
        for candidate in candidates
    ]


def _same_candidate_work(
    first: MetadataCandidate,
    second: MetadataCandidate,
) -> bool:
    first_title = _normalise(first.title)
    second_title = _normalise(second.title)
    if not first_title or first_title != second_title:
        return False
    first_isbn = _normalised_isbn(first.isbn)
    second_isbn = _normalised_isbn(second.isbn)
    if first_isbn and second_isbn and first_isbn == second_isbn:
        return True
    first_author = set(_normalise(first.author).split())
    second_author = set(_normalise(second.author).split())
    if first_author and second_author:
        return first_author == second_author
    return len(first_title.replace(" ", "")) >= 8


def _normalised_isbn(value: str) -> str:
    return "".join(
        character
        for character in str(value).casefold()
        if character.isdigit() or character == "x"
    )


def _comic_filename_search_terms(
    file_name: str,
) -> tuple[str, str, str] | None:
    """Extract a reusable series, issue and publisher pattern from CBR/CBZ."""
    filename = str(file_name).strip().replace("\\", "/").rsplit("/", 1)[-1]
    if not filename or "." not in filename:
        return None
    stem, extension = filename.rsplit(".", 1)
    if extension.casefold() not in {"cbr", "cbz"}:
        return None
    cleaned = " ".join(stem.replace("_", " ").split())
    match = re.fullmatch(
        r"(?:(?:\((?P<round>[^)]+)\)|\[(?P<square>[^\]]+)\])\s*)?"
        r"(?P<series>.+?)\s+(?:#\s*)?"
        r"(?P<issue>\d+(?:\.\d+)?[A-Za-z]?)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    publisher = " ".join(
        (match.group("round") or match.group("square") or "").split()
    )
    series = " ".join(match.group("series").strip(" -").split())
    issue_number = match.group("issue")
    if not series:
        return None

    publisher_aliases = {
        "frew": "Frew Publications",
    }
    publisher = publisher_aliases.get(
        _normalise(publisher),
        publisher,
    )
    series_aliases = {
        ("frew", "phantom"): "The Phantom",
        ("frew publications", "phantom"): "The Phantom",
    }
    series = series_aliases.get(
        (_normalise(publisher), _normalise(series)),
        series,
    )
    return series, issue_number, publisher


def _filename_search_terms(
    file_name: str,
    *,
    wanted_title: str = "",
    wanted_author: str = "",
) -> tuple[str, str]:
    filename = str(file_name).strip().replace("\\", "/").rsplit("/", 1)[-1]
    if not filename:
        return "", ""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    stem = " ".join(stem.replace("_", " ").split())
    if not stem:
        return "", ""
    segments = [
        _clean_filename_segment(segment)
        for segment in re.split(r"\s+(?:-|\u2013|\u2014)\s+", stem)
    ]
    segments = [segment for segment in segments if segment]
    if (
        len(segments) > 1
        and re.fullmatch(r"(?:18|19|20)\d{2}", segments[0])
    ):
        # Some collections prefix a filename with the publication year, for
        # example ``2006 - The Smelliest Day at the Zoo - Alan Rusbridger``.
        # A standalone four-digit segment is search noise, while a real title
        # such as ``2066 Election Day`` remains untouched because the year is
        # part of the same title segment.
        segments = segments[1:]
    if (
        len(segments) > 1
        and re.fullmatch(r"\d{1,3}", segments[0])
    ):
        # A common series layout is ``01 - Title - Author``.  The first
        # segment is an ordering number, not the book title.
        segments = segments[1:]
    if len(segments) >= 2:
        author_scores = [
            _author_likelihood(segment)
            for segment in segments
        ]
        if len(segments) > 2:
            best_author = max(
                range(len(segments)),
                key=lambda index: author_scores[index],
            )
            if author_scores[best_author] >= 2:
                title_index = (
                    len(segments) - 1 if best_author == 0 else 0
                )
                return (
                    _remove_leading_sequence_number(segments[title_index]),
                    _clean_author_candidate(segments[best_author]),
                )

        left, right = segments[0], segments[-1]
        left_author_score = author_scores[0]
        right_author_score = author_scores[-1]
        direct_score = right_author_score
        reverse_score = left_author_score
        if (
            _title_matches(left, wanted_title)
            and _author_matches(right, wanted_author)
        ):
            direct_score += 4
        if (
            _title_matches(right, wanted_title)
            and _author_matches(left, wanted_author)
        ):
            reverse_score += 4
        if right_author_score - left_author_score >= 2:
            direct_score += 4
        elif left_author_score - right_author_score >= 2:
            reverse_score += 4
        if reverse_score > direct_score:
            return (
                _remove_leading_sequence_number(right),
                _clean_author_candidate(left),
            )
        return (
            _remove_leading_sequence_number(left),
            _clean_author_candidate(right),
        )
    return _remove_leading_sequence_number(stem), ""


def _clean_filename_segment(value: str) -> str:
    cleaned = re.sub(
        r"\s*\((?:epub|mobi|pdf|azw3|fb2)\)\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return " ".join(cleaned.split())


def _clean_author_candidate(value: str) -> str:
    cleaned = re.sub(r"\s*\[[^\]]+\]\s*\d*(?:\.\d+)?\s*$", "", value)
    cleaned = re.sub(r",?\s*\d{4}(?:\s*-\s*\d{4})?\s*$", "", cleaned)
    cleaned = " ".join(cleaned.split()).strip(" ,-")
    if cleaned.casefold() in {"unknown", "unknown author", "extra"}:
        return ""
    return cleaned


def _author_likelihood(value: str) -> int:
    cleaned = _clean_author_candidate(value)
    if not cleaned:
        return -5
    lowered_tokens = set(_normalise(cleaned).split())
    title_words = {
        "a",
        "an",
        "and",
        "at",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "the",
        "to",
        "with",
        "without",
    }
    score = -2 if lowered_tokens & title_words else 0
    comma_parts = [part.strip() for part in cleaned.split(",")]
    if (
        len(comma_parts) >= 2
        and len(comma_parts[0].split()) == 1
        and comma_parts[0]
        and comma_parts[1]
    ):
        score += 4
    tokens = cleaned.replace(",", " ").split()
    if 2 <= len(tokens) <= 5 and all(
        _looks_like_name_token(token) for token in tokens
    ):
        score += 2
    if any(
        len(token.strip(".,")) == 1
        for token in tokens
    ):
        score += 1
    if len(tokens) > 6 or any(character in cleaned for character in "[]()"):
        score -= 2
    return score


def _looks_like_name_token(value: str) -> bool:
    token = value.strip(".,")
    if not token or token.isdigit() or "'" in token:
        return False
    pieces = token.split("-")
    return all(
        piece
        and (
            len(piece) == 1
            or piece[0].isupper()
            or piece.casefold() in {"de", "del", "la", "le", "van", "von"}
        )
        for piece in pieces
    )


def _title_matches(filename_value: str, metadata_value: str) -> bool:
    filename_key = _normalise(_remove_leading_sequence_number(filename_value))
    metadata_key = _normalise(_remove_leading_sequence_number(metadata_value))
    if not filename_key or not metadata_key:
        return False
    return (
        filename_key == metadata_key
        or (
            len(filename_key) >= 8
            and filename_key in metadata_key
        )
        or (
            len(metadata_key) >= 8
            and metadata_key in filename_key
        )
    )


def _author_matches(filename_value: str, metadata_value: str) -> bool:
    filename_tokens = set(_normalise(
        _clean_author_candidate(filename_value)
    ).split())
    metadata_tokens = set(_normalise(metadata_value).split())
    return bool(filename_tokens) and filename_tokens == metadata_tokens


def _author_is_compatible(wanted_author: str, candidate_author: str) -> bool:
    wanted_tokens = set(_normalise(
        _clean_author_candidate(wanted_author)
    ).split())
    candidate_tokens = set(_normalise(
        _clean_author_candidate(candidate_author)
    ).split())
    return bool(wanted_tokens) and (
        wanted_tokens <= candidate_tokens or candidate_tokens <= wanted_tokens
    )


def _candidate_is_reviewable(
    candidate: MetadataCandidate,
    *,
    title: str,
    author: str,
) -> bool:
    """Apply the same display-quality rule before and after fallbacks."""

    return candidate.confidence >= 75 or (
        _title_matches(title, candidate.title)
        and (not author or _author_matches(author, candidate.author))
    )


def _bounded_title_aliases(title: str) -> tuple[str, ...]:
    """Return only tightly bounded publisher-title variants."""

    cleaned = " ".join(str(title or "").split())
    aliases: list[str] = []
    substitutions = (
        (r"^(?:the\s+)?mystery\s+of\s+the\s+(.+)$", "The Secret of the {}"),
        (r"^(?:the\s+)?secret\s+of\s+the\s+(.+)$", "The Mystery of the {}"),
    )
    for pattern, template in substitutions:
        match = re.fullmatch(pattern, cleaned, flags=re.IGNORECASE)
        if match and match.group(1).strip():
            aliases.append(template.format(match.group(1).strip()))

    # A missing possessive apostrophe is common in filenames because some
    # download tools strip punctuation.  Keep this retry deliberately narrow:
    # only the complete word ``Mans`` becomes ``Man's``.  A returned catalogue
    # record still has to pass the normal title/author validation before it can
    # be shown to the user.
    possessive = re.sub(r"\bmans\b", "Man's", cleaned, flags=re.IGNORECASE)
    if possessive != cleaned:
        aliases.append(possessive)

    return tuple(dict.fromkeys(aliases))


def _collapse_accidental_character_repeats(value: str) -> str:
    """Repair an obvious key-bounce typo without changing double letters.

    Online catalogues often treat a title such as ``Mirrror`` as an exact
    search and return nothing.  Three or more consecutive copies of the same
    letter are almost always an accidental repeat in an ebook filename.  The
    provider query is therefore reduced to two copies (``Mirrror`` ->
    ``Mirror``), while legitimate double-letter words remain unchanged.  The
    catalogue is only updated later from a result that the user reviews.
    """

    return re.sub(r"([A-Za-z])\1{2,}", r"\1\1", str(value or ""))


def _remove_leading_sequence_number(value: str) -> str:
    cleaned = re.sub(
        r"^\s*(?:\d{1,2}\s+|\d{1,3}[._-]+\s*)(?=[A-Za-z])",
        "",
        value,
    )
    return " ".join(cleaned.split())


def _embedded_title_without_file_order_prefix(
    title: str,
    file_name: str,
) -> str:
    """Remove an ordering prefix only when the filename confirms it."""
    filename = str(file_name or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    file_match = re.match(
        r"^\s*(\d{1,3})\s+(?:-|\u2013|\u2014)\s+",
        stem,
    )
    if not file_match:
        return ""
    title_match = re.match(
        rf"^\s*{re.escape(file_match.group(1))}[\s._-]+(?=[A-Za-z])",
        title,
    )
    if not title_match:
        return ""
    return " ".join(title[title_match.end() :].split())


def clean_published_date(value: str | None) -> str:
    """Hide invalid sentinel years while preserving provider date detail."""
    cleaned = " ".join(str(value or "").split())
    year_match = re.match(r"^(\d{4})", cleaned)
    if year_match and int(year_match.group(1)) < 1000:
        return ""
    return cleaned


def _has_leading_sequence_number(value: str) -> bool:
    return _remove_leading_sequence_number(value) != " ".join(value.split())


def _cache_key(key: tuple[str, str, str]) -> str:
    return json.dumps(key, ensure_ascii=False, separators=(",", ":"))

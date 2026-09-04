"""UI-independent library querying and manual-review service."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import shutil

from database.database import DatabaseManager
from preferences import PreferencesStore


LIBRARY_SORT_FIELDS = frozenset(
    {
        "title",
        "author",
        "series",
        "date_added",
        "file_modified",
        "format",
        "metadata_quality",
    }
)
LIBRARY_SORT_DIRECTIONS = frozenset({"ascending", "descending"})
DEFAULT_LIBRARY_PAGE_SIZE = 100
MAX_LIBRARY_PAGE_SIZE = 500
MANUAL_REVIEW_FOLDER_NAME = "To be manually reviewed"
DELETED_FOLDER_NAME = "-=deleted=-"


@dataclass(frozen=True)
class LibraryRecord:
    """Book data prepared for presentation by any client."""

    title: str
    author: str
    isbn: str
    publisher: str
    published_date: str
    language: str
    file_format: str
    file_size: int
    metadata_status: str
    file_path: str
    book_id: int = 0
    file_name: str = ""
    library_folder: str = ""
    series: str = ""
    series_number: float | None = None
    series_group: str = ""
    series_group_number: float | None = None
    description: str = ""
    cover_path: str = ""
    date_added: str = ""
    file_modified_at: str = ""
    collections: tuple[str, ...] = ()
    metadata_issues: tuple[str, ...] = ()
    metadata_issue_count: int = 0
    provider_rating: float = 0.0
    rating_count: int = 0
    rating_source: str = ""
    metadata_workflow_complete: bool = False
    metadata_workflow_state: int = 0


@dataclass(frozen=True)
class LibraryFilterOptions:
    """Available library filter values."""

    formats: tuple[str, ...]
    metadata_statuses: tuple[str, ...]
    authors: tuple[str, ...] = ()
    series: tuple[str, ...] = ()
    collections: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()


@dataclass(frozen=True)
class LibraryResult:
    """A filtered result set and the active library total."""

    records: tuple[LibraryRecord, ...]
    total_count: int


@dataclass(frozen=True)
class LibraryQuery:
    """Validated database-backed Library browser query."""

    search_text: str = ""
    file_format: str = ""
    file_formats: tuple[str, ...] = ()
    provider_ratings: tuple[int, ...] = ()
    metadata_status: str = ""
    author: str = ""
    series: str = ""
    collection: str = ""
    library_location: str = ""
    metadata_attention: bool = False
    sort_field: str = "title"
    sort_direction: str = "ascending"
    offset: int = 0
    page_size: int = DEFAULT_LIBRARY_PAGE_SIZE


@dataclass(frozen=True)
class LibraryPageResult:
    """One Library page plus matching and active-library counts."""

    records: tuple[LibraryRecord, ...]
    matching_count: int
    total_count: int
    offset: int
    page_size: int
    has_more: bool


@dataclass(frozen=True)
class CollectionRecord:
    """A named collection and its number of active books."""

    collection_id: int
    name: str
    book_count: int


@dataclass(frozen=True)
class ManualReviewMove:
    """Completed physical move out of the active ebook catalogue."""

    book_id: int
    title: str
    original_path: str
    destination_path: str
    review_folder: str


@dataclass(frozen=True)
class DeletedBookMove:
    """Completed physical move of a book the user no longer wants tracked."""

    book_id: int
    title: str
    original_path: str
    destination_path: str
    deleted_folder: str


@dataclass(frozen=True)
class RelinkedMissingBooksSummary:
    """Outcome of searching a folder for already-relocated missing books."""

    relinked_book_ids: tuple[int, ...] = ()
    still_missing_count: int = 0


@dataclass(frozen=True)
class MissingFileEntry:
    """One catalogued book whose recorded file could not be found."""

    book_id: int
    title: str
    author: str
    file_path: str


class LibraryService:
    """Coordinate library reads while leaving SQL to the database layer."""

    def __init__(
        self,
        database: DatabaseManager | None = None,
        *,
        preferences: PreferencesStore | None = None,
    ) -> None:
        self._database = database or DatabaseManager()
        self._preferences = preferences or PreferencesStore()

    def get_filter_options(self) -> LibraryFilterOptions:
        """Return validated choices used by Library filters."""
        browser_options = getattr(
            self._database,
            "get_library_browser_filter_options",
            None,
        )
        if browser_options is not None:
            options = browser_options()
            return LibraryFilterOptions(
                formats=tuple(options.get("formats", ())),
                metadata_statuses=tuple(
                    options.get("metadata_statuses", ())
                ),
                authors=tuple(options.get("authors", ())),
                series=tuple(options.get("series", ())),
                collections=tuple(options.get("collections", ())),
                locations=tuple(options.get("locations", ())),
            )

        formats, statuses = self._database.get_library_filter_options()
        return LibraryFilterOptions(tuple(formats), tuple(statuses))

    def get_library(
        self,
        *,
        search_text: str = "",
        file_format: str = "",
        metadata_status: str = "",
        author: str = "",
        series: str = "",
        library_location: str = "",
        metadata_attention: bool = False,
    ) -> LibraryResult:
        """Return filtered records and the total active record count."""
        filters: dict[str, object] = dict(
            search_text=search_text,
            file_format=file_format,
            metadata_status=metadata_status,
        )
        if author.strip():
            filters["author"] = author
        if series.strip():
            filters["series"] = series
        if library_location.strip():
            filters["library_location"] = library_location
        if metadata_attention:
            filters["metadata_attention"] = True

        rows = self._database.search_books(**filters)
        records = tuple(self._to_record(row) for row in rows)

        if (
            search_text.strip()
            or file_format
            or metadata_status
            or author.strip()
            or series.strip()
            or library_location.strip()
            or metadata_attention
        ):
            total_count = self._database.count_books()
        else:
            total_count = len(records)

        return LibraryResult(records, total_count)

    def get_library_page(
        self,
        query: LibraryQuery,
    ) -> LibraryPageResult:
        """Return one validated, sorted page for the Library browser."""
        self._validate_query(query)
        filters = {
            "search_text": query.search_text,
            "file_format": query.file_format,
            "file_formats": query.file_formats,
            "provider_ratings": query.provider_ratings,
            "metadata_status": query.metadata_status,
            "author": query.author,
            "series": query.series,
            "collection": query.collection,
            "library_location": query.library_location,
            "metadata_attention": query.metadata_attention,
        }
        rows = self._database.search_books(
            **filters,
            sort_field=query.sort_field,
            sort_direction=query.sort_direction,
            limit=query.page_size,
            offset=query.offset,
        )
        records = tuple(self._to_record(row) for row in rows)
        matching_count = self._database.count_search_books(**filters)
        total_count = self._database.count_books()
        return LibraryPageResult(
            records=records,
            matching_count=matching_count,
            total_count=total_count,
            offset=query.offset,
            page_size=query.page_size,
            has_more=query.offset + len(records) < matching_count,
        )

    def count_records(self) -> int:
        """Return the number of active library records."""
        return self._database.count_books()

    def get_collections(self) -> tuple[CollectionRecord, ...]:
        """Return all collections for display and assignment."""
        return tuple(
            CollectionRecord(
                collection_id=int(_row_value(row, "id") or 0),
                name=str(_row_value(row, "name") or ""),
                book_count=int(_row_value(row, "book_count") or 0),
            )
            for row in self._database.list_collections()
        )

    def create_collection(self, name: str) -> CollectionRecord:
        """Create a collection and return its current snapshot."""
        collection_id = self._database.create_collection(name)
        for collection in self.get_collections():
            if collection.collection_id == collection_id:
                return collection
        raise RuntimeError("The new collection could not be loaded.")

    def get_book_collection_ids(self, book_id: int) -> tuple[int, ...]:
        """Return collection IDs assigned to a book."""
        return tuple(self._database.get_book_collection_ids(book_id))

    def set_book_collections(
        self,
        book_id: int,
        collection_ids: tuple[int, ...] | list[int],
    ) -> None:
        """Replace database memberships without changing ebook files."""
        self._database.set_book_collections(book_id, collection_ids)

    def move_book_to_manual_review(
        self,
        book_id: int,
    ) -> ManualReviewMove:
        """Move one file to its watched root's excluded review folder."""
        row = self._database.get_book_by_id(book_id)
        if row is None:
            raise ValueError(
                "The selected book is no longer in the Twano catalogue."
            )
        source = Path(str(row["file_path"])).resolve(strict=True)
        watched_root = Path(str(row["library_folder"])).resolve(strict=True)
        if not watched_root.is_dir():
            raise FileNotFoundError(
                "The watched folder is unavailable. Reconnect it before "
                "moving this book."
            )
        try:
            source.relative_to(watched_root)
        except ValueError as error:
            raise ValueError(
                "The selected file is outside its watched folder and cannot "
                "be moved automatically."
            ) from error

        review_folder = watched_root / MANUAL_REVIEW_FOLDER_NAME
        review_folder.mkdir(exist_ok=True)
        resolved_review_folder = review_folder.resolve(strict=True)
        try:
            resolved_review_folder.relative_to(watched_root)
        except ValueError as error:
            raise ValueError(
                "The manual-review folder resolves outside the watched "
                "library. Remove that folder link before trying again."
            ) from error
        if resolved_review_folder in source.parents:
            raise ValueError(
                "This book is already inside the manual-review folder."
            )

        destination = self._available_destination(
            resolved_review_folder,
            source.name,
        )
        shutil.move(str(source), str(destination))
        try:
            self._database.remove_book_from_catalogue(book_id)
        except Exception as error:
            try:
                shutil.move(str(destination), str(source))
            except Exception as rollback_error:
                raise RuntimeError(
                    "Twano moved the file but could not update the catalogue "
                    "or return the file to its original location. The file is "
                    f"currently at:\n{destination}\n\n{rollback_error}"
                ) from error
            raise
        return ManualReviewMove(
            book_id=int(book_id),
            title=str(row["title"] or row["file_name"]),
            original_path=str(source),
            destination_path=str(destination),
            review_folder=str(resolved_review_folder),
        )

    def move_book_to_deleted(
        self,
        book_id: int,
    ) -> DeletedBookMove:
        """Move one file to its excluded deleted folder."""
        row = self._database.get_book_by_id(book_id)
        if row is None:
            raise ValueError(
                "The selected book is no longer in the Twano catalogue."
            )
        source = Path(str(row["file_path"])).resolve(strict=True)
        watched_root = Path(str(row["library_folder"])).resolve(strict=True)
        if not watched_root.is_dir():
            raise FileNotFoundError(
                "The watched folder is unavailable. Reconnect it before "
                "deleting this book."
            )
        try:
            source.relative_to(watched_root)
        except ValueError as error:
            raise ValueError(
                "The selected file is outside its watched folder and cannot "
                "be moved automatically."
            ) from error

        # Deleted books move into one shared destination folder when the
        # user has configured one in Settings, instead of staying inside
        # whichever watched library they happened to be scanned from.
        configured_destination = (
            self._preferences.load_organization_preferences()
            .destination_folder
        )
        destination_root = (
            Path(configured_destination).resolve()
            if configured_destination
            else watched_root
        )
        deleted_folder = destination_root / DELETED_FOLDER_NAME
        deleted_folder.mkdir(parents=True, exist_ok=True)
        resolved_deleted_folder = deleted_folder.resolve(strict=True)
        try:
            resolved_deleted_folder.relative_to(destination_root)
        except ValueError as error:
            raise ValueError(
                "The deleted-books folder resolves outside its destination. "
                "Remove that folder link before trying again."
            ) from error
        if resolved_deleted_folder in source.parents:
            raise ValueError(
                "This book is already inside the deleted-books folder."
            )

        destination = self._available_destination(
            resolved_deleted_folder,
            source.name,
        )
        shutil.move(str(source), str(destination))
        try:
            self._database.remove_book_from_catalogue(book_id)
        except Exception as error:
            try:
                shutil.move(str(destination), str(source))
            except Exception as rollback_error:
                raise RuntimeError(
                    "Twano moved the file but could not update the catalogue "
                    "or return the file to its original location. The file is "
                    f"currently at:\n{destination}\n\n{rollback_error}"
                ) from error
            raise
        return DeletedBookMove(
            book_id=int(book_id),
            title=str(row["title"] or row["file_name"]),
            original_path=str(source),
            destination_path=str(destination),
            deleted_folder=str(resolved_deleted_folder),
        )

    def relink_missing_books_from(
        self,
        destination_folder: str | Path,
    ) -> RelinkedMissingBooksSummary:
        """Find already-moved files for missing books inside one folder.

        Twano cannot detect a file move on its own, so when the user
        manually relocates already-organised books — for example, into a
        newly chosen destination folder — each book flagged missing stays
        that way until something re-links it. For each missing book, this
        first checks whether its exact relative path was preserved under
        the given folder (the common case when a whole -=Series=- or
        author folder was moved as-is), then falls back to a same-name,
        same-size search anywhere inside it.
        """
        root = Path(destination_folder).resolve()
        if not root.is_dir():
            return RelinkedMissingBooksSummary()
        relinked: list[int] = []
        still_missing = 0
        for row in self._database.get_books(include_missing=True):
            if not bool(row["is_missing"]):
                continue
            candidate = self._find_relocated_file(row, root)
            if candidate is None:
                still_missing += 1
                continue
            self._database.relink_missing_book(
                int(row["id"]),
                file_path=candidate,
                library_folder=root,
            )
            relinked.append(int(row["id"]))
        return RelinkedMissingBooksSummary(
            relinked_book_ids=tuple(relinked),
            still_missing_count=still_missing,
        )

    def find_books_with_missing_files(self) -> tuple[MissingFileEntry, ...]:
        """Check every catalogued book's file, not just one watched source.

        A normal scan only re-checks files inside the one watched source
        it targets, so a book already organised into a shared destination
        folder outside any watched source never gets re-verified by a
        scan again. This checks every book in the whole catalogue,
        regardless of the ``is_missing`` flag or which source it came
        from, so a stale entry pointing at a file that's genuinely gone
        can be found and reviewed for removal.
        """
        entries: list[MissingFileEntry] = []
        for row in self._database.get_books(include_missing=True):
            file_path = str(row["file_path"] or "")
            if file_path and Path(file_path).is_file():
                continue
            entries.append(
                MissingFileEntry(
                    book_id=int(row["id"]),
                    title=str(row["title"] or row["file_name"]),
                    author=str(row["author"] or ""),
                    file_path=file_path,
                )
            )
        return tuple(entries)

    def remove_books_from_catalogue(
        self,
        book_ids: Sequence[int],
    ) -> int:
        """Remove catalogue rows the user reviewed and chose to remove.

        Only removes the catalogue record itself -- there is no file to
        touch, since this is only ever used for entries a Verify Library
        check already confirmed point at a file that isn't there.
        """
        removed = 0
        for book_id in book_ids:
            try:
                self._database.remove_book_from_catalogue(int(book_id))
            except ValueError:
                continue
            removed += 1
        return removed

    @staticmethod
    def _find_relocated_file(row, root: Path) -> Path | None:
        old_path = Path(str(row["file_path"]))
        expected_size = int(row["file_size"] or 0)
        old_root_value = str(row["library_folder"] or "")
        if old_root_value:
            try:
                relative = old_path.resolve().relative_to(
                    Path(old_root_value).resolve()
                )
            except (ValueError, OSError):
                relative = None
            if relative is not None:
                guess = root / relative
                if guess.is_file() and (
                    not expected_size
                    or guess.stat().st_size == expected_size
                ):
                    return guess
        expected_name = str(row["file_name"] or old_path.name)
        if not expected_name:
            return None
        try:
            for found in root.rglob(expected_name):
                if not found.is_file():
                    continue
                if expected_size and found.stat().st_size != expected_size:
                    continue
                return found
        except OSError:
            return None
        return None

    def manual_review_folders(self) -> tuple[Path, ...]:
        """Return existing review folders for active watched libraries."""
        folders: list[Path] = []
        for row in self._database.list_library_sources():
            candidate = (
                Path(str(row["folder_path"]))
                / MANUAL_REVIEW_FOLDER_NAME
            )
            if candidate.is_dir():
                folders.append(candidate.resolve())
        return tuple(
            sorted(
                set(folders),
                key=lambda path: str(path).casefold(),
            )
        )

    @staticmethod
    def _available_destination(folder: Path, file_name: str) -> Path:
        candidate = folder / file_name
        if not candidate.exists():
            return candidate
        stem = Path(file_name).stem
        suffix = Path(file_name).suffix
        counter = 2
        while True:
            candidate = folder / f"{stem} ({counter}){suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    @staticmethod
    def _validate_query(query: LibraryQuery) -> None:
        if query.sort_field not in LIBRARY_SORT_FIELDS:
            raise ValueError(
                f"Unsupported library sort field: {query.sort_field}"
            )
        if query.sort_direction not in LIBRARY_SORT_DIRECTIONS:
            raise ValueError(
                "Unsupported library sort direction: "
                f"{query.sort_direction}"
            )
        if query.offset < 0:
            raise ValueError("Library query offset cannot be negative.")
        if not 1 <= query.page_size <= MAX_LIBRARY_PAGE_SIZE:
            raise ValueError(
                "Library page size must be between 1 and "
                f"{MAX_LIBRARY_PAGE_SIZE}."
            )
        if any(rating < 0 or rating > 5 for rating in query.provider_ratings):
            raise ValueError("Website rating bands must be between 0 and 5.")

    @staticmethod
    def _to_record(row) -> LibraryRecord:
        """Detach a database row into an immutable service value."""
        file_name = str(_row_value(row, "file_name") or "")
        raw_title = str(_row_value(row, "title") or "")
        raw_author = str(_row_value(row, "author") or "")
        isbn = str(_row_value(row, "isbn") or "")
        publisher = str(_row_value(row, "publisher") or "")
        series = str(_row_value(row, "series") or "")
        series_group = str(_row_value(row, "series_group") or "")
        description = str(_row_value(row, "description") or "")
        cover_path = str(_row_value(row, "cover_path") or "")
        raw_series_number = _row_value(row, "series_number")
        raw_series_group_number = _row_value(row, "series_group_number")
        raw_collections = str(_row_value(row, "collections") or "")
        metadata_status = str(
            _row_value(row, "metadata_status") or "pending"
        )

        issues = []
        if not raw_title:
            issues.append("Missing title")
        if not raw_author or raw_author.casefold() in {
            "unknown",
            "unknown author",
        }:
            issues.append("Unknown author")
        if not isbn:
            issues.append("Missing ISBN")
        if not publisher:
            issues.append("Missing publisher")
        if not cover_path:
            issues.append("Missing cover")
        if not series:
            issues.append("Missing series")
        if not description:
            issues.append("Missing description")
        if metadata_status not in {"embedded", "external"}:
            issues.append(
                f"Metadata status: {metadata_status.replace('_', ' ')}"
            )

        return LibraryRecord(
            title=raw_title or file_name,
            author=raw_author or "Unknown",
            isbn=isbn,
            publisher=publisher,
            published_date=str(
                _row_value(row, "published_date") or ""
            ),
            language=str(_row_value(row, "language") or ""),
            file_format=str(_row_value(row, "file_format") or ""),
            file_size=int(_row_value(row, "file_size") or 0),
            metadata_status=metadata_status,
            file_path=str(_row_value(row, "file_path") or ""),
            book_id=int(_row_value(row, "id") or 0),
            file_name=file_name,
            library_folder=str(
                _row_value(row, "library_folder") or ""
            ),
            series=series,
            series_number=(
                float(raw_series_number)
                if raw_series_number is not None
                else None
            ),
            series_group=series_group,
            series_group_number=(
                float(raw_series_group_number)
                if raw_series_group_number is not None
                else None
            ),
            description=description,
            cover_path=cover_path,
            date_added=str(_row_value(row, "discovered_at") or ""),
            file_modified_at=str(
                _row_value(row, "file_modified_at") or ""
            ),
            collections=tuple(
                value
                for value in raw_collections.split("\x1f")
                if value
            ),
            metadata_issues=tuple(issues),
            metadata_issue_count=len(issues),
            provider_rating=float(_row_value(row, "provider_rating") or 0),
            rating_count=int(_row_value(row, "rating_count") or 0),
            rating_source=str(_row_value(row, "rating_source") or ""),
            metadata_workflow_complete=(
                int(_row_value(row, "metadata_workflow_complete") or 0) == 1
            ),
            metadata_workflow_state=int(
                _row_value(row, "metadata_workflow_complete") or 0
            ),
        )


def _row_value(row, key: str):
    """Read dict and sqlite Row values without leaking storage details."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return None

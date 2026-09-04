"""UI-independent dashboard service."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from database.database import DatabaseManager


@dataclass(frozen=True)
class RecentBook:
    """A recently discovered title prepared for dashboard display."""

    title: str
    author: str
    file_format: str
    discovered_at: str


@dataclass(frozen=True)
class DashboardData:
    """Dashboard counts and summaries prepared for presentation."""

    total_books: int
    embedded_metadata: int
    needs_metadata: int
    missing_books: int
    total_size: int
    library_count: int
    metadata_health: int
    formats: Mapping[str, int]
    books_this_week: int = 0
    last_scanned_at: str | None = None
    recent_books: tuple[RecentBook, ...] = ()
    attention_books: tuple[RecentBook, ...] = ()
    library_locations: tuple[str, ...] = ()


class DashboardService:
    """Coordinate dashboard reads while leaving SQL to the database."""

    def __init__(self, database: DatabaseManager | None = None) -> None:
        self._database = database or DatabaseManager()

    def get_dashboard_data(self) -> DashboardData:
        """Return an immutable dashboard snapshot."""
        statistics = self._database.get_dashboard_statistics()
        formats = statistics.get("formats", {})
        recent_books = statistics.get("recent_books", ())

        return DashboardData(
            total_books=int(statistics["total_books"]),
            embedded_metadata=int(statistics["embedded_metadata"]),
            needs_metadata=int(statistics["needs_metadata"]),
            missing_books=int(statistics["missing_books"]),
            total_size=int(statistics["total_size"]),
            library_count=int(statistics["library_count"]),
            metadata_health=int(statistics["metadata_health"]),
            formats=MappingProxyType({
                str(file_format): int(count)
                for file_format, count in (
                    formats.items() if isinstance(formats, dict) else ()
                )
            }),
            books_this_week=int(statistics.get("books_this_week", 0)),
            last_scanned_at=(
                str(statistics["last_scanned_at"])
                if statistics.get("last_scanned_at")
                else None
            ),
            recent_books=tuple(
                RecentBook(
                    title=str(book.get("title", "Untitled")),
                    author=str(book.get("author", "Unknown author")),
                    file_format=str(book.get("file_format", "")),
                    discovered_at=str(book.get("discovered_at", "")),
                )
                for book in recent_books
                if isinstance(book, dict)
            ),
            attention_books=tuple(
                RecentBook(
                    title=str(book.get("title", "Untitled")),
                    author=str(book.get("author", "Unknown author")),
                    file_format="",
                    discovered_at="",
                )
                for book in statistics.get("attention_books", ())
                if isinstance(book, dict)
            ),
            library_locations=tuple(str(path) for path in statistics.get("library_locations", ())),
        )

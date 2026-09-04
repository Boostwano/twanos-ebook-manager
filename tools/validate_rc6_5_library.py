"""Measure RC6.5 Library behavior against 10,000 synthetic records."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QItemSelectionModel  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QListView,
    QStackedWidget,
    QTableView,
)

from database.database import DatabaseManager  # noqa: E402
from services.library_service import (  # noqa: E402
    LibraryQuery,
    LibraryService,
)
from ui.library_model import LibraryModel  # noqa: E402
from ui.thumbnail_cache import ThumbnailCache  # noqa: E402


BOOK_COUNT = 10_000


class CountingLibraryService(LibraryService):
    """Count model page calls without altering the production service."""

    def __init__(self, database: DatabaseManager) -> None:
        super().__init__(database)
        self.page_calls = 0

    def get_library_page(self, query: LibraryQuery):
        self.page_calls += 1
        return super().get_library_page(query)


def populate(database: DatabaseManager) -> float:
    """Insert a deterministic large catalogue in one transaction."""
    started = perf_counter()
    formats = ("EPUB", "PDF", "MOBI", "CBZ")
    timestamp = "2026-07-28T00:00:00+00:00"
    with database.connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO libraries (
                folder_path,
                created_at,
                last_scanned_at
            )
            VALUES (?, ?, ?)
            """,
            ("C:/Synthetic Library", timestamp, timestamp),
        )
        library_id = int(cursor.lastrowid)
        connection.executemany(
            """
            INSERT INTO books (
                library_id,
                file_path,
                file_name,
                title,
                author,
                isbn,
                file_format,
                file_size,
                file_modified_at,
                discovered_at,
                last_seen_at,
                metadata_status,
                review_required,
                is_missing,
                publisher,
                language,
                published_date,
                series,
                series_number,
                description,
                cover_path
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )
            """,
            (
                (
                    library_id,
                    f"C:/Synthetic Library/Book {index:05d}.epub",
                    f"Book {index:05d}.epub",
                    f"Book {index:05d}",
                    f"Author {index % 250:03d}",
                    f"9780000{index:06d}",
                    formats[index % len(formats)],
                    50_000 + index,
                    f"2026-06-{(index % 28) + 1:02d}T00:00:00+00:00",
                    f"2026-01-{(index % 28) + 1:02d}T00:00:00+00:00",
                    timestamp,
                    "embedded" if index % 3 else "pending",
                    1 if index % 17 == 0 else 0,
                    0,
                    f"Publisher {index % 40:02d}",
                    "en",
                    str(1980 + (index % 46)),
                    f"Series {index % 100:03d}",
                    float((index % 20) + 1),
                    f"Synthetic description for book {index}.",
                    "",
                )
                for index in range(BOOK_COUNT)
            ),
        )
        connection.executemany(
            """
            INSERT INTO collections (name, created_at)
            VALUES (?, ?)
            """,
            (
                (f"Collection {index:02d}", timestamp)
                for index in range(25)
            ),
        )
        connection.executemany(
            """
            INSERT INTO book_collections (
                book_id,
                collection_id,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (
                (index + 1, (index % 25) + 1, timestamp)
                for index in range(BOOK_COUNT)
            ),
        )
    return (perf_counter() - started) * 1000


def measure(database: DatabaseManager) -> dict[str, object]:
    """Collect truthful query, render, switch, and cache observations."""
    service = CountingLibraryService(database)

    started = perf_counter()
    initial = service.get_library_page(LibraryQuery(page_size=100))
    initial_query_ms = (perf_counter() - started) * 1000

    started = perf_counter()
    filtered = service.get_library_page(
        LibraryQuery(
            file_format="MOBI",
            author="Author 042",
            collection="Collection 17",
            sort_field="file_modified",
            sort_direction="descending",
            page_size=100,
        )
    )
    filter_sort_query_ms = (perf_counter() - started) * 1000

    started = perf_counter()
    incremental = service.get_library_page(
        LibraryQuery(offset=100, page_size=100)
    )
    incremental_page_ms = (perf_counter() - started) * 1000

    application = QApplication.instance() or QApplication([])
    model = LibraryModel(service, background_queries=False)
    table = QTableView()
    grid = QListView()
    selection = QItemSelectionModel(model)
    table.setModel(model)
    grid.setModel(model)
    table.setSelectionModel(selection)
    grid.setSelectionModel(selection)
    views = QStackedWidget()
    views.addWidget(grid)
    views.addWidget(table)
    views.resize(1000, 620)

    started = perf_counter()
    model.set_query(LibraryQuery(page_size=100))
    views.show()
    application.processEvents()
    first_page_model_render_ms = (perf_counter() - started) * 1000

    calls_before_switch = service.page_calls
    started = perf_counter()
    for index in range(200):
        views.setCurrentIndex(index % 2)
        application.processEvents()
    view_switch_ms = (perf_counter() - started) * 1000
    calls_after_switch = service.page_calls

    cache = ThumbnailCache(max_items=192)
    results = {
        "records": BOOK_COUNT,
        "initial_page_records": len(initial.records),
        "initial_query_ms": round(initial_query_ms, 3),
        "filter_sort_matches": filtered.matching_count,
        "filter_sort_query_ms": round(filter_sort_query_ms, 3),
        "incremental_page_records": len(incremental.records),
        "incremental_page_ms": round(incremental_page_ms, 3),
        "first_page_model_render_ms": round(
            first_page_model_render_ms,
            3,
        ),
        "view_switches": 200,
        "view_switch_ms": round(view_switch_ms, 3),
        "view_switch_query_delta": (
            calls_after_switch - calls_before_switch
        ),
        "thumbnail_cache_limit": cache.max_items,
    }
    views.close()
    table.deleteLater()
    grid.deleteLater()
    views.deleteLater()
    application.processEvents()
    return results


def main() -> int:
    with TemporaryDirectory(
        prefix="Twano-RC65-performance-",
        ignore_cleanup_errors=True,
    ) as folder:
        database = DatabaseManager(Path(folder) / "synthetic.db")
        insert_ms = populate(database)
        results = measure(database)
        results["dataset_insert_ms"] = round(insert_ms, 3)
        print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

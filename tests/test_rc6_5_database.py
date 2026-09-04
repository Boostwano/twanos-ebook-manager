"""RC6.5 additive schema, paging, sorting, and collection tests."""

from pathlib import Path
import sqlite3

import pytest

from core.scanner import BookFile
from database.database import DatabaseManager
from services.library_service import LibraryQuery, LibraryService


def _database_with_books(
    tmp_path: Path,
    count: int = 4,
) -> tuple[DatabaseManager, list[Path]]:
    folder = tmp_path / "library"
    folder.mkdir()
    paths = []
    books = []
    formats = ("EPUB", "PDF", "MOBI", "CBZ")
    for index in range(count):
        path = folder / f"Book {index}.ebook"
        path.write_bytes(f"book-{index}".encode())
        paths.append(path)
        books.append(
            BookFile(
                name=f"Book {index}",
                extension=formats[index % len(formats)],
                size_bytes=path.stat().st_size,
                path=path,
            )
        )

    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, books)
    with database.connection() as connection:
        rows = connection.execute(
            "SELECT id FROM books ORDER BY id"
        ).fetchall()
        values = (
            (
                "Zulu",
                "Beta",
                "Saga",
                2.0,
                "2026-01-04T00:00:00+00:00",
                "2026-02-04T00:00:00+00:00",
                "pending",
                1,
            ),
            (
                "Alpha",
                "Zulu",
                "Saga",
                1.0,
                "2026-01-03T00:00:00+00:00",
                "2026-02-03T00:00:00+00:00",
                "external",
                0,
            ),
            (
                "Mike",
                "Alpha",
                "Chronicles",
                3.0,
                "2026-01-02T00:00:00+00:00",
                "2026-02-02T00:00:00+00:00",
                "embedded",
                0,
            ),
            (
                "Bravo",
                "Mike",
                None,
                None,
                "2026-01-01T00:00:00+00:00",
                "2026-02-01T00:00:00+00:00",
                "pending",
                0,
            ),
        )
        for row, value in zip(rows, values, strict=True):
            connection.execute(
                """
                UPDATE books
                SET
                    title = ?,
                    author = ?,
                    series = ?,
                    series_number = ?,
                    discovered_at = ?,
                    file_modified_at = ?,
                    metadata_status = ?,
                    review_required = ?
                WHERE id = ?
                """,
                (*value, int(row["id"])),
            )
    return database, paths


def test_additive_migration_preserves_legacy_database(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE libraries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_path TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            last_scanned_at TEXT
        );
        CREATE TABLE books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_id INTEGER NOT NULL,
            file_path TEXT NOT NULL UNIQUE,
            file_name TEXT NOT NULL,
            title TEXT,
            author TEXT,
            isbn TEXT,
            file_format TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            file_modified_at TEXT,
            discovered_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            metadata_status TEXT NOT NULL DEFAULT 'pending',
            review_required INTEGER NOT NULL DEFAULT 0,
            is_missing INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    connection.execute(
        """
        INSERT INTO libraries (folder_path, created_at)
        VALUES ('C:/Legacy', '2026-01-01')
        """
    )
    connection.execute(
        """
        INSERT INTO books (
            library_id, file_path, file_name, title, file_format,
            file_size, discovered_at, last_seen_at
        )
        VALUES (
            1, 'C:/Legacy/Book.epub', 'Book.epub', 'Legacy Book',
            'EPUB', 10, '2026-01-01', '2026-01-01'
        )
        """
    )
    connection.commit()
    connection.close()

    database = DatabaseManager(path)
    with database.connection() as upgraded:
        columns = {
            row["name"]
            for row in upgraded.execute(
                "PRAGMA table_info(books)"
            ).fetchall()
        }
        tables = {
            row["name"]
            for row in upgraded.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

    assert "series_number" in columns
    assert {"series_group", "series_group_number"}.issubset(columns)
    assert {"provider_rating", "rating_count", "rating_source"}.issubset(
        columns
    )
    assert {"collections", "book_collections"}.issubset(tables)
    assert database.count_books() == 1


def test_multiple_formats_and_website_rating_filters(tmp_path: Path) -> None:
    database, _ = _database_with_books(tmp_path)
    rows = database.search_books(sort_field="title")
    rated_id = int(rows[0]["id"])
    with database.connection() as connection:
        connection.execute(
            "UPDATE books SET provider_rating = 4.2, rating_count = 25, "
            "rating_source = 'Google Books' WHERE id = ?",
            (rated_id,),
        )

    filtered = database.search_books(
        file_formats=("EPUB", "CBZ"),
        provider_ratings=(0, 4),
        sort_field="title",
    )

    assert filtered
    assert all(row["file_format"] in {"EPUB", "CBZ"} for row in filtered)
    assert {
        int(float(row["provider_rating"]) + 0.5) for row in filtered
    }.issubset({0, 4})
    assert database.count_search_books(provider_ratings=(4,)) == 1
    assert int(database.search_books(provider_ratings=(4,))[0]["id"]) == rated_id


def test_collection_membership_filter_and_cascade(
    tmp_path: Path,
) -> None:
    database, _ = _database_with_books(tmp_path)
    books = database.search_books(sort_field="title")
    first_id = int(books[0]["id"])
    collection_id = database.create_collection("Favourites")

    assert database.create_collection(" favourites ") == collection_id
    database.set_book_collections(first_id, [collection_id])

    assigned = database.search_books(collection="FAVOURITES")
    assert [int(row["id"]) for row in assigned] == [first_id]
    assert assigned[0]["collections"] == "Favourites"
    assert database.get_book_collection_ids(first_id) == [collection_id]

    with database.connection() as connection:
        connection.execute("DELETE FROM books WHERE id = ?", (first_id,))
        remaining = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM book_collections
            WHERE book_id = ?
            """,
            (first_id,),
        ).fetchone()
    assert remaining["total"] == 0


@pytest.mark.parametrize(
    "sort_field,expected_ascending,expected_descending",
    [
        ("title", "Alpha", "Zulu"),
        ("author", "Mike", "Alpha"),
        ("series", "Bravo", "Zulu"),
        ("date_added", "Bravo", "Zulu"),
        ("file_modified", "Bravo", "Zulu"),
        ("format", "Bravo", "Alpha"),
        ("metadata_quality", "Mike", "Bravo"),
    ],
)
def test_allowlisted_sort_fields_and_directions(
    tmp_path: Path,
    sort_field: str,
    expected_ascending: str,
    expected_descending: str,
) -> None:
    database, _ = _database_with_books(tmp_path)
    ascending = database.search_books(
        sort_field=sort_field,
        sort_direction="ascending",
    )
    descending = database.search_books(
        sort_field=sort_field,
        sort_direction="descending",
    )

    assert ascending[0]["title"] == expected_ascending
    assert descending[0]["title"] == expected_descending


def test_invalid_sort_and_paging_boundaries_are_rejected(
    tmp_path: Path,
) -> None:
    database, _ = _database_with_books(tmp_path)

    with pytest.raises(ValueError, match="sort field"):
        database.search_books(sort_field="books.title; DROP TABLE books")
    with pytest.raises(ValueError, match="direction"):
        database.search_books(sort_direction="sideways")
    with pytest.raises(ValueError, match="greater than zero"):
        database.search_books(limit=0)
    with pytest.raises(ValueError, match="requires a limit"):
        database.search_books(offset=1)


def test_service_page_contract_reports_matching_and_total_counts(
    tmp_path: Path,
) -> None:
    database, _ = _database_with_books(tmp_path)
    service = LibraryService(database)

    first = service.get_library_page(
        LibraryQuery(file_format="EPUB", page_size=1)
    )
    second = service.get_library_page(
        LibraryQuery(offset=1, page_size=2)
    )

    assert len(first.records) == 1
    assert first.matching_count == 1
    assert first.total_count == 4
    assert not first.has_more
    assert len(second.records) == 2
    assert second.offset == 1
    assert second.has_more
    assert second.records[0].book_id > 0
    assert second.records[0].date_added
    assert second.records[0].file_modified_at


def test_combined_filters_and_browser_options(tmp_path: Path) -> None:
    database, _ = _database_with_books(tmp_path)
    collection_id = database.create_collection("Reading List")
    alpha = database.search_books(search_text="Alpha")[0]
    database.set_book_collections(int(alpha["id"]), [collection_id])

    rows = database.search_books(
        search_text="Alpha",
        author="Zulu",
        series="Saga",
        collection="Reading List",
        metadata_status="external",
    )
    options = database.get_library_browser_filter_options()

    assert [row["title"] for row in rows] == ["Alpha"]
    assert "Zulu" in options["authors"]
    assert "Saga" in options["series"]
    assert "Reading List" in options["collections"]
    assert options["locations"]

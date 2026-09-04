"""Tests for the SQLite database layer."""

from pathlib import Path

from core.scanner import BookFile
from database.database import DatabaseManager


def test_save_scan_results(tmp_path: Path) -> None:
    database_path = tmp_path / "test_library.db"
    library_folder = tmp_path / "books"
    library_folder.mkdir()

    book_path = library_folder / "Example Book.epub"
    book_path.write_bytes(b"example ebook content")

    book = BookFile(
        name="Example Book",
        extension="EPUB",
        size_bytes=book_path.stat().st_size,
        path=book_path,
    )

    database = DatabaseManager(database_path)
    saved_count = database.save_scan_results(library_folder, [book])

    assert saved_count == 1
    assert database.count_books() == 1

    stored_books = database.get_books()

    assert len(stored_books) == 1
    assert stored_books[0]["title"] == "Example Book"
    assert stored_books[0]["file_format"] == "EPUB"


def test_search_books(tmp_path: Path) -> None:
    """Books can be searched and filtered."""
    database_path = tmp_path / "search_test.db"
    library_folder = tmp_path / "library"
    library_folder.mkdir()

    first_path = library_folder / "The Hobbit.epub"
    second_path = library_folder / "Dune.pdf"

    first_path.write_bytes(b"hobbit")
    second_path.write_bytes(b"dune")

    books = [
        BookFile(
            name="The Hobbit",
            extension="EPUB",
            size_bytes=first_path.stat().st_size,
            path=first_path,
        ),
        BookFile(
            name="Dune",
            extension="PDF",
            size_bytes=second_path.stat().st_size,
            path=second_path,
        ),
    ]

    database = DatabaseManager(database_path)
    database.save_scan_results(library_folder, books)

    database.update_book_metadata(
        first_path,
        title="The Hobbit",
        author="J. R. R. Tolkien",
        isbn="9780261103344",
        publisher="HarperCollins",
        language="en",
        published_date=None,
        metadata_status="embedded",
    )

    title_results = database.search_books(
        search_text="Hobbit"
    )
    author_results = database.search_books(
        search_text="Tolkien"
    )
    publisher_results = database.search_books(
        search_text="HarperCollins"
    )
    format_results = database.search_books(
        file_format="PDF"
    )
    status_results = database.search_books(
        metadata_status="embedded"
    )
    attention_results = database.search_books(
        metadata_attention=True
    )

    assert len(title_results) == 1
    assert title_results[0]["title"] == "The Hobbit"

    assert len(author_results) == 1
    assert author_results[0]["author"] == "J. R. R. Tolkien"

    assert len(publisher_results) == 1
    assert publisher_results[0]["publisher"] == "HarperCollins"

    assert len(format_results) == 1
    assert format_results[0]["file_format"] == "PDF"

    assert len(status_results) == 1
    assert status_results[0]["metadata_status"] == "embedded"

    assert len(attention_results) == 1
    assert attention_results[0]["title"] == "Dune"
    assert {
        "series",
        "description",
        "cover_path",
    }.issubset(attention_results[0].keys())


def test_dashboard_statistics(tmp_path: Path) -> None:
    """Dashboard statistics reflect stored library books."""
    database_path = tmp_path / "dashboard_test.db"
    library_folder = tmp_path / "dashboard_books"
    library_folder.mkdir()

    epub_path = library_folder / "Example.epub"
    pdf_path = library_folder / "Document.pdf"

    epub_path.write_bytes(b"epub content")
    pdf_path.write_bytes(b"pdf content")

    books = [
        BookFile(
            name="Example",
            extension="EPUB",
            size_bytes=epub_path.stat().st_size,
            path=epub_path,
        ),
        BookFile(
            name="Document",
            extension="PDF",
            size_bytes=pdf_path.stat().st_size,
            path=pdf_path,
        ),
    ]

    database = DatabaseManager(database_path)
    database.save_scan_results(library_folder, books)

    database.update_book_metadata(
        epub_path,
        title="Example Book",
        author="Example Author",
        isbn=None,
        publisher=None,
        language="en",
        published_date=None,
        metadata_status="embedded",
    )

    statistics = database.get_dashboard_statistics()

    assert statistics["total_books"] == 2
    assert statistics["library_count"] == 1
    assert statistics["embedded_metadata"] == 1
    assert statistics["needs_metadata"] == 1
    assert statistics["metadata_health"] == 50
    assert statistics["formats"]["EPUB"] == 1
    assert statistics["formats"]["PDF"] == 1
    assert statistics["books_this_week"] == 2
    assert len(statistics["recent_books"]) == 2
    assert statistics["last_scanned_at"] is not None

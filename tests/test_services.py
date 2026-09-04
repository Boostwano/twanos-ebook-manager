"""Tests for UI-independent application services."""

from pathlib import Path

from metadata.models import MetadataResult
from metadata.provider_manager import ProviderManager
from services.dashboard_service import DashboardService
from services.library_service import LibraryService
from services.metadata_service import MetadataService
from services.scan_service import ScanService


class FakeLibraryDatabase:
    """Database double for LibraryService tests."""

    def __init__(self) -> None:
        self.filters = None

    def search_books(self, **filters):
        self.filters = filters
        return [
            {
                "title": None,
                "file_name": "Example.epub",
                "author": None,
                "isbn": None,
                "publisher": None,
                "published_date": None,
                "language": None,
                "file_format": "EPUB",
                "file_size": 2048,
                "metadata_status": "pending",
                "file_path": "C:/Books/Example.epub",
            }
        ]

    def count_books(self):
        return 7

    def get_library_filter_options(self):
        return ["EPUB", "PDF"], ["embedded", "pending"]


def test_library_service_returns_detached_records_and_filters() -> None:
    database = FakeLibraryDatabase()
    service = LibraryService(database)

    result = service.get_library(search_text="example", file_format="EPUB")
    options = service.get_filter_options()

    assert database.filters == {
        "search_text": "example",
        "file_format": "EPUB",
        "metadata_status": "",
    }
    assert result.total_count == 7
    assert result.records[0].title == "Example.epub"
    assert result.records[0].author == "Unknown"
    assert options.formats == ("EPUB", "PDF")
    assert options.metadata_statuses == ("embedded", "pending")


def test_dashboard_service_returns_immutable_snapshot() -> None:
    class FakeDashboardDatabase:
        def get_dashboard_statistics(self):
            return {
                "total_books": 4,
                "embedded_metadata": 3,
                "needs_metadata": 1,
                "missing_books": 2,
                "total_size": 4096,
                "library_count": 1,
                "metadata_health": 75,
                "formats": {"EPUB": 4},
            }

    data = DashboardService(FakeDashboardDatabase()).get_dashboard_data()

    assert data.total_books == 4
    assert data.metadata_health == 75
    assert dict(data.formats) == {"EPUB": 4}


def test_metadata_service_wraps_local_extractor(
    tmp_path: Path,
) -> None:
    book_path = tmp_path / "Example.epub"
    expected = MetadataResult(
        title="Example",
        extraction_status="embedded",
        confidence=1.0,
        provider_name="test",
    )
    calls = []

    class FakeProviderManager:
        def extract(self, path):
            calls.append(path)
            return expected

    result = MetadataService(FakeProviderManager()).extract(book_path)

    assert result is expected
    assert calls == [book_path]


def test_scan_service_discovers_recursively_and_persists_metadata(
    tmp_path: Path,
) -> None:
    library_folder = tmp_path / "library"
    nested_folder = library_folder / "nested"
    nested_folder.mkdir(parents=True)
    book_path = nested_folder / "Example.epub"
    book_path.write_bytes(b"book")
    (nested_folder / "ignore.docx").write_bytes(b"ignore")

    class FakeDatabase:
        def __init__(self):
            self.saved = None
            self.metadata = None

        def save_scan_results(self, folder, books):
            self.saved = (folder, books)
            return len(books)

        def update_book_metadata(self, path, **metadata):
            self.metadata = (path, metadata)

    class FakeProvider:
        @property
        def name(self):
            return "fake"

        def supports(self, path):
            return True

        def extract(self, path):
            return MetadataResult(
                title=path.stem,
                extraction_status="embedded",
                confidence=1.0,
                provider_name=self.name,
            )

    database = FakeDatabase()
    service = ScanService(
        database,
        ProviderManager([FakeProvider()]),
    )
    books = service.discover_books(
        library_folder,
        is_cancelled=lambda: False,
    )

    assert [book.path for book in books] == [book_path]
    assert service.save_discovered_books(library_folder, books) == 1
    metadata = service.process_metadata(books[0])
    assert metadata.title == "Example"
    assert database.saved == (library_folder, books)
    assert database.metadata[0] == book_path

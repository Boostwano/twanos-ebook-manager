"""Service and sizing coverage for RC6.4 smart search."""

from services.library_service import LibraryService
from ui.responsive import clamp, responsive_scale, scaled


class SearchDatabase:
    def __init__(self) -> None:
        self.filters = None

    def search_books(self, **filters):
        self.filters = filters
        return []

    def count_books(self):
        return 0

    def get_library_filter_options(self):
        return ["EPUB"], ["pending"]


def test_responsive_values_are_clamped() -> None:
    assert clamp(1, -10, 3) == 1
    assert clamp(1, 2, 3) == 2
    assert clamp(1, 10, 3) == 3
    assert responsive_scale(100, 100) == 0.76
    assert responsive_scale(10000, 10000) == 1.36
    assert scaled(0.1, 100, 20, 200) == 20
    assert scaled(5, 100, 20, 200) == 200


def test_search_filters_route_through_library_service() -> None:
    database = SearchDatabase()
    service = LibraryService(database)

    service.get_library(
        search_text="dune",
        file_format="EPUB",
        metadata_status="pending",
        author="Herbert",
        series="Dune",
        library_location="Classics",
    )

    assert database.filters == {
        "search_text": "dune",
        "file_format": "EPUB",
        "metadata_status": "pending",
        "author": "Herbert",
        "series": "Dune",
        "library_location": "Classics",
    }


def test_metadata_attention_uses_explicit_database_filter() -> None:
    database = SearchDatabase()
    service = LibraryService(database)

    result = service.get_library(metadata_attention=True)

    assert result.records == ()
    assert database.filters == {
        "search_text": "",
        "file_format": "",
        "metadata_status": "",
        "metadata_attention": True,
    }


def test_empty_and_no_result_searches_are_safe() -> None:
    database = SearchDatabase()
    service = LibraryService(database)

    empty = service.get_library(search_text="")
    missing = service.get_library(search_text="not in library")

    assert empty.records == ()
    assert empty.total_count == 0
    assert missing.records == ()
    assert missing.total_count == 0

"""Paging and stale-result tests for the shared Library model."""

from PySide6.QtWidgets import QApplication

from services.library_service import (
    LibraryPageResult,
    LibraryQuery,
    LibraryRecord,
)
from ui.library_model import LibraryModel


def _record(book_id: int) -> LibraryRecord:
    return LibraryRecord(
        title=f"Book {book_id}",
        author="Author",
        isbn="",
        publisher="",
        published_date="",
        language="",
        file_format="EPUB",
        file_size=book_id,
        metadata_status="embedded",
        file_path=f"C:/Books/{book_id}.epub",
        book_id=book_id,
    )


class FakePagedService:
    def __init__(self, total: int = 5) -> None:
        self.records = tuple(_record(index + 1) for index in range(total))
        self.queries = []

    def get_library_page(self, query: LibraryQuery) -> LibraryPageResult:
        self.queries.append(query)
        records = self.records[
            query.offset : query.offset + query.page_size
        ]
        return LibraryPageResult(
            records=records,
            matching_count=len(self.records),
            total_count=len(self.records),
            offset=query.offset,
            page_size=query.page_size,
            has_more=query.offset + len(records) < len(self.records),
        )


def test_model_loads_incremental_pages() -> None:
    QApplication.instance() or QApplication([])
    service = FakePagedService()
    model = LibraryModel(service, background_queries=False)

    model.set_query(LibraryQuery(page_size=2))
    assert model.rowCount() == 2
    assert model.canFetchMore()

    model.fetchMore()
    assert model.rowCount() == 4
    model.fetchMore()

    assert model.rowCount() == 5
    assert not model.canFetchMore()
    assert [query.offset for query in service.queries] == [0, 2, 4]


def test_stale_generation_result_is_ignored() -> None:
    QApplication.instance() or QApplication([])
    service = FakePagedService(1)
    model = LibraryModel(service, background_queries=False)
    model.set_query(LibraryQuery(search_text="current"))
    current_generation = model.generation
    stale = LibraryPageResult(
        records=(_record(99),),
        matching_count=1,
        total_count=1,
        offset=1,
        page_size=1,
        has_more=False,
    )

    model._handle_result(current_generation - 1, stale)

    assert model.rowCount() == 1
    assert model.record_at(0).book_id == 1

"""Tests for the shared RC6.5 Library grid/list page."""

from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSettings
from PySide6.QtWidgets import QApplication

from preferences import LibraryViewMode, PreferencesStore
from services.library_service import LibraryService
from ui.library_page import LibraryPage


def _row(index: int = 1) -> dict[str, object]:
    return {
        "id": index,
        "title": f"Example {index}",
        "file_name": f"Example {index}.epub",
        "author": "Author",
        "isbn": "",
        "publisher": "",
        "published_date": "",
        "language": "en",
        "file_format": "EPUB",
        "file_size": 1024,
        "metadata_status": "pending",
        "file_path": f"C:/Books/Example {index}.epub",
        "library_folder": "C:/Books",
        "series": "Examples",
        "series_number": float(index),
        "description": "",
        "cover_path": "",
        "discovered_at": "2026-01-01",
        "file_modified_at": "2026-01-02",
        "collections": "Reading List",
        "provider_rating": 4.3,
        "rating_count": 1250,
        "rating_source": "Google Books",
    }


class FakeDatabase:
    """Database stand-in implementing the RC6.5 Library contracts."""

    def __init__(self, rows=None) -> None:
        self.rows = list(rows if rows is not None else [_row()])
        self.search_calls: list[dict[str, object]] = []
        self.count_search_calls: list[dict[str, object]] = []

    def get_library_browser_filter_options(self):
        return {
            "formats": ["EPUB"],
            "metadata_statuses": ["pending"],
            "authors": ["Author"],
            "series": ["Examples"],
            "collections": ["Reading List"],
            "locations": ["C:/Books"],
        }

    def search_books(self, **filters):
        self.search_calls.append(filters)
        rows = self._filtered(filters)
        offset = int(filters.get("offset", 0))
        limit = filters.get("limit")
        return rows[offset : offset + int(limit)] if limit else rows[offset:]

    def count_search_books(self, **filters):
        self.count_search_calls.append(filters)
        return len(self._filtered(filters))

    def count_books(self):
        return len(self.rows)

    def list_collections(self):
        return [{"id": 1, "name": "Reading List", "book_count": 1}]

    def get_book_collection_ids(self, _book_id):
        return [1]

    def _filtered(self, filters):
        rows = self.rows
        search = str(filters.get("search_text", "")).casefold()
        if search:
            rows = [
                row
                for row in rows
                if search
                in " ".join(
                    str(row.get(key, ""))
                    for key in ("title", "author", "file_path")
                ).casefold()
            ]
        exact_fields = {
            "file_format": "file_format",
            "metadata_status": "metadata_status",
            "author": "author",
            "series": "series",
        }
        for filter_name, row_name in exact_fields.items():
            value = str(filters.get(filter_name, ""))
            if value:
                rows = [
                    row
                    for row in rows
                    if str(row.get(row_name, "")) == value
                ]
        formats = tuple(filters.get("file_formats", ()))
        if formats:
            rows = [row for row in rows if row.get("file_format") in formats]
        ratings = tuple(filters.get("provider_ratings", ()))
        if ratings:
            rows = [
                row
                for row in rows
                if int(float(row.get("provider_rating", 0)) + 0.5) in ratings
            ]
        collection = str(filters.get("collection", ""))
        if collection:
            rows = [
                row
                for row in rows
                if collection in str(row.get("collections", "")).split("\x1f")
            ]
        location = str(filters.get("library_location", ""))
        if location:
            rows = [
                row
                for row in rows
                if location == row.get("library_folder")
            ]
        return list(rows)


def _page(
    tmp_path: Path,
    rows=None,
) -> tuple[LibraryPage, FakeDatabase]:
    QApplication.instance() or QApplication([])
    tmp_path.mkdir(parents=True, exist_ok=True)
    settings = QSettings(
        str(tmp_path / "settings.ini"),
        QSettings.Format.IniFormat,
    )
    settings.clear()
    database = FakeDatabase(rows)
    page = LibraryPage(
        LibraryService(database),
        PreferencesStore(settings),
        background_queries=False,
    )
    return page, database


def test_activation_performs_one_paged_library_query(
    tmp_path: Path,
) -> None:
    page, database = _page(tmp_path)
    database.search_calls.clear()

    page.activate()

    assert len(database.search_calls) == 1
    assert database.search_calls[0]["limit"] == 100
    assert database.search_calls[0]["offset"] == 0
    page.deleteLater()


def test_metadata_update_clears_stale_filters_and_reselects_book(
    tmp_path: Path,
) -> None:
    page, _database = _page(tmp_path, [_row(1), _row(2)])
    page.search_input.setText("old title that no longer matches")
    page.format_filter.set_selected_values(("EPUB",))

    page.reveal_book_after_update(2)

    assert page.search_input.text() == ""
    assert page.format_filter.selected_values() == ()
    assert page.details_panel.book is not None
    assert page.details_panel.book.book_id == 2
    page.deleteLater()


def test_website_rating_is_read_only_in_book_details(tmp_path: Path) -> None:
    page, _database = _page(tmp_path, [_row(1)])
    page.selection_model.setCurrentIndex(
        page.model.index(0, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    assert page.details_panel.rating_label.text() == (
        "Website rating: 4.3/5 from Google Books (1,250 ratings)"
    )
    page.deleteLater()


def test_grid_and_list_share_model_selection_without_requery(
    tmp_path: Path,
) -> None:
    page, database = _page(tmp_path, [_row(1), _row(2)])
    index = page.model.index(1, 0)
    page.selection_model.setCurrentIndex(
        index,
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    query_count = len(database.search_calls)

    page.set_view_mode(LibraryViewMode.LIST)
    page.set_view_mode(LibraryViewMode.GRID)

    assert len(database.search_calls) == query_count
    assert page.library_grid.model() is page.library_table.model()
    assert (
        page.library_grid.selectionModel()
        is page.library_table.selectionModel()
    )
    assert page.selection_model.currentIndex().row() == 1
    assert page.details_panel.book.book_id == 2
    page.deleteLater()


def test_all_filters_reach_the_paged_query(tmp_path: Path) -> None:
    page, database = _page(tmp_path)
    page.search_input.blockSignals(True)
    page.search_input.setText("Example")
    page.search_input.blockSignals(False)
    page.rating_filter.set_selected_values((4, 5))
    for combo, value in (
        (page.format_filter, "EPUB"),
        (page.author_filter, "Author"),
        (page.series_filter, "Examples"),
        (page.collection_filter, "Reading List"),
        (page.location_filter, "C:/Books"),
        (page.status_filter, "pending"),
    ):
        combo.blockSignals(True)
        combo.setCurrentIndex(combo.findData(value))
        combo.blockSignals(False)

    page.refresh_library()

    assert database.search_calls[-1] == {
        "search_text": "Example",
        "file_format": "",
        "file_formats": ("EPUB",),
        "provider_ratings": (4, 5),
        "metadata_status": "pending",
        "author": "Author",
        "series": "Examples",
        "collection": "Reading List",
        "library_location": "C:/Books",
        "metadata_attention": False,
        "sort_field": "title",
        "sort_direction": "ascending",
        "limit": 100,
        "offset": 0,
    }
    page.deleteLater()


def test_details_selection_and_route_only_actions(tmp_path: Path) -> None:
    page, _database = _page(tmp_path)
    metadata = []
    reviews = []
    page.edit_metadata_requested.connect(metadata.append)
    page.review_issues_requested.connect(reviews.append)
    page.selection_model.setCurrentIndex(
        page.model.index(0, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )

    page.details_panel.metadata_button.click()
    page.details_panel.review_button.click()

    assert page.details_panel.book.title == "Example 1"
    assert metadata == ["Example 1"]
    assert reviews == ["Example 1"]
    assert not page.details_panel.open_button.isEnabled()
    assert page.details_panel.metadata_button.text() == "Metadata"
    assert {
        page.details_panel.open_button.objectName(),
        page.details_panel.folder_button.objectName(),
        page.details_panel.metadata_button.objectName(),
        page.details_panel.review_button.objectName(),
        page.details_panel.collection_button.objectName(),
    } == {
        "openBookAction",
        "openFolderAction",
        "viewMetadataAction",
        "reviewIssuesAction",
        "manageCollectionsAction",
    }
    page.deleteLater()


def test_empty_library_and_no_match_states_are_distinct(
    tmp_path: Path,
) -> None:
    empty_page, _database = _page(tmp_path / "empty", [])
    assert "Library is empty" in empty_page.state_label.text()
    empty_page.deleteLater()

    no_match_page, _database = _page(tmp_path / "filtered")
    no_match_page.search_input.blockSignals(True)
    no_match_page.search_input.setText("not present")
    no_match_page.search_input.blockSignals(False)
    no_match_page.refresh_library()

    assert "No books match" in no_match_page.state_label.text()
    no_match_page.deleteLater()


def test_compact_toolbar_reflows_without_right_edge_clipping(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, _database = _page(tmp_path)
    page.resize(700, 720)
    page.show()
    page._apply_responsive_layout()
    application.processEvents()

    sort_index = page.toolbar_layout.indexOf(page.sort_combo)
    sort_row, _column, _row_span, _column_span = (
        page.toolbar_layout.getItemPosition(sort_index)
    )
    toolbar_right = page.toolbar_widget.contentsRect().right()
    filter_right = page.filter_frame.contentsRect().right()

    assert page._compact
    assert sort_row == 2
    assert all(
        widget.geometry().right() <= toolbar_right
        for widget in page._toolbar_widgets
        if widget.isVisible()
    )
    assert all(
        combo.geometry().right() <= filter_right
        for combo in (
            page.format_filter,
            page.author_filter,
            page.series_filter,
            page.collection_filter,
            page.location_filter,
            page.status_filter,
        )
    )
    page.close()
    page.deleteLater()


def test_restored_window_keeps_details_panel_visible(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, _database = _page(tmp_path)
    page.resize(950, 760)
    page.show()
    page._apply_responsive_layout()
    page.selection_model.setCurrentIndex(
        page.model.index(0, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    application.processEvents()

    assert not page._compact
    assert page.details_button.isCheckable()
    assert page.details_button.text() == "Details"
    assert page.details_panel.parent() is page.splitter
    assert page.details_panel.isVisible()
    assert (
        page.details_panel.open_button.geometry().top()
        > page.details_panel.description_label.geometry().top()
    )
    action_tops = {
        button.geometry().top()
        for button in (
            page.details_panel.open_button,
            page.details_panel.folder_button,
            page.details_panel.metadata_button,
            page.details_panel.review_button,
            page.details_panel.collection_button,
        )
    }
    assert len(action_tops) == 1
    assert all(
        button.height() == page.details_panel.ACTION_BUTTON_HEIGHT
        and button.font().pixelSize()
        == page.details_panel.ACTION_BUTTON_FONT_SIZE
        for button in (
            page.details_panel.open_button,
            page.details_panel.folder_button,
            page.details_panel.metadata_button,
            page.details_panel.review_button,
            page.details_panel.collection_button,
        )
    )
    assert (
        page.details_panel.scroll_area.widget().width()
        <= page.details_panel.scroll_area.viewport().width()
    )
    page.close()
    page.deleteLater()


def test_compact_book_click_opens_details_and_back_restores_browser(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, _database = _page(tmp_path)
    page.resize(700, 720)
    page.show()
    page._apply_responsive_layout()
    application.processEvents()

    index = page.model.index(0, 0)
    page.library_grid.clicked.emit(index)
    application.processEvents()

    assert page._compact
    assert not page.details_button.isCheckable()
    assert page.details_button.text() == "View Details"
    assert page.details_panel.book.book_id == 1
    assert page.content_stack.currentWidget() is page.details_panel
    assert not page.search_input.isVisible()

    page.details_panel.back_requested.emit()
    application.processEvents()

    assert page.content_stack.currentWidget() is page.splitter
    assert page.search_input.isVisible()
    page.close()
    page.deleteLater()

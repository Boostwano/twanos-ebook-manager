"""First-class book search page with expandable filter structure."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from preferences import PreferencesStore
from services.library_service import LibraryRecord, LibraryService
from ui.book_actions import open_book
from ui.library_page import display_status
from ui.search_components import SearchResultItem


class SearchResultsPage(QWidget):
    """Search, refine, open, and locate matching library books."""

    view_in_library_requested = Signal(str)

    def __init__(
        self,
        service: LibraryService,
        preferences: PreferencesStore,
    ) -> None:
        super().__init__()
        self.service = service
        self.preferences = preferences

        heading = QLabel("Search Results")
        heading.setObjectName("pageTitle")
        self.result_summary = QLabel(
            "Search your library by title, author, ISBN, publisher, or file."
        )
        self.result_summary.setObjectName("pageDescription")
        self.result_summary.setWordWrap(True)

        self.query_input = QLineEdit()
        self.query_input.setObjectName("searchResultsQuery")
        self.query_input.setPlaceholderText(
            "Search title, author, ISBN, publisher, series, or filename…"
        )
        self.query_input.setClearButtonEnabled(True)
        self.query_input.returnPressed.connect(self.apply_search)
        self.query_input.textChanged.connect(self._schedule_search)
        search_button = QPushButton("Search")
        search_button.setObjectName("primaryButton")
        search_button.clicked.connect(self.apply_search)

        query_layout = QHBoxLayout()
        query_layout.setSpacing(8)
        query_layout.addWidget(self.query_input, 1)
        query_layout.addWidget(search_button)

        self.format_filter = QComboBox()
        self.format_filter.setObjectName("searchFormatFilter")
        self.format_filter.addItem("All formats", "")
        self.status_filter = QComboBox()
        self.status_filter.setObjectName("searchStatusFilter")
        self.status_filter.addItem("All metadata", "")
        self.author_filter = QLineEdit()
        self.author_filter.setObjectName("searchAuthorFilter")
        self.author_filter.setPlaceholderText("Any author")
        self.series_filter = QLineEdit()
        self.series_filter.setObjectName("searchSeriesFilter")
        self.series_filter.setPlaceholderText("Any series")
        self.location_filter = QLineEdit()
        self.location_filter.setObjectName("searchLocationFilter")
        self.location_filter.setPlaceholderText("Any library location")
        self.clear_button = QPushButton("Clear Filters")
        self.clear_button.clicked.connect(self.clear_filters)

        filter_frame = QFrame()
        filter_frame.setObjectName("searchFilters")
        filter_layout = QGridLayout(filter_frame)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setHorizontalSpacing(8)
        filter_layout.setVerticalSpacing(7)
        filter_layout.addWidget(self._filter_label("Format"), 0, 0)
        filter_layout.addWidget(self._filter_label("Metadata status"), 0, 1)
        filter_layout.addWidget(self._filter_label("Author"), 0, 2)
        filter_layout.addWidget(self.format_filter, 1, 0)
        filter_layout.addWidget(self.status_filter, 1, 1)
        filter_layout.addWidget(self.author_filter, 1, 2)
        filter_layout.addWidget(self._filter_label("Series"), 2, 0)
        filter_layout.addWidget(self._filter_label("Library location"), 2, 1)
        filter_layout.addWidget(self.series_filter, 3, 0)
        filter_layout.addWidget(
            self.location_filter,
            3,
            1,
            1,
            2,
        )
        filter_layout.addWidget(self.clear_button, 2, 2)
        for column in range(3):
            filter_layout.setColumnStretch(column, 1)

        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(8)
        self.results_layout.addStretch()

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("searchResultsScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidget(self.results_container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(11)
        layout.addWidget(heading)
        layout.addWidget(self.result_summary)
        layout.addLayout(query_layout)
        layout.addWidget(filter_frame)
        layout.addWidget(self.scroll_area, 1)

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self.apply_search)
        for control in (
            self.author_filter,
            self.series_filter,
            self.location_filter,
        ):
            control.textChanged.connect(self._schedule_search)
        self.format_filter.currentIndexChanged.connect(self.apply_search)
        self.status_filter.currentIndexChanged.connect(self.apply_search)

        self._load_filter_options()
        self._render_message(
            "Enter a search above to find books without changing the "
            "Home layout."
        )

    @staticmethod
    def _filter_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("filterLabel")
        return label

    @property
    def query(self) -> str:
        return self.query_input.text().strip()

    def set_query(self, query: str) -> None:
        """Populate a routed query and immediately show its results."""
        self.search_timer.stop()
        self.query_input.blockSignals(True)
        self.query_input.setText(query)
        self.query_input.blockSignals(False)
        self.apply_search()

    def activate(self) -> None:
        """Keep the current query while this page remains active."""
        return

    def _load_filter_options(self) -> None:
        options = self.service.get_filter_options()
        self.format_filter.blockSignals(True)
        self.status_filter.blockSignals(True)
        for file_format in options.formats:
            self.format_filter.addItem(file_format, file_format)
        for status in options.metadata_statuses:
            self.status_filter.addItem(display_status(status), status)
        self.format_filter.blockSignals(False)
        self.status_filter.blockSignals(False)

    def apply_search(self) -> None:
        """Run the current search and rebuild detailed result cards."""
        self.search_timer.stop()
        query = self.query
        if not query:
            self.result_summary.setText(
                "Search your library by title, author, ISBN, publisher, "
                "or file."
            )
            self._render_message(
                "Enter a search above to find books without changing the "
                "Home layout."
            )
            return

        result = self.service.get_library(
            search_text=query,
            file_format=str(self.format_filter.currentData() or ""),
            metadata_status=str(
                self.status_filter.currentData() or ""
            ),
            author=self.author_filter.text(),
            series=self.series_filter.text(),
            library_location=self.location_filter.text(),
        )
        count = len(result.records)
        noun = "result" if count == 1 else "results"
        self.result_summary.setText(
            f'{count:,} {noun} for “{query}”'
        )

        self._clear_results()
        if not result.records:
            self._add_message(
                f'No books matched “{query}”. Try a broader title, '
                "author, ISBN, or filename."
            )
        else:
            for book in result.records:
                item = SearchResultItem(book)
                item.open_requested.connect(self._open_book)
                item.secondary_requested.connect(
                    self._view_in_library
                )
                self.results_layout.addWidget(item)
        self.results_layout.addStretch()

    def clear_filters(self) -> None:
        """Clear refinements while retaining the routed search query."""
        self.search_timer.stop()
        controls = (
            self.format_filter,
            self.status_filter,
            self.author_filter,
            self.series_filter,
            self.location_filter,
        )
        for control in controls:
            control.blockSignals(True)
        self.format_filter.setCurrentIndex(0)
        self.status_filter.setCurrentIndex(0)
        self.author_filter.clear()
        self.series_filter.clear()
        self.location_filter.clear()
        for control in controls:
            control.blockSignals(False)
        self.apply_search()

    def _open_book(self, book: LibraryRecord) -> None:
        open_book(self, book, self.preferences)

    def _view_in_library(self, book: LibraryRecord) -> None:
        self.view_in_library_requested.emit(book.title)

    def _render_message(self, message: str) -> None:
        self._clear_results()
        self._add_message(message)
        self.results_layout.addStretch()

    def _add_message(self, message: str) -> None:
        label = QLabel(message)
        label.setObjectName("emptyResults")
        label.setWordWrap(True)
        self.results_layout.addWidget(label)

    def _clear_results(self) -> None:
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _schedule_search(self) -> None:
        self.search_timer.start()

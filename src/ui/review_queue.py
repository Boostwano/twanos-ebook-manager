"""Metadata-attention review queue backed by LibraryService."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
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
from ui.search_components import SearchResultItem


class ReviewQueuePage(QWidget):
    """Show books with weak metadata and a direct route to review."""

    review_requested = Signal(str)
    view_in_library_requested = Signal(str)

    def __init__(
        self,
        service: LibraryService,
        preferences: PreferencesStore,
    ) -> None:
        super().__init__()
        self.service = service
        self.preferences = preferences

        heading = QLabel("Review Queue")
        heading.setObjectName("pageTitle")
        description = QLabel(
            "Books needing metadata attention, with the weak or missing "
            "fields called out before any changes are made."
        )
        description.setObjectName("pageDescription")
        description.setWordWrap(True)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Filter metadata issues by title, author, ISBN, or filename…"
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._schedule_refresh)
        refresh_button = QPushButton("Refresh Queue")
        refresh_button.clicked.connect(self.refresh)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(refresh_button)

        self.summary = QLabel("Metadata attention: 0 books")
        self.summary.setObjectName("scanSummary")

        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(8)
        self.results_layout.addStretch()

        scroll_area = QScrollArea()
        scroll_area.setObjectName("reviewQueueScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(self.results_container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(11)
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addLayout(search_layout)
        layout.addWidget(self.summary)
        layout.addWidget(scroll_area, 1)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(250)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh()

    def activate(self, *, metadata_only: bool = True) -> None:
        """Refresh the actionable metadata filter on navigation."""
        if metadata_only:
            self.refresh()

    def refresh(self) -> None:
        self.refresh_timer.stop()
        result = self.service.get_library(
            search_text=self.search_input.text(),
            metadata_attention=True,
        )
        count = len(result.records)
        noun = "book" if count == 1 else "books"
        self.summary.setText(
            f"Metadata attention: {count:,} {noun}"
        )

        self._clear_results()
        if not result.records:
            message = QLabel(
                "No books currently need metadata attention."
            )
            message.setObjectName("emptyResults")
            message.setWordWrap(True)
            self.results_layout.addWidget(message)
        else:
            for book in result.records:
                item = SearchResultItem(
                    book,
                    show_issues=True,
                    secondary_text="Review Metadata",
                )
                item.open_requested.connect(self._open_book)
                item.secondary_requested.connect(self._review_book)
                self.results_layout.addWidget(item)
        self.results_layout.addStretch()

    def _open_book(self, book: LibraryRecord) -> None:
        open_book(self, book, self.preferences)

    def _review_book(self, book: LibraryRecord) -> None:
        self.review_requested.emit(book.title)

    def _clear_results(self) -> None:
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _schedule_refresh(self) -> None:
        self.refresh_timer.start()

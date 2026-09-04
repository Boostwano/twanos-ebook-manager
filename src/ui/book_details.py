"""Responsive book details and basic collection membership controls."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.library_service import (
    CollectionRecord,
    LibraryRecord,
    LibraryService,
)
from ui.library_format import (
    display_series,
    display_status,
    format_file_size,
)
from ui.thumbnail_cache import ThumbnailCache


class CollectionDialog(QDialog):
    """Create collections and atomically replace one book's memberships."""

    def __init__(
        self,
        service: LibraryService,
        book: LibraryRecord,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._book = book
        self._checkboxes: dict[int, QCheckBox] = {}
        self._empty_label: QLabel | None = None
        self.setWindowTitle(f"Collections — {book.title}")
        self.setMinimumWidth(390)

        message = QLabel(
            "Collection membership changes only Twano's catalogue. "
            "The ebook file is not moved or modified."
        )
        message.setWordWrap(True)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(4, 4, 4, 4)
        self._list_layout.setSpacing(5)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(190)
        scroll.setWidget(self._list_widget)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("New collection name")
        add_button = QPushButton("Create")
        add_button.clicked.connect(self._create_collection)
        self._name_input.returnPressed.connect(self._create_collection)

        create_layout = QHBoxLayout()
        create_layout.addWidget(self._name_input, 1)
        create_layout.addWidget(add_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(message)
        layout.addWidget(scroll, 1)
        layout.addLayout(create_layout)
        layout.addWidget(buttons)
        self._load_collections()

    def _load_collections(self) -> None:
        assigned = set(
            self._service.get_book_collection_ids(self._book.book_id)
        )
        for collection in self._service.get_collections():
            self._add_collection(collection, collection.collection_id in assigned)
        self._show_empty_state()

    def _add_collection(
        self,
        collection: CollectionRecord,
        checked: bool,
    ) -> None:
        existing = self._checkboxes.get(collection.collection_id)
        if existing is not None:
            existing.setChecked(checked)
            return
        if self._empty_label is not None:
            self._empty_label.deleteLater()
            self._empty_label = None
        checkbox = QCheckBox(
            f"{collection.name} ({collection.book_count:,})"
        )
        checkbox.setChecked(checked)
        checkbox.setProperty("collectionName", collection.name)
        self._checkboxes[collection.collection_id] = checkbox
        self._list_layout.addWidget(checkbox)

    def _show_empty_state(self) -> None:
        if self._checkboxes:
            return
        self._empty_label = QLabel(
            "No collections yet. Create the first one below."
        )
        self._empty_label.setObjectName("emptyResults")
        self._empty_label.setWordWrap(True)
        self._list_layout.addWidget(self._empty_label)

    def _create_collection(self) -> None:
        name = self._name_input.text()
        try:
            collection = self._service.create_collection(name)
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Collection not created", str(error))
            return
        self._add_collection(collection, True)
        self._name_input.clear()

    def _save(self) -> None:
        selected_ids = [
            collection_id
            for collection_id, checkbox in self._checkboxes.items()
            if checkbox.isChecked()
        ]
        try:
            self._service.set_book_collections(
                self._book.book_id,
                selected_ids,
            )
        except (ValueError, RuntimeError) as error:
            QMessageBox.critical(
                self,
                "Collections not saved",
                str(error),
            )
            return
        self.accept()


class BookDetailsPanel(QFrame):
    """One details implementation used in wide and compact layouts."""

    back_requested = Signal()
    open_book_requested = Signal(object)
    open_folder_requested = Signal(object)
    edit_metadata_requested = Signal(str)
    review_issues_requested = Signal(str)
    collections_changed = Signal()

    COVER_SIZE = QSize(190, 260)
    ACTION_BUTTON_HEIGHT = 42
    ACTION_BUTTON_FONT_SIZE = 13

    def __init__(
        self,
        service: LibraryService,
        thumbnail_cache: ThumbnailCache,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._cache = thumbnail_cache
        self._book: LibraryRecord | None = None
        self.setObjectName("bookDetails")
        self.setMinimumWidth(300)

        self.back_button = QPushButton("← Back to Library")
        self.back_button.clicked.connect(self.back_requested)
        self.back_button.setVisible(False)

        self.cover_label = QLabel("Select a book")
        self.cover_label.setObjectName("detailsCover")
        self.cover_label.setFixedSize(self.COVER_SIZE)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel("Book details")
        self.title_label.setObjectName("detailsTitle")
        self.title_label.setWordWrap(True)
        self.author_label = QLabel(
            "Select a Library item to see its details."
        )
        self.author_label.setObjectName("detailsAuthor")
        self.author_label.setWordWrap(True)
        self.series_label = QLabel()
        self.series_label.setObjectName("detailsSeries")
        self.series_label.setWordWrap(True)
        self.description_label = QLabel()
        self.description_label.setObjectName("detailsDescription")
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.facts = QLabel()
        self.facts.setObjectName("detailsFacts")
        self.facts.setWordWrap(True)
        self.facts.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.issues = QLabel()
        self.issues.setObjectName("detailsIssues")
        self.issues.setWordWrap(True)
        self.collections = QLabel()
        self.collections.setObjectName("detailsCollections")
        self.collections.setWordWrap(True)

        self.rating_label = QLabel("Website rating: Not available")
        self.rating_label.setObjectName("detailsWebsiteRating")
        self.rating_label.setWordWrap(True)

        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("openBookAction")
        self.open_button.setToolTip("Open this book in your configured reader")
        self.open_button.clicked.connect(self._open_book)
        self.folder_button = QPushButton("Folder")
        self.folder_button.setObjectName("openFolderAction")
        self.folder_button.setToolTip("Open the folder containing this book")
        self.folder_button.clicked.connect(self._open_folder)
        self.metadata_button = QPushButton("Metadata")
        self.metadata_button.setObjectName("viewMetadataAction")
        self.metadata_button.setToolTip(
            "Metadata editing arrives after Twano's protection and Undo "
            "foundation. RC6.5 opens the selected book's read-only context."
        )
        self.metadata_button.clicked.connect(self._edit_metadata)
        self.review_button = QPushButton("Issues")
        self.review_button.setObjectName("reviewIssuesAction")
        self.review_button.clicked.connect(self._review_issues)
        self.collection_button = QPushButton("Collections")
        self.collection_button.setObjectName("manageCollectionsAction")
        self.collection_button.clicked.connect(self._manage_collections)
        for button in (
            self.open_button,
            self.folder_button,
            self.metadata_button,
            self.review_button,
            self.collection_button,
        ):
            button.setMinimumWidth(0)
            button.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Fixed,
            )
            button.setFixedHeight(self.ACTION_BUTTON_HEIGHT)
            button.setStyleSheet(
                "QPushButton { padding: 4px 3px; "
                f"font-size: {self.ACTION_BUTTON_FONT_SIZE}px; }}"
            )

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(5)
        for button in (
            self.open_button,
            self.folder_button,
            self.metadata_button,
            self.review_button,
            self.collection_button,
        ):
            action_row.addWidget(button, 1)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 14, 14, 18)
        content_layout.setSpacing(8)
        content_layout.addWidget(self.title_label)
        content_layout.addWidget(self.author_label)
        content_layout.addWidget(self.series_label)
        content_layout.addWidget(
            self.cover_label,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        content_layout.addWidget(self.description_label)
        content_layout.addLayout(action_row)
        content_layout.addWidget(self.rating_label)
        content_layout.addWidget(self.facts)
        content_layout.addWidget(self.issues)
        content_layout.addWidget(self.collections)
        content_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setWidget(content)
        self.scroll_area = scroll

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.back_button)
        layout.addWidget(scroll, 1)

        self._cache.thumbnail_ready.connect(self._thumbnail_changed)
        self._cache.thumbnail_failed.connect(self._thumbnail_failed)
        self._set_actions_enabled(False)

    @property
    def book(self) -> LibraryRecord | None:
        return self._book

    def set_book(self, book: LibraryRecord | None) -> None:
        self._book = book
        if book is None:
            self.cover_label.setText("Select a book")
            self.cover_label.clear()
            self.cover_label.setText("Select a book")
            self.title_label.setText("Book details")
            self.author_label.setText(
                "Select a Library item to see its details."
            )
            for label in (
                self.series_label,
                self.description_label,
                self.facts,
                self.issues,
                self.collections,
                self.rating_label,
            ):
                label.clear()
            self.rating_label.setText("Website rating: Not available")
            self._set_actions_enabled(False)
            return

        self.title_label.setText(book.title)
        self.author_label.setText(f"by {book.author}")
        self.series_label.setText(display_series(book))
        self.description_label.setText(
            book.description or "No description is available."
        )
        file_state = (
            "Available"
            if Path(book.file_path).is_file()
            else "File not found"
        )
        facts = [
            f"Format: {book.file_format or 'Unknown'}",
            f"Size: {format_file_size(book.file_size)}",
            f"ISBN: {book.isbn or 'Not available'}",
            f"Publisher: {book.publisher or 'Not available'}",
            f"Published: {book.published_date or 'Not available'}",
            f"Language: {book.language or 'Not available'}",
            f"Metadata: {display_status(book.metadata_status)}",
            f"Modified: {book.file_modified_at or 'Not available'}",
            f"File: {book.file_path or 'Not available'}",
            f"File state: {file_state}",
        ]
        self.facts.setText("\n".join(facts))
        self.issues.setText(
            "Issues: "
            + (
                "; ".join(book.metadata_issues)
                if book.metadata_issues
                else "No metadata issues detected."
            )
        )
        self.collections.setText(
            "Collections: "
            + (
                ", ".join(book.collections)
                if book.collections
                else "None"
            )
        )
        if book.provider_rating > 0:
            source = book.rating_source or "metadata provider"
            count = (
                f" ({book.rating_count:,} ratings)"
                if book.rating_count > 0
                else ""
            )
            self.rating_label.setText(
                f"Website rating: {book.provider_rating:.1f}/5 from "
                f"{source}{count}"
            )
        else:
            self.rating_label.setText("Website rating: Not available")
        self._set_actions_enabled(True)
        self._refresh_cover()

    def _set_actions_enabled(self, enabled: bool) -> None:
        for button in (
            self.open_button,
            self.folder_button,
            self.metadata_button,
            self.review_button,
            self.collection_button,
        ):
            button.setEnabled(enabled)

        if not enabled or self._book is None:
            return
        file_available = Path(self._book.file_path).is_file()
        folder_available = self._folder_path(self._book).is_dir()
        self.open_button.setEnabled(file_available)
        self.open_button.setToolTip(
            "" if file_available else "The ebook file is unavailable."
        )
        self.folder_button.setEnabled(folder_available)
        self.folder_button.setToolTip(
            ""
            if folder_available
            else "The containing folder is unavailable."
        )
        self.review_button.setEnabled(bool(self._book.metadata_issues))
        self.review_button.setToolTip(
            ""
            if self._book.metadata_issues
            else "No metadata issues are recorded for this book."
        )

    def _refresh_cover(self) -> None:
        if self._book is None:
            return
        pixmap = self._cache.get_thumbnail(
            self._book,
            self.COVER_SIZE,
        )
        if pixmap is not None:
            self.cover_label.setPixmap(pixmap)
            self.cover_label.setText("")
            return
        state = self._cache.state(self._book, self.COVER_SIZE)
        labels = {
            "missing": "NO COVER",
            "failed": "COVER UNAVAILABLE",
            "loading": "LOADING COVER…",
        }
        self.cover_label.clear()
        self.cover_label.setText(labels.get(state, "NO COVER"))

    def _thumbnail_changed(self, book_id: int) -> None:
        if self._book is not None and self._book.book_id == book_id:
            self._refresh_cover()

    def _thumbnail_failed(self, book_id: int, _message: str) -> None:
        if self._book is not None and self._book.book_id == book_id:
            self._refresh_cover()

    def _open_book(self) -> None:
        if self._book is not None:
            self.open_book_requested.emit(self._book)

    def _open_folder(self) -> None:
        if self._book is not None:
            self.open_folder_requested.emit(self._book)

    def _edit_metadata(self) -> None:
        if self._book is not None:
            self.edit_metadata_requested.emit(self._book.title)

    def _review_issues(self) -> None:
        if self._book is not None:
            self.review_issues_requested.emit(self._book.title)

    def _manage_collections(self) -> None:
        if self._book is None:
            return
        dialog = CollectionDialog(self._service, self._book, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.collections_changed.emit()

    @staticmethod
    def _folder_path(book: LibraryRecord) -> Path:
        path = Path(book.file_path)
        if path.parent.is_dir():
            return path.parent
        return Path(book.library_folder)

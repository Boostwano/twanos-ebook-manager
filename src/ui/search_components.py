"""Reusable fields, suggestions, covers, and book result rows."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.library_service import LibraryRecord


class SearchField(QLineEdit):
    """Search box that keeps suggestion navigation on the text field."""

    submitted = Signal()
    dismissed = Signal()
    selection_requested = Signal(int)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Down:
            self.selection_requested.emit(1)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Up:
            self.selection_requested.emit(-1)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.submitted.emit()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.dismissed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class CoverThumbnail(QLabel):
    """Use a local cover when available, otherwise a calm letter tile."""

    def __init__(
        self,
        book: LibraryRecord,
        *,
        width: int = 46,
        height: int = 62,
    ) -> None:
        super().__init__()
        self.setObjectName("resultCover")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(width, height)

        cover_path = Path(book.cover_path) if book.cover_path else None
        if cover_path and cover_path.is_file():
            pixmap = QPixmap(str(cover_path))
            if not pixmap.isNull():
                self.setPixmap(
                    pixmap.scaled(
                        width,
                        height,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return

        self.setText((book.title[:1] or "B").upper())
        self.setToolTip("Cover not available")


class SuggestionRow(QWidget):
    """Compact visual content for one floating suggestion."""

    def __init__(self, book: LibraryRecord) -> None:
        super().__init__()
        cover = CoverThumbnail(book, width=30, height=42)
        title = QLabel(book.title)
        title.setObjectName("suggestionTitle")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        details = QLabel(
            f"{book.author}  ·  {book.file_format.upper()}"
        )
        details.setObjectName("suggestionDetails")

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        text_layout.addWidget(title)
        text_layout.addWidget(details)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(9)
        layout.addWidget(cover)
        layout.addLayout(text_layout, 1)


class SearchSuggestionPopup(QFrame):
    """A child overlay that never participates in the Home layout."""

    book_requested = Signal(object)
    all_results_requested = Signal(str)

    MAXIMUM_HEIGHT = 350

    def __init__(self, owner: QWidget, anchor: QWidget) -> None:
        super().__init__(owner)
        self.setObjectName("searchSuggestionPopup")
        self.anchor = anchor
        self.query = ""

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("suggestionList")
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.list_widget.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.list_widget.itemClicked.connect(self._activate_item)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self.list_widget)

        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)
        self.hide()

    def show_results(
        self,
        query: str,
        records: tuple[LibraryRecord, ...] | list[LibraryRecord],
    ) -> None:
        """Render up to five matches plus the full-results destination."""
        self.query = query.strip()
        self.list_widget.clear()

        for book in tuple(records)[:5]:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, book)
            item.setSizeHint(QSize(0, 52))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, SuggestionRow(book))

        if not records:
            empty_item = QListWidgetItem("No matching books found")
            empty_item.setData(Qt.ItemDataRole.UserRole, None)
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_item.setSizeHint(QSize(0, 38))
            self.list_widget.addItem(empty_item)

        more_item = QListWidgetItem(
            f'View all results for “{self.query}”'
        )
        more_item.setData(Qt.ItemDataRole.UserRole, self.query)
        more_item.setData(Qt.ItemDataRole.UserRole + 1, "all")
        more_item.setSizeHint(QSize(0, 40))
        self.list_widget.addItem(more_item)

        self.list_widget.setCurrentItem(None)
        self._place_below_anchor()
        self.show()
        self.raise_()

    def _place_below_anchor(self) -> None:
        owner = self.parentWidget()
        if owner is None:
            return
        position = self.anchor.mapTo(
            owner,
            QPoint(0, self.anchor.height() + 4),
        )
        width = min(
            max(360, self.anchor.width()),
            720,
            max(360, owner.width() - position.x() - 12),
        )
        content_height = sum(
            self.list_widget.sizeHintForRow(row)
            for row in range(self.list_widget.count())
        ) + 4
        height = min(self.MAXIMUM_HEIGHT, max(44, content_height))
        self.setGeometry(position.x(), position.y(), width, height)

    def reposition(self) -> None:
        if self.isVisible():
            self._place_below_anchor()

    def select_relative(self, direction: int) -> None:
        """Move selection while the text field retains keyboard focus."""
        if not self.isVisible() or self.list_widget.count() == 0:
            return
        selectable_rows = [
            row
            for row in range(self.list_widget.count())
            if self.list_widget.item(row).flags()
            & Qt.ItemFlag.ItemIsSelectable
        ]
        if not selectable_rows:
            return
        current_row = self.list_widget.currentRow()
        if current_row not in selectable_rows:
            next_row = (
                selectable_rows[0]
                if direction > 0
                else selectable_rows[-1]
            )
        else:
            current_index = selectable_rows.index(current_row)
            next_row = selectable_rows[
                (current_index + direction) % len(selectable_rows)
            ]
        self.list_widget.setCurrentRow(next_row)

    def activate_selected(self) -> bool:
        """Open the selected row; return false when nothing is selected."""
        item = self.list_widget.currentItem()
        if item is None:
            return False
        self._activate_item(item)
        return True

    def close_popup(self) -> None:
        self.list_widget.setCurrentItem(None)
        self.hide()

    def _activate_item(self, item: QListWidgetItem) -> None:
        if item.data(Qt.ItemDataRole.UserRole + 1) == "all":
            query = str(item.data(Qt.ItemDataRole.UserRole) or self.query)
            self.close_popup()
            self.all_results_requested.emit(query)
            return
        book = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(book, LibraryRecord):
            self.close_popup()
            self.book_requested.emit(book)

    def eventFilter(self, watched, event: QEvent) -> bool:
        if (
            self.isVisible()
            and event.type() == QEvent.Type.MouseButtonPress
            and isinstance(event, QMouseEvent)
        ):
            global_position = event.globalPosition().toPoint()
            popup_rectangle = self.rect().translated(
                self.mapToGlobal(QPoint(0, 0))
            )
            anchor_rectangle = self.anchor.rect().translated(
                self.anchor.mapToGlobal(QPoint(0, 0))
            )
            if (
                not popup_rectangle.contains(global_position)
                and not anchor_rectangle.contains(global_position)
            ):
                self.close_popup()
        return super().eventFilter(watched, event)


class SearchResultItem(QFrame):
    """Reusable detailed search or review result."""

    open_requested = Signal(object)
    secondary_requested = Signal(object)

    def __init__(
        self,
        book: LibraryRecord,
        *,
        show_issues: bool = False,
        secondary_text: str = "View in Library",
    ) -> None:
        super().__init__()
        self.book = book
        self.setObjectName("searchResultItem")

        cover = CoverThumbnail(book, width=54, height=74)

        title = QLabel(book.title)
        title.setObjectName("resultTitle")
        title.setWordWrap(True)
        byline = QLabel(book.author)
        byline.setObjectName("resultByline")

        series_text = f"Series: {book.series}" if book.series else ""
        series_label = QLabel(series_text)
        series_label.setObjectName("resultSeries")
        series_label.setVisible(bool(series_text))

        status = book.metadata_status.replace("_", " ").title()
        facts = QLabel(
            f"{book.file_format.upper()}  ·  Metadata: {status}"
        )
        facts.setObjectName("resultFacts")
        filename = book.file_name or Path(book.file_path).name
        location_text = filename
        if book.library_folder:
            location_text += f"  ·  {book.library_folder}"
        location = QLabel(location_text)
        location.setObjectName("resultLocation")
        location.setWordWrap(True)
        location.setToolTip(book.file_path)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)
        text_layout.addWidget(title)
        text_layout.addWidget(byline)
        text_layout.addWidget(series_label)
        text_layout.addWidget(facts)
        text_layout.addWidget(location)

        if show_issues:
            issues = QLabel(
                "Needs attention: "
                + (
                    ", ".join(book.metadata_issues)
                    if book.metadata_issues
                    else "Metadata review requested"
                )
            )
            issues.setObjectName("resultIssues")
            issues.setWordWrap(True)
            text_layout.addWidget(issues)

        open_button = QPushButton("Open Book")
        open_button.setObjectName("resultOpen")
        open_button.clicked.connect(
            lambda: self.open_requested.emit(self.book)
        )
        secondary_button = QPushButton(secondary_text)
        secondary_button.setObjectName("resultView")
        secondary_button.clicked.connect(
            lambda: self.secondary_requested.emit(self.book)
        )

        actions = QVBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        actions.addWidget(open_button)
        actions.addWidget(secondary_button)
        actions.addStretch()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(13)
        layout.addWidget(cover, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text_layout, 1)
        layout.addLayout(actions)

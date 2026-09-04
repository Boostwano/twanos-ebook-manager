"""Explainable duplicate review with recoverable quarantine."""

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.duplicate_service import (
    DuplicateGroup,
    DuplicateService,
)
from workers.duplicate_scan_worker import DuplicateScanWorker


class DuplicatePage(QWidget):
    """Review exact copies separately from possible alternate editions."""

    catalogue_changed = Signal()
    view_in_library_requested = Signal(str)
    metadata_requested = Signal(str)
    work_stopped = Signal()

    def __init__(self, service: DuplicateService) -> None:
        super().__init__()
        self.service = service
        self.groups: tuple[DuplicateGroup, ...] = ()
        self.current_group: DuplicateGroup | None = None
        self.scan_thread: QThread | None = None
        self.scan_worker: DuplicateScanWorker | None = None

        title = QLabel("Duplicate Review")
        title.setObjectName("pageTitle")
        description = QLabel(
            "Confirmed file or ebook-content copies are separated from "
            "possible editions. Twano never deletes a book automatically."
        )
        description.setObjectName("pageDescription")
        description.setWordWrap(True)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_groups_tab(), "Possible Duplicates")
        self.tabs.addTab(self._build_quarantine_tab(), "Recoverable Quarantine")

        self.status_label = QLabel("Choose Refresh Duplicate Check to begin.")
        self.status_label.setObjectName("duplicateStatus")
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.status_label)
        self._refresh_quarantine()

    def _build_groups_tab(self) -> QWidget:
        self.group_table = QTableWidget(0, 4)
        self.group_table.setObjectName("duplicateGroupTable")
        self.group_table.setHorizontalHeaderLabels(
            ("Group", "Confidence", "Evidence", "Books")
        )
        self.group_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.group_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.group_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.group_table.itemSelectionChanged.connect(
            self._group_selection_changed
        )

        self.book_table = QTableWidget(0, 5)
        self.book_table.setObjectName("duplicateBookTable")
        self.book_table.setHorizontalHeaderLabels(
            ("Title", "Author", "Format", "Size", "Location")
        )
        self.book_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.book_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.book_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.refresh_button = QPushButton("Refresh Check")
        self.refresh_button.setObjectName("duplicateRefreshAction")
        self.refresh_button.clicked.connect(self.refresh)
        self.keep_button = QPushButton("Keep as Intentional Editions")
        self.keep_button.setObjectName("duplicateKeepAction")
        self.keep_button.clicked.connect(self._mark_intentional)
        self.preferred_button = QPushButton("Review Preferred Metadata")
        self.preferred_button.setObjectName("duplicatePreferredAction")
        self.preferred_button.clicked.connect(self._review_metadata)
        self.library_button = QPushButton("View in Library")
        self.library_button.setObjectName("duplicateLibraryAction")
        self.library_button.clicked.connect(self._view_in_library)
        self.quarantine_button = QPushButton("Quarantine Exact Copy")
        self.quarantine_button.setObjectName("duplicateQuarantineAction")
        self.quarantine_button.clicked.connect(self._quarantine)

        actions = QGridLayout()
        actions.setHorizontalSpacing(7)
        actions.setVerticalSpacing(7)
        actions.addWidget(self.refresh_button, 0, 0)
        actions.addWidget(self.keep_button, 0, 1)
        actions.addWidget(self.preferred_button, 0, 2)
        actions.addWidget(self.library_button, 1, 0)
        actions.addWidget(self.quarantine_button, 1, 1, 1, 2)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(actions)
        layout.addWidget(self.group_table, 2)
        layout.addWidget(self.book_table, 3)
        return page

    def _build_quarantine_tab(self) -> QWidget:
        self.quarantine_table = QTableWidget(0, 4)
        self.quarantine_table.setObjectName("quarantineTable")
        self.quarantine_table.setHorizontalHeaderLabels(
            ("Book", "Original location", "Quarantine location", "Moved")
        )
        self.quarantine_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.quarantine_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.quarantine_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.restore_button = QPushButton("Restore Selected Book")
        self.restore_button.setObjectName("quarantineRestoreAction")
        self.restore_button.clicked.connect(self._restore)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.quarantine_table, 1)
        layout.addWidget(self.restore_button, 0, Qt.AlignmentFlag.AlignRight)
        return page

    def activate(self) -> None:
        if not self.groups:
            self.refresh()
        self._refresh_quarantine()

    def refresh(self) -> None:
        if self.scan_thread is not None:
            return
        self.current_group = None
        self.group_table.clearSelection()
        self.book_table.setRowCount(0)
        self._set_group_actions_enabled(False)
        self.refresh_button.setEnabled(False)
        self.status_label.setText(
            "Checking likely matches. File contents are compared only when "
            "two books have the same size…"
        )
        self.scan_thread = QThread(self)
        self.scan_worker = DuplicateScanWorker(self.service)
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.completed.connect(self._scan_completed)
        self.scan_worker.failed.connect(self.status_label.setText)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.finished.connect(self.scan_worker.deleteLater)
        self.scan_thread.finished.connect(self._scan_finished)
        self.scan_thread.finished.connect(self.scan_thread.deleteLater)
        self.scan_thread.start()

    def _scan_completed(self, groups: tuple[DuplicateGroup, ...]) -> None:
        self.groups = tuple(groups)
        self.current_group = None
        self.group_table.blockSignals(True)
        self.group_table.clearSelection()
        self.group_table.setRowCount(len(self.groups))
        for row, group in enumerate(self.groups):
            lead = group.books[0]
            values = (
                lead.title,
                group.confidence,
                ", ".join(group.evidence),
                str(len(group.books)),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, group)
                self.group_table.setItem(row, column, item)
        self.group_table.blockSignals(False)
        if self.groups:
            self.group_table.selectRow(0)
            self._group_selection_changed()
            exact_count = sum(group.exact_copy for group in self.groups)
            self.status_label.setText(
                f"Found {len(self.groups)} groups: {exact_count} exact "
                "or content-copy groups and "
                f"{len(self.groups) - exact_count} possible edition groups."
            )
        else:
            self.current_group = None
            self.book_table.setRowCount(0)
            self._set_group_actions_enabled(False)
            self.status_label.setText(
                "No duplicate groups were found. Intentional editions you "
                "previously reviewed remain hidden."
            )

    def _scan_finished(self) -> None:
        self.scan_thread = None
        self.scan_worker = None
        self.refresh_button.setEnabled(True)
        self.work_stopped.emit()

    def is_busy(self) -> bool:
        return self.scan_thread is not None

    def _group_selection_changed(self) -> None:
        row = self.group_table.currentRow()
        if row < 0:
            self.current_group = None
            self.book_table.setRowCount(0)
            self._set_group_actions_enabled(False)
            return
        item = self.group_table.item(row, 0)
        group = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.current_group = (
            group if isinstance(group, DuplicateGroup) else None
        )
        self._populate_books()

    def _set_group_actions_enabled(self, enabled: bool) -> None:
        """Keep actions bound to the currently displayed duplicate group."""
        self.keep_button.setEnabled(enabled)
        self.preferred_button.setEnabled(enabled)
        self.library_button.setEnabled(enabled)
        self.quarantine_button.setEnabled(
            enabled
            and bool(self.current_group and self.current_group.exact_copy)
        )

    def _populate_books(self) -> None:
        books = self.current_group.books if self.current_group else ()
        self.book_table.setRowCount(len(books))
        for row, book in enumerate(books):
            size = (
                f"{book.file_size / (1024 * 1024):.1f} MB"
                if book.file_size
                else "Unknown"
            )
            values = (
                book.title,
                book.author,
                book.file_format,
                size,
                book.file_path,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, book.book_id)
                self.book_table.setItem(row, column, item)
        if books:
            self.book_table.selectRow(0)
        self._set_group_actions_enabled(bool(books))

    def _selected_book_id(self) -> int | None:
        row = self.book_table.currentRow()
        item = self.book_table.item(row, 0) if row >= 0 else None
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _selected_title(self) -> str:
        row = self.book_table.currentRow()
        item = self.book_table.item(row, 0) if row >= 0 else None
        return item.text() if item else ""

    def _mark_intentional(self) -> None:
        if self.current_group is None:
            return
        self.service.mark_intentional(self.current_group.group_key)
        self.status_label.setText(
            "This group is now treated as intentional editions. You can "
            "include reviewed groups in a future duplicate check if needed."
        )
        self.groups = tuple(
            group
            for group in self.groups
            if group.group_key != self.current_group.group_key
        )
        self._scan_completed(self.groups)

    def _review_metadata(self) -> None:
        title = self._selected_title()
        if title:
            self.metadata_requested.emit(title)

    def _view_in_library(self) -> None:
        title = self._selected_title()
        if title:
            self.view_in_library_requested.emit(title)

    def _quarantine(self) -> None:
        book_id = self._selected_book_id()
        if self.current_group is None or book_id is None:
            return
        answer = QMessageBox.warning(
            self,
            "Move Exact Copy to Quarantine?",
            (
                "The selected file will be moved into Twano's recoverable "
                "quarantine. At least one confirmed copy will remain. "
                + (
                    "The readable EPUB contents match; only recognised "
                    "vendor catalogue metadata differs. "
                    if "Same ebook contents" in self.current_group.evidence
                    and "Exact file contents" not in self.current_group.evidence
                    else "The complete file contents match exactly. "
                )
                + "You can restore it from the Quarantine tab."
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            destination = self.service.quarantine_exact_copy(
                self.current_group,
                book_id,
            )
        except Exception as error:
            self.status_label.setText(str(error))
            return
        self.status_label.setText(
            f"The exact copy was moved safely to {destination}."
        )
        self.catalogue_changed.emit()
        self.groups = ()
        self.current_group = None
        self.group_table.clearSelection()
        self.book_table.setRowCount(0)
        self._set_group_actions_enabled(False)
        self.refresh()
        self._refresh_quarantine()

    def _refresh_quarantine(self) -> None:
        rows = self.service.list_quarantine()
        self.quarantine_table.setRowCount(len(rows))
        for row_number, row in enumerate(rows):
            values = (
                str(row.get("title") or row.get("file_name") or "Untitled"),
                str(row["original_path"]),
                str(row["quarantine_path"]),
                str(row["created_at"]),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    (int(row["id"]), int(row["book_id"])),
                )
                self.quarantine_table.setItem(row_number, column, item)

    def _restore(self) -> None:
        row = self.quarantine_table.currentRow()
        item = self.quarantine_table.item(row, 0) if row >= 0 else None
        if item is None:
            return
        quarantine_id, _book_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            destination = self.service.restore_quarantined(quarantine_id)
        except Exception as error:
            self.status_label.setText(str(error))
            return
        self.status_label.setText(
            f"The book was restored to {destination}."
        )
        self.catalogue_changed.emit()
        self._refresh_quarantine()

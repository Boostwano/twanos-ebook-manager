"""Library scanning page with background processing."""

import logging
from collections.abc import Callable
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QGridLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.scanner import BookFile
from preferences import PreferencesStore, ProtectionMode
from services.scan_service import (
    LibrarySource,
    ScanAnalysisItem,
    ScanAnalysisResult,
    ScanApplyResult,
    ScanItemStatus,
    ScanService,
    SourceRemovalResult,
    SourceConnectionResult,
    SourceConnectionStatus,
)
from ui.library_format import format_file_size
from ui.library_source_dialog import (
    LibrarySourceDialog,
    MultipleLibrarySourcesDialog,
)
from workers.scan_worker import ScanWorker
from workers.scan_analysis_worker import ScanAnalysisWorker
from workers.scan_apply_worker import ScanApplyWorker
from workers.source_connection_worker import SourceConnectionWorker
from workers.source_removal_worker import SourceRemovalWorker
from ui.theme import configure_table


logger = logging.getLogger(__name__)

def format_elapsed_time(seconds: float) -> str:
    """Format elapsed seconds as HH:MM:SS."""
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class ScanPage(QWidget):
    """Select and scan an eBook library folder."""

    scan_stopped = Signal()
    catalogue_changed = Signal()

    def __init__(
        self,
        scan_service_factory: Callable[[], ScanService],
        preferences: PreferencesStore | None = None,
    ) -> None:
        super().__init__()

        self.scan_service_factory = scan_service_factory
        self.preferences = preferences
        self._protection_mode = (
            preferences.load_home_preferences().protection_mode
            if preferences is not None
            else ProtectionMode.STANDARD
        )
        self.source_service = scan_service_factory()
        self.sources: tuple[LibrarySource, ...] = ()
        self.selected_source_id: int | None = None
        self.selected_folder: Path | None = None
        self.scan_thread: QThread | None = None
        self.scan_worker: ScanWorker | None = None
        self.analysis_thread: QThread | None = None
        self.analysis_worker: ScanAnalysisWorker | None = None
        self.current_analysis: ScanAnalysisResult | None = None
        self.current_analyses: tuple[ScanAnalysisResult, ...] = ()
        self._analysis_queue: list[LibrarySource] = []
        self._batch_analysis_results: list[ScanAnalysisResult] = []
        self._batch_analysis_failures: list[str] = []
        self._batch_analysis_total = 0
        self._batch_analysis_active = False
        self.apply_thread: QThread | None = None
        self.apply_worker: ScanApplyWorker | None = None
        self._batch_apply_queue: list[ScanAnalysisResult] = []
        self._batch_apply_results: list[ScanApplyResult] = []
        self._batch_apply_total = 0
        self._batch_apply_active = False
        self.connection_thread: QThread | None = None
        self.connection_worker: SourceConnectionWorker | None = None
        self.removal_thread: QThread | None = None
        self.removal_worker: SourceRemovalWorker | None = None
        self.scan_started_at: float | None = None
        self.processed_count = 0
        self.total_count = 0

        heading = QLabel("Scan Library")
        heading.setObjectName("pageTitle")

        description = QLabel(
            "Manage watched locations and test that Twano can read them. "
            "Source settings never move or change ebook files."
        )
        description.setObjectName("pageDescription")
        description.setWordWrap(True)

        source_heading = QLabel("Watched Library Sources")
        source_heading.setObjectName("sectionTitle")

        source_help = QLabel(
            "Add local folders, mapped drives, or UNC locations. Remove Watch "
            "also removes that source's books from the Twano Library, but "
            "never changes the folder or ebook files."
        )
        source_help.setWordWrap(True)

        self.source_table = QTableWidget(0, 6)
        self.source_table.setHorizontalHeaderLabels(
            ["Source", "Location", "Connection", "Watch", "Rules", "Last scan"]
        )
        configure_table(self.source_table, row_height=30)
        self.source_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.source_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.source_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.source_table.setMinimumHeight(145)
        source_header = self.source_table.horizontalHeader()
        source_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        source_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        source_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        source_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        source_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        source_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.source_table.currentCellChanged.connect(
            self._source_selection_changed
        )

        self.select_button = QPushButton("Add Folders")
        self.select_button.setObjectName("addSourceAction")
        self.select_button.clicked.connect(self._select_folder)
        self.edit_source_button = QPushButton("Edit Source")
        self.edit_source_button.setObjectName("editSourceAction")
        self.edit_source_button.clicked.connect(self._edit_source)
        self.test_source_button = QPushButton("Test Connection")
        self.test_source_button.setObjectName("testConnectionAction")
        self.test_source_button.clicked.connect(self._test_source_connection)
        self.toggle_source_button = QPushButton("Disable Source")
        self.toggle_source_button.setObjectName("toggleSourceAction")
        self.toggle_source_button.clicked.connect(self._toggle_source)
        self.remove_source_button = QPushButton("Remove Watch")
        self.remove_source_button.setObjectName("removeWatchAction")
        self.remove_source_button.clicked.connect(self._remove_source)

        source_actions = QGridLayout()
        source_actions.addWidget(self.select_button, 0, 0)
        source_actions.addWidget(self.edit_source_button, 0, 1)
        source_actions.addWidget(self.test_source_button, 0, 2)
        source_actions.addWidget(self.toggle_source_button, 1, 0)
        source_actions.addWidget(self.remove_source_button, 1, 1)
        source_actions.setColumnStretch(2, 1)

        self.folder_label = QLabel("No watched source selected")
        self.folder_label.setObjectName("folderPath")
        self.folder_label.setWordWrap(True)
        self.folder_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.preview_note = QLabel(
            "Preview analyses the selected source without changing the "
            "Library. The table lists changes and issues; unchanged books "
            "remain in the summary. Apply rechecks every candidate, then "
            "creates a safety backup and updates the catalogue. Ebook files "
            "are never changed."
        )
        self.preview_note.setWordWrap(True)

        self.scan_button = QPushButton("Preview Scan")
        self.scan_button.setObjectName("previewScanAction")
        self.scan_button.setEnabled(False)
        self.scan_button.clicked.connect(self._start_scan)
        self.scan_all_button = QPushButton("Preview All Watched Folders")
        self.scan_all_button.setObjectName("previewAllSourcesAction")
        self.scan_all_button.clicked.connect(self._start_all_scans)

        self.cancel_button = QPushButton("Cancel Scan")
        self.cancel_button.setObjectName("cancelScanAction")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_scan)

        self.discard_button = QPushButton("Discard Preview")
        self.discard_button.setObjectName("discardPreviewAction")
        self.discard_button.setEnabled(False)
        self.discard_button.clicked.connect(self._discard_preview)

        self.apply_button = QPushButton("Apply Preview")
        self.apply_button.setObjectName("applyPreviewAction")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_preview)

        source_scan_actions = QGridLayout()
        source_scan_actions.addWidget(self.scan_button, 0, 0)
        source_scan_actions.addWidget(self.scan_all_button, 0, 1)
        source_scan_actions.addWidget(self.cancel_button, 0, 2)
        source_scan_actions.setColumnStretch(3, 1)

        preview_actions = QGridLayout()
        preview_actions.addWidget(self.discard_button, 0, 0)
        preview_actions.addWidget(self.apply_button, 0, 1)
        preview_actions.setColumnStretch(2, 1)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("scanSummary")
        self.status_label.setWordWrap(True)

        self.current_file_label = QLabel("Current file: —")
        self.current_file_label.setWordWrap(True)
        self.current_file_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")

        self.statistics_label = QLabel(
            "Processed: 0 | Total: 0 | Elapsed: 00:00:00"
        )

        self.results_table = QTableWidget(0, 5)
        self.results_table.setHorizontalHeaderLabels(
            ["Status", "Book", "Format", "Size", "Location"]
        )
        configure_table(self.results_table, row_height=28)

        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        history_heading = QLabel("Recent Scan History")
        history_heading.setObjectName("sectionTitle")

        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(
            [
                "Finished",
                "Status",
                "New",
                "Changed",
                "Missing",
                "Skipped",
            ]
        )
        configure_table(self.history_table, row_height=28)
        self.history_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.history_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.history_table.setMinimumHeight(120)
        history_header = self.history_table.horizontalHeader()
        history_header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        for column in range(1, 6):
            history_header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )

        self.sources_tab = QWidget()
        sources_layout = QVBoxLayout(self.sources_tab)
        sources_layout.setContentsMargins(14, 14, 14, 14)
        sources_layout.setSpacing(9)
        sources_layout.addWidget(source_heading)
        sources_layout.addWidget(source_help)
        sources_layout.addWidget(self.source_table, 1)
        sources_layout.addLayout(source_actions)
        sources_layout.addWidget(self.folder_label)
        sources_layout.addLayout(source_scan_actions)

        self.preview_tab = QWidget()
        preview_layout = QVBoxLayout(self.preview_tab)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_layout.setSpacing(8)
        preview_layout.addWidget(self.preview_note)
        preview_layout.addLayout(preview_actions)
        preview_layout.addWidget(self.status_label)
        preview_layout.addWidget(self.current_file_label)
        preview_layout.addWidget(self.progress_bar)
        preview_layout.addWidget(self.statistics_label)
        preview_layout.addWidget(self.results_table, 1)

        self.history_tab = QWidget()
        history_layout = QVBoxLayout(self.history_tab)
        history_layout.setContentsMargins(14, 14, 14, 14)
        history_layout.setSpacing(8)
        history_layout.addWidget(history_heading)
        history_layout.addWidget(self.history_table, 1)

        self.scan_tabs = QTabWidget()
        self.scan_tabs.setObjectName("scanTaskTabs")
        self.scan_tabs.addTab(self.sources_tab, "Sources")
        self.scan_tabs.addTab(self.preview_tab, "Preview && Apply")
        self.scan_tabs.addTab(self.history_tab, "History")
        self.scan_tabs.setCurrentWidget(self.sources_tab)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(28, 22, 28, 24)
        root_layout.setSpacing(8)
        root_layout.addWidget(heading)
        root_layout.addWidget(description)
        root_layout.addWidget(self.scan_tabs, 1)
        self.refresh_sources()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < 850
        self.source_table.setColumnHidden(4, compact)
        self.source_table.setColumnHidden(5, compact)
        header = self.source_table.horizontalHeader()
        if compact:
            for column in range(4):
                header.setSectionResizeMode(
                    column,
                    QHeaderView.ResizeMode.Stretch,
                )
        else:
            for column in range(6):
                header.setSectionResizeMode(
                    column,
                    QHeaderView.ResizeMode.Stretch,
                )

    def refresh_sources(self, selected_source_id: int | None = None) -> None:
        """Reload detached source settings and preserve table selection."""
        preserve_id = (
            selected_source_id
            if selected_source_id is not None
            else self.selected_source_id
        )
        self.sources = self.source_service.get_sources()
        self.source_table.blockSignals(True)
        self.source_table.setRowCount(0)
        selected_row = -1
        for row, source in enumerate(self.sources):
            self.source_table.insertRow(row)
            rules = self._rules_summary(source)
            values = (
                source.display_name,
                source.folder_path,
                self._connection_label(source.connection_status),
                "Enabled" if source.enabled else "Disabled",
                rules,
                source.last_scanned_at or "Never",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 0:
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        source.source_id,
                    )
                self.source_table.setItem(row, column, item)
            if source.source_id == preserve_id:
                selected_row = row
        self.source_table.blockSignals(False)

        if selected_row < 0 and self.sources:
            selected_row = 0
        if selected_row >= 0:
            self.source_table.selectRow(selected_row)
            self.source_table.setCurrentCell(selected_row, 0)
            self._source_selection_changed(selected_row, 0, -1, -1)
        else:
            self.selected_source_id = None
            self.selected_folder = None
            self.folder_label.setText("No watched source selected")
            self.history_table.setRowCount(0)
            self._refresh_source_actions()

    def _source_selection_changed(
        self,
        current_row: int,
        _current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        source = (
            self.sources[current_row]
            if 0 <= current_row < len(self.sources)
            else None
        )
        self.selected_source_id = source.source_id if source else None
        self.selected_folder = (
            Path(source.folder_path) if source else None
        )
        self.folder_label.setText(
            f"Selected source: {source.folder_path}"
            if source
            else "No watched source selected"
        )
        self._refresh_history()
        self._refresh_source_actions()

    def _selected_source(self) -> LibrarySource | None:
        for source in self.sources:
            if source.source_id == self.selected_source_id:
                return source
        return None

    def _refresh_history(self) -> None:
        """Show recent approved Apply outcomes for the selected source."""
        self.history_table.setRowCount(0)
        source = self._selected_source()
        if source is None:
            return
        try:
            entries = self.source_service.get_scan_history(
                source.source_id,
                limit=10,
            )
        except (ValueError, RuntimeError):
            return
        for row, entry in enumerate(entries):
            self.history_table.insertRow(row)
            values = (
                entry.finished_at.replace("T", " ")[:19],
                entry.status.title(),
                f"{entry.new_count:,}",
                f"{entry.changed_count:,}",
                f"{entry.missing_count:,}",
                f"{entry.safely_skipped_count:,}",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    entry.error_summary
                    or (
                        "Recorded in Activity & Undo."
                        if entry.protection_operation_id is not None
                        else value
                    )
                )
                if column > 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )
                self.history_table.setItem(row, column, item)

    def _select_folder(self) -> None:
        """Add several watched folders without importing any books."""
        dialog = MultipleLibrarySourcesDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        added: list[LibrarySource] = []
        failures: list[str] = []
        for folder_path in dialog.folder_paths:
            try:
                folder = Path(folder_path)
                added.append(
                    self.source_service.add_source(
                        folder_path,
                        display_name=folder.name or str(folder),
                        include_subfolders=dialog.include_subfolders,
                        include_patterns=dialog.include_patterns,
                        exclude_patterns=dialog.exclude_patterns,
                    )
                )
            except (ValueError, RuntimeError) as error:
                failures.append(f"{folder_path}: {error}")
        if not added:
            QMessageBox.warning(
                self,
                "Folders not added",
                "\n\n".join(failures) or "No folders were added.",
            )
            return
        self.refresh_sources(added[-1].source_id)
        noun = "folder" if len(added) == 1 else "folders"
        message = (
            f"{len(added)} watched {noun} added. You can preview all enabled "
            "folders together."
        )
        if failures:
            message += " Some folders were not added: " + "; ".join(failures)
        self.status_label.setText(message)

    def add_source_path(self, folder_path: str) -> None:
        """Add a routed Calibre or network folder, then show Sources."""
        cleaned = str(folder_path).strip()
        if not cleaned:
            self.status_label.setText(
                "Choose a Calibre or network library folder first."
            )
            return
        try:
            source = self.source_service.add_source(cleaned)
        except (ValueError, RuntimeError) as error:
            self.status_label.setText(str(error))
            return
        self.refresh_sources(source.source_id)
        self.scan_tabs.setCurrentWidget(self.sources_tab)
        self.status_label.setText(
            "Source added. Test its connection before scanning."
        )

    def _edit_source(self) -> None:
        source = self._selected_source()
        if source is None:
            return
        dialog = LibrarySourceDialog(source, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            updated = self.source_service.update_source(
                source.source_id,
                display_name=dialog.display_name,
                include_subfolders=dialog.include_subfolders,
                include_patterns=dialog.include_patterns,
                exclude_patterns=dialog.exclude_patterns,
            )
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Source not updated", str(error))
            return
        self.refresh_sources(updated.source_id)
        self.status_label.setText("Source settings updated.")

    def _toggle_source(self) -> None:
        source = self._selected_source()
        if source is None:
            return
        try:
            updated = self.source_service.set_source_enabled(
                source.source_id,
                not source.enabled,
            )
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Source not updated", str(error))
            return
        self.refresh_sources(updated.source_id)
        self.status_label.setText(
            "Source enabled. Test its connection before scanning."
            if updated.enabled
            else "Source disabled. Existing catalogue books were kept."
        )

    def _remove_source(self) -> None:
        source = self._selected_source()
        if source is None or self.removal_thread is not None:
            return
        try:
            book_count = self.source_service.count_source_books(
                source.source_id
            )
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Folder not removed", str(error))
            return
        noun = "book" if book_count == 1 else "books"
        answer = QMessageBox.question(
            self,
            "Remove Watched Folder",
            f"Remove this watched folder from Twano?\n\n"
            f"This will remove {book_count:,} {noun} associated with this "
            "folder from the Twano Library.\n\n"
            "The folder and ebook files will not be deleted, moved, renamed, "
            "or modified. No other library sources will be affected.\n\n"
            "You can add and scan this folder again later.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start_source_removal(source)

    def _start_source_removal(self, source: LibrarySource) -> None:
        if self.removal_thread is not None:
            return
        self.source_table.setEnabled(False)
        self._refresh_source_actions()
        self.status_label.setText(
            "Removing the watched folder and its books from the Twano "
            "Library. Ebook files are unchanged."
        )
        self.removal_thread = QThread(self)
        self.removal_worker = SourceRemovalWorker(
            source.source_id,
            self.scan_service_factory,
        )
        self.removal_worker.moveToThread(self.removal_thread)
        self.removal_thread.started.connect(self.removal_worker.run)
        self.removal_worker.completed.connect(
            self._on_source_removal_completed
        )
        self.removal_worker.failed.connect(self._on_source_removal_failed)
        self.removal_worker.finished.connect(
            self.removal_worker.deleteLater
        )
        self.removal_worker.finished.connect(self.removal_thread.quit)
        self.removal_thread.finished.connect(
            self._on_source_removal_thread_finished
        )
        self.removal_thread.start()

    def _on_source_removal_completed(
        self,
        result: SourceRemovalResult,
    ) -> None:
        if (
            self.current_analysis is not None
            and self.current_analysis.source.source_id == result.source_id
        ):
            self.current_analysis = None
            self.results_table.setRowCount(0)
        if any(
            analysis.source.source_id == result.source_id
            for analysis in self.current_analyses
        ):
            self.current_analyses = ()
            self.current_analysis = None
            self.results_table.setRowCount(0)
        self.refresh_sources()
        noun = "book" if result.removed_book_count == 1 else "books"
        self.status_label.setText(
            f"Watched folder removed. {result.removed_book_count:,} {noun} "
            "were removed from the Twano Library. The folder and ebook "
            "files were unchanged."
        )
        self.catalogue_changed.emit()

    def _on_source_removal_failed(self, message: str) -> None:
        self.status_label.setText(
            "The watched folder was not removed. No catalogue or ebook "
            "files were changed."
        )
        QMessageBox.warning(self, "Folder not removed", message)

    def _on_source_removal_thread_finished(self) -> None:
        thread = self.removal_thread
        self.removal_thread = None
        self.removal_worker = None
        if thread is not None:
            thread.deleteLater()
        self.source_table.setEnabled(True)
        self._refresh_source_actions()
        if not self.is_scanning():
            self.scan_stopped.emit()

    def _test_source_connection(self) -> None:
        source = self._selected_source()
        if source is None or self.connection_thread is not None:
            return
        if not source.enabled:
            QMessageBox.information(
                self,
                "Source Disabled",
                "Enable this source before testing its connection.",
            )
            return

        self.connection_thread = QThread(self)
        self.connection_worker = SourceConnectionWorker(
            source.source_id,
            self.scan_service_factory,
        )
        self.connection_worker.moveToThread(self.connection_thread)
        self.connection_thread.started.connect(
            self.connection_worker.run
        )
        self.connection_worker.completed.connect(
            self._on_connection_completed
        )
        self.connection_worker.failed.connect(
            self._on_connection_failed
        )
        self.connection_worker.finished.connect(
            self.connection_worker.deleteLater
        )
        self.connection_worker.finished.connect(
            self.connection_thread.quit
        )
        self.connection_thread.finished.connect(
            self._on_connection_thread_finished
        )

        self.status_label.setText(
            f"Testing connection to {source.display_name}…"
        )
        self.source_table.setEnabled(False)
        self._refresh_source_actions()
        self.connection_thread.start()

    def _on_connection_completed(
        self,
        result: SourceConnectionResult,
    ) -> None:
        self.status_label.setText(result.message)
        self.refresh_sources(result.source_id)

    def _on_connection_failed(self, message: str) -> None:
        self.status_label.setText("Connection test failed.")
        QMessageBox.warning(self, "Connection Test Failed", message)

    def _on_connection_thread_finished(self) -> None:
        thread = self.connection_thread
        self.connection_thread = None
        self.connection_worker = None
        if thread is not None:
            thread.deleteLater()
        self.source_table.setEnabled(True)
        self._refresh_source_actions()
        if (
            self.scan_thread is None
            and self.analysis_thread is None
            and self.apply_thread is None
        ):
            self.scan_stopped.emit()

    def _refresh_source_actions(self) -> None:
        source = self._selected_source()
        busy = (
            self.scan_thread is not None
            or self.analysis_thread is not None
            or self.apply_thread is not None
            or self.connection_thread is not None
            or self.removal_thread is not None
            or self._batch_analysis_active
            or self._batch_apply_active
        )
        self.select_button.setEnabled(not busy)
        self.edit_source_button.setEnabled(source is not None and not busy)
        self.test_source_button.setEnabled(
            bool(source and source.enabled and not busy)
        )
        self.toggle_source_button.setEnabled(
            source is not None and not busy
        )
        self.remove_source_button.setEnabled(
            source is not None and not busy
        )
        self.toggle_source_button.setText(
            "Disable Source"
            if source is None or source.enabled
            else "Enable Source"
        )
        legacy_scan_ready = (
            source is None and self.selected_folder is not None
        )
        self.scan_button.setText(
            "Preview Scan"
            if source is not None
            else "Scan Selected Source"
        )
        self.scan_button.setEnabled(
            not busy
            and (
                legacy_scan_ready
                or bool(source and source.enabled)
            )
        )
        enabled_sources = tuple(item for item in self.sources if item.enabled)
        self.scan_all_button.setEnabled(
            not busy and bool(enabled_sources)
        )
        self.scan_all_button.setText(
            "Preview All Watched Folders"
            if len(enabled_sources) != 1
            else "Preview Watched Folder"
        )
        self.discard_button.setEnabled(
            not busy
            and bool(self.current_analyses or self.current_analysis is not None)
        )
        analyses = self._reviewed_analyses()
        batch_ready = bool(
            analyses
            and all(
                analysis.completed
                and analysis.connected
                and not analysis.cancelled
                for analysis in analyses
            )
            and any(analysis.applicable_count > 0 for analysis in analyses)
        )
        analysis = self.current_analysis
        self.apply_button.setEnabled(
            not busy
            and self._protection_mode == ProtectionMode.STANDARD
            and batch_ready
            and (
                len(analyses) > 1
                or (
                    analysis is not None
                    and source is not None
                    and source.source_id == analysis.source.source_id
                )
            )
        )
        self.apply_button.setText(
            "Apply All Previews" if len(analyses) > 1 else "Apply Preview"
        )
        self.apply_button.setToolTip(
            (
                "Apply the preview after Twano creates a safety backup."
                if self._protection_mode == ProtectionMode.STANDARD
                else (
                    "Change Protection Mode to Standard in Settings before "
                    "applying catalogue changes."
                )
            )
        )

    def _reviewed_analyses(self) -> tuple[ScanAnalysisResult, ...]:
        if self.current_analyses:
            return self.current_analyses
        return (
            (self.current_analysis,)
            if self.current_analysis is not None
            else ()
        )

    def set_protection_mode(
        self,
        mode: ProtectionMode | str,
    ) -> None:
        """Refresh the simple Apply availability when Settings changes."""
        self._protection_mode = ProtectionMode(mode)
        self._refresh_source_actions()

    @staticmethod
    def _connection_label(status: SourceConnectionStatus) -> str:
        return {
            SourceConnectionStatus.NOT_TESTED: "Not tested",
            SourceConnectionStatus.AVAILABLE: "Available",
            SourceConnectionStatus.UNAVAILABLE: "Unavailable",
            SourceConnectionStatus.NOT_FOLDER: "Not a folder",
            SourceConnectionStatus.PERMISSION_DENIED: "Permission denied",
            SourceConnectionStatus.DISABLED: "Disabled",
        }[status]

    @staticmethod
    def _rules_summary(source: LibrarySource) -> str:
        parts = [
            "Subfolders" if source.include_subfolders else "Top folder only"
        ]
        if source.include_patterns:
            parts.append("Include: " + "; ".join(source.include_patterns))
        if source.exclude_patterns:
            parts.append("Exclude: " + "; ".join(source.exclude_patterns))
        return " | ".join(parts)

    def _start_scan(self) -> None:
        """Create and start the background scanning thread."""
        if self.selected_folder is None:
            return

        source = self._selected_source()
        if source is not None:
            self._start_analysis(source)
            return
        if self.scan_thread is not None:
            QMessageBox.information(
                self,
                "Scan Already Running",
                "A library scan is already running.",
            )
            return

        self._prepare_interface_for_scan()

        self.scan_thread = QThread(self)
        self.scan_worker = ScanWorker(
            self.selected_folder,
            self.scan_service_factory,
        )
        self.scan_worker.moveToThread(self.scan_thread)

        self.scan_thread.started.connect(self.scan_worker.run)

        self.scan_worker.discovery_started.connect(
            self._on_discovery_started
        )
        self.scan_worker.processing_started.connect(
            self._on_processing_started
        )
        self.scan_worker.progress_changed.connect(
            self._on_progress_changed
        )
        self.scan_worker.current_file_changed.connect(
            self._on_current_file_changed
        )
        self.scan_worker.book_processed.connect(
            self._add_book_to_table
        )
        self.scan_worker.status_changed.connect(
            self.status_label.setText
        )
        self.scan_worker.completed.connect(
            self._on_scan_completed
        )
        self.scan_worker.cancelled.connect(
            self._on_scan_cancelled
        )
        self.scan_worker.failed.connect(
            self._on_scan_failed
        )

        self.scan_worker.finished.connect(self.scan_worker.deleteLater)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_thread.finished.connect(self._on_thread_finished)

        self.scan_thread.start()

    def _start_all_scans(self) -> None:
        """Preview every enabled watched folder sequentially."""
        if self.is_scanning():
            return
        enabled_sources = [
            source for source in self.sources if source.enabled
        ]
        if not enabled_sources:
            QMessageBox.information(
                self,
                "No Enabled Watched Folders",
                "Add or enable at least one watched folder before scanning.",
            )
            return
        self.current_analysis = None
        self.current_analyses = ()
        self._batch_analysis_results = []
        self._batch_analysis_failures = []
        self._analysis_queue = list(enabled_sources)
        self._batch_analysis_total = len(enabled_sources)
        self._batch_analysis_active = True
        self._prepare_interface_for_scan()
        self.results_table.setRowCount(0)
        self._start_next_batch_analysis()

    def _start_next_batch_analysis(self) -> None:
        if not self._batch_analysis_active:
            return
        if not self._analysis_queue:
            self._finish_batch_analysis()
            return
        source = self._analysis_queue.pop(0)
        position = self._batch_analysis_total - len(self._analysis_queue)
        self.status_label.setText(
            f"Previewing watched folder {position} of "
            f"{self._batch_analysis_total}: {source.display_name}"
        )
        self.selected_source_id = source.source_id
        self.selected_folder = Path(source.folder_path)
        self._start_analysis(source, prepare_interface=False)

    def _finish_batch_analysis(self) -> None:
        self._batch_analysis_active = False
        self.current_analyses = tuple(self._batch_analysis_results)
        self.current_analysis = (
            self.current_analyses[0] if len(self.current_analyses) == 1 else None
        )
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("All watched folders previewed")
        source_count = self._batch_analysis_total
        successful_count = len(self.current_analyses)
        applicable = sum(
            analysis.applicable_count for analysis in self.current_analyses
        )
        self.status_label.setText(
            f"Combined preview ready — {source_count:,} watched folders "
            f"checked; {successful_count:,} ready; {applicable:,} catalogue "
            "changes require review. "
            "Nothing has been applied."
            + (
                " Problems: " + " ".join(self._batch_analysis_failures)
                if self._batch_analysis_failures
                else ""
            )
        )
        self.current_file_label.setText(
            "All enabled watched folders have been analysed."
        )
        self.source_table.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._refresh_source_actions()
        self.scan_stopped.emit()

    def _start_analysis(
        self,
        source: LibrarySource,
        *,
        prepare_interface: bool = True,
    ) -> None:
        """Start a non-mutating source analysis in a fresh worker thread."""
        if self.analysis_thread is not None:
            QMessageBox.information(
                self,
                "Preview Already Running",
                "A source preview is already running.",
            )
            return

        if prepare_interface:
            self.current_analysis = None
            self.current_analyses = ()
            self._prepare_interface_for_scan()
        self.status_label.setText(
            "Starting safe source analysis…"
        )
        self.progress_bar.setFormat("Analysing without changes…")

        self.analysis_thread = QThread(self)
        self.analysis_worker = ScanAnalysisWorker(
            source.source_id,
            self.scan_service_factory,
        )
        self.analysis_worker.moveToThread(self.analysis_thread)
        self.analysis_thread.started.connect(self.analysis_worker.run)
        self.analysis_worker.status_changed.connect(
            self.status_label.setText
        )
        self.analysis_worker.current_location_changed.connect(
            self._on_analysis_location
        )
        self.analysis_worker.discovery_count_changed.connect(
            self._on_analysis_count
        )
        self.analysis_worker.completed.connect(
            self._on_analysis_completed
        )
        self.analysis_worker.cancelled.connect(
            self._on_analysis_cancelled
        )
        self.analysis_worker.failed.connect(
            self._on_analysis_failed
        )
        self.analysis_worker.finished.connect(
            self.analysis_worker.deleteLater
        )
        self.analysis_worker.finished.connect(
            self.analysis_thread.quit
        )
        self.analysis_thread.finished.connect(
            self._on_analysis_thread_finished
        )
        self.analysis_thread.start()

    def _on_analysis_location(self, location: str) -> None:
        self.current_file_label.setText(
            f"Current location: {location}"
        )

    def _on_analysis_count(self, count: int) -> None:
        self.processed_count = count
        self.statistics_label.setText(
            f"Analysed: {count:,} | "
            f"Elapsed: {format_elapsed_time(self._elapsed_seconds())}"
        )

    def _on_analysis_completed(
        self,
        result: ScanAnalysisResult,
    ) -> None:
        if self._batch_analysis_active:
            if result.completed and result.connected and not result.cancelled:
                self._batch_analysis_results.append(result)
                self.current_analyses = tuple(self._batch_analysis_results)
                self._append_analysis(result, show_source=True)
            else:
                issue = (
                    result.issues[0].message
                    if result.issues
                    else f"{result.source.display_name} could not be previewed."
                )
                self._batch_analysis_failures.append(
                    f"{result.source.display_name}: {issue}"
                )
            completed = self._batch_analysis_total - len(self._analysis_queue)
            self.progress_bar.setRange(0, self._batch_analysis_total)
            self.progress_bar.setValue(completed)
            self.progress_bar.setFormat(
                "Previewed %v of %m watched folders"
            )
            return
        self.current_analysis = result
        self.current_analyses = (result,)
        self._show_analysis(result)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if result.completed else 0)
        if result.completed:
            self.progress_bar.setFormat("Preview ready — no changes applied")
            self.status_label.setText(self._analysis_summary(result))
            self.current_file_label.setText(
                "Analysis complete. The Library is unchanged."
            )
        else:
            self.progress_bar.setFormat("Preview incomplete")
            issue = (
                result.issues[0].message
                if result.issues
                else "The source analysis did not complete."
            )
            self.status_label.setText(
                f"Preview unavailable — {issue}"
            )
            self.current_file_label.setText(
                "No missing books were inferred."
            )

    def _on_analysis_cancelled(
        self,
        result: ScanAnalysisResult,
    ) -> None:
        if self._batch_analysis_active:
            self._analysis_queue.clear()
            self._batch_analysis_active = False
            self._batch_analysis_results = []
            self.current_analyses = ()
            self.current_analysis = None
        else:
            self.current_analysis = result
            self.current_analyses = (result,)
        self._show_analysis(result)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Preview cancelled")
        self.status_label.setText(
            "Preview cancelled. The Library was not changed and no missing "
            "books were inferred."
        )
        self.current_file_label.setText("Analysis cancelled")

    def _on_analysis_failed(self, message: str) -> None:
        if self._batch_analysis_active:
            self._batch_analysis_failures.append(message)
            self.status_label.setText(
                "One watched folder could not be previewed. Continuing with "
                "the remaining enabled folders."
            )
            return
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Preview failed")
        self.status_label.setText(
            "Preview failed. The Library was not changed."
        )
        QMessageBox.warning(self, "Preview Failed", message)

    def _on_analysis_thread_finished(self) -> None:
        thread = self.analysis_thread
        self.analysis_thread = None
        self.analysis_worker = None
        if thread is not None:
            thread.deleteLater()
        if self._batch_analysis_active:
            QTimer.singleShot(0, self._start_next_batch_analysis)
            return
        self.source_table.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._refresh_source_actions()
        if (
            self.scan_thread is None
            and self.connection_thread is None
            and self.apply_thread is None
        ):
            self.scan_stopped.emit()

    def _show_analysis(self, result: ScanAnalysisResult) -> None:
        self.results_table.setRowCount(0)
        self._append_analysis(result, show_source=False)

    def _append_analysis(
        self,
        result: ScanAnalysisResult,
        *,
        show_source: bool,
    ) -> None:
        for item in result.items:
            if item.status == ScanItemStatus.UNCHANGED:
                continue
            self._add_analysis_item(
                item,
                source_name=result.source.display_name if show_source else "",
            )

    def _add_analysis_item(
        self,
        item: ScanAnalysisItem,
        *,
        source_name: str = "",
    ) -> None:
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        values = (
            self._analysis_status_label(item.status),
            item.name,
            item.file_format,
            format_file_size(item.size_bytes),
            (
                f"{source_name} — {item.relative_path}"
                if source_name
                else item.relative_path
            ),
        )
        for column, value in enumerate(values):
            table_item = QTableWidgetItem(str(value))
            table_item.setToolTip(item.message or item.file_path)
            if column == 0:
                table_item.setData(
                    Qt.ItemDataRole.UserRole,
                    item.file_path,
                )
            if column in (0, 2, 3):
                table_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )
            self.results_table.setItem(row, column, table_item)

    @staticmethod
    def _analysis_status_label(status: ScanItemStatus) -> str:
        return {
            ScanItemStatus.NEW: "New",
            ScanItemStatus.CHANGED: "Changed",
            ScanItemStatus.UNCHANGED: "Unchanged",
            ScanItemStatus.MISSING: "Missing",
            ScanItemStatus.UNREADABLE: "Unreadable",
        }[status]

    @staticmethod
    def _analysis_summary(result: ScanAnalysisResult) -> str:
        return (
            "Preview ready — "
            f"New: {result.count(ScanItemStatus.NEW):,} | "
            f"Changed: {result.count(ScanItemStatus.CHANGED):,} | "
            f"Missing: {result.count(ScanItemStatus.MISSING):,} | "
            f"Unreadable: {result.count(ScanItemStatus.UNREADABLE):,} | "
            f"Unchanged: {result.count(ScanItemStatus.UNCHANGED):,} | "
            f"Skipped: {result.skipped_count:,}. "
            "Nothing has been applied."
        )

    def _discard_preview(self) -> None:
        self.current_analysis = None
        self.current_analyses = ()
        self._analysis_queue.clear()
        self._batch_analysis_results = []
        self._batch_analysis_failures = []
        self._batch_analysis_active = False
        self._batch_apply_queue.clear()
        self._batch_apply_results = []
        self._batch_apply_active = False
        self.results_table.setRowCount(0)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.status_label.setText(
            "Preview discarded. The Library was not changed."
        )
        self.current_file_label.setText("Current location: —")
        self.processed_count = 0
        self.total_count = 0
        self._update_statistics()
        self._refresh_source_actions()

    def _apply_preview(self) -> None:
        """Confirm and start applying the current immutable preview."""
        if self._protection_mode != ProtectionMode.STANDARD:
            QMessageBox.information(
                self,
                "Read-Only Mode",
                "Apply Preview is unavailable in Read-Only mode.\n\n"
                "Change Protection Mode to Standard in Settings when you "
                "are ready to update the catalogue.",
            )
            return
        analyses = tuple(
            analysis
            for analysis in self._reviewed_analyses()
            if analysis.completed
            and analysis.connected
            and not analysis.cancelled
            and analysis.applicable_count > 0
        )
        if not analyses:
            return
        total_changes = sum(
            analysis.applicable_count for analysis in analyses
        )
        folder_count = len(analyses)
        confirmation = (
            f"Apply {total_changes:,} previewed catalogue changes from "
            f"{folder_count:,} watched folders?\n\n"
            "Twano will process each folder safely in sequence. Every folder "
            "is rechecked and receives its own verified backup and Undo "
            "history entry. Ebook files will not be changed."
            if folder_count > 1
            else (
                "Apply the previewed catalogue changes?\n\n"
                "Twano will recheck every candidate and create a safety backup "
                "automatically before updating the catalogue. Ebook files "
                "will not be changed."
            )
        )
        answer = QMessageBox.question(
            self,
            "Apply All Previews" if folder_count > 1 else "Apply Preview",
            confirmation,
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._batch_apply_results = []
        self._batch_apply_total = folder_count
        self._batch_apply_queue = list(analyses[1:])
        self._batch_apply_active = folder_count > 1
        self.current_analysis = analyses[0]
        self._start_apply(analyses[0])

    def _start_apply(self, analysis: ScanAnalysisResult) -> None:
        """Run rechecks, metadata refresh, and transactional Apply."""
        if self.apply_thread is not None:
            return
        self.scan_started_at = monotonic()
        self.source_table.setEnabled(False)
        self.select_button.setEnabled(False)
        self.edit_source_button.setEnabled(False)
        self.test_source_button.setEnabled(False)
        self.toggle_source_button.setEnabled(False)
        self.remove_source_button.setEnabled(False)
        self.scan_button.setEnabled(False)
        self.scan_all_button.setEnabled(False)
        self.discard_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setRange(0, max(1, len(analysis.items)))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Rechecking %v of %m — %p%")
        self.status_label.setText(
            "Preparing the approved preview. No catalogue changes have "
            "been made yet."
        )

        self.apply_thread = QThread(self)
        backup_folder: str | Path | None = None
        retention_days = 0
        if self.preferences is not None:
            stored = self.preferences.load_protection_preferences()
            backup_folder = stored.backup_folder or None
            retention_days = stored.retention_days
        self.apply_worker = ScanApplyWorker(
            analysis,
            self.scan_service_factory,
            backup_folder=backup_folder,
            retention_days=retention_days,
            protection_mode=self._protection_mode,
        )
        self.apply_worker.moveToThread(self.apply_thread)
        self.apply_thread.started.connect(self.apply_worker.run)
        self.apply_worker.status_changed.connect(
            self.status_label.setText
        )
        self.apply_worker.current_item_changed.connect(
            self._on_apply_item
        )
        self.apply_worker.progress_changed.connect(
            self._on_apply_progress
        )
        self.apply_worker.backup_progress_changed.connect(
            self._on_backup_progress
        )
        self.apply_worker.completed.connect(
            self._on_apply_completed
        )
        self.apply_worker.cancelled.connect(
            self._on_apply_cancelled
        )
        self.apply_worker.failed.connect(self._on_apply_failed)
        self.apply_worker.finished.connect(
            self.apply_worker.deleteLater
        )
        self.apply_worker.finished.connect(self.apply_thread.quit)
        self.apply_thread.finished.connect(
            self._on_apply_thread_finished
        )
        self.apply_thread.start()

    def _on_apply_item(self, file_path: str) -> None:
        self.current_file_label.setText(
            f"Safety check: {file_path}"
        )

    def _on_apply_progress(self, processed: int, total: int) -> None:
        self.processed_count = processed
        self.total_count = total
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(processed)
        self._update_statistics()

    def _on_backup_progress(self, percent: int, message: str) -> None:
        """Show that backup verification is progressing after file rechecks."""
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(max(0, min(100, int(percent))))
        self.progress_bar.setFormat("Creating verified backup — %p%")
        self.current_file_label.setText(message)

    def _on_apply_completed(self, result: ScanApplyResult) -> None:
        self._mark_apply_results(result, self.current_analysis)
        if self._batch_apply_active:
            self._batch_apply_results.append(result)
            completed = len(self._batch_apply_results)
            self.status_label.setText(
                f"Applied watched folder {completed:,} of "
                f"{self._batch_apply_total:,}. Preparing the next folder."
            )
            self.current_file_label.setText(
                "Safety backup and catalogue history recorded for this "
                "folder. Ebook files were unchanged."
            )
            self.refresh_sources(result.source_id)
            self.catalogue_changed.emit()
            return
        self.current_analysis = None
        self.current_analyses = ()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Applied atomically")
        self.status_label.setText(
            "Apply complete — "
            f"New: {result.applied_new_count:,} | "
            f"Changed: {result.applied_changed_count:,} | "
            f"Missing: {result.applied_missing_count:,} | "
            f"Safely skipped: {len(result.safely_skipped):,}."
        )
        self.current_file_label.setText(
            "Safety backup and catalogue history recorded. Ebook files "
            "were unchanged."
        )
        self.refresh_sources(result.source_id)
        self.catalogue_changed.emit()

    def _on_apply_cancelled(self, result: ScanApplyResult) -> None:
        self.current_analysis = None
        self.current_analyses = ()
        self._batch_apply_queue.clear()
        previously_applied = len(self._batch_apply_results)
        self._batch_apply_active = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Apply cancelled")
        self.status_label.setText(
            (
                f"Apply All cancelled. {previously_applied:,} earlier watched "
                "folders remain applied and are available in Activity & Undo."
                if previously_applied
                else (
                    "Apply cancelled before the transaction. The catalogue "
                    "was not changed."
                )
            )
        )
        self.current_file_label.setText("Apply cancelled safely.")
        self.refresh_sources(result.source_id)

    def _on_apply_failed(self, message: str) -> None:
        source_id = (
            self.current_analysis.source.source_id
            if self.current_analysis is not None
            else self.selected_source_id
        )
        self.current_analysis = None
        self.current_analyses = ()
        self._batch_apply_queue.clear()
        previously_applied = len(self._batch_apply_results)
        was_batch = self._batch_apply_active
        self._batch_apply_active = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Apply rolled back")
        self.status_label.setText(
            (
                f"Apply All stopped. This folder was rolled back; "
                f"{previously_applied:,} earlier watched folders remain "
                "applied and can be reversed in Activity & Undo."
                if was_batch and previously_applied
                else "Apply failed. Catalogue changes were rolled back."
            )
        )
        self.current_file_label.setText(
            (
                "No partial update remains for the folder that failed."
                if was_batch
                else "No partial catalogue update remains."
            )
        )
        if source_id is not None:
            self.refresh_sources(source_id)
        QMessageBox.critical(self, "Apply Failed", message)

    def _mark_apply_results(
        self,
        result: ScanApplyResult,
        analysis: ScanAnalysisResult | None = None,
    ) -> None:
        skipped = {
            skip.file_path: skip.reason
            for skip in result.safely_skipped
        }
        allowed_paths = (
            {item.file_path for item in analysis.items}
            if analysis is not None
            else None
        )
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item is None:
                continue
            file_path = str(
                item.data(Qt.ItemDataRole.UserRole) or ""
            )
            if allowed_paths is not None and file_path not in allowed_paths:
                continue
            if file_path in skipped:
                item.setText("Safely skipped")
                item.setToolTip(skipped[file_path])
            elif item.text() in {"New", "Changed", "Missing"}:
                item.setText(f"Applied — {item.text()}")

    def _on_apply_thread_finished(self) -> None:
        thread = self.apply_thread
        self.apply_thread = None
        self.apply_worker = None
        if thread is not None:
            thread.deleteLater()
        if self._batch_apply_active and self._batch_apply_queue:
            next_analysis = self._batch_apply_queue.pop(0)
            self.current_analysis = next_analysis
            QTimer.singleShot(
                0,
                lambda analysis=next_analysis: self._start_apply(analysis),
            )
            return
        if self._batch_apply_active:
            results = tuple(self._batch_apply_results)
            self._batch_apply_active = False
            self.current_analysis = None
            self.current_analyses = ()
            self._batch_apply_queue.clear()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("All watched folders applied")
            self.status_label.setText(
                f"Apply All complete - {len(results):,} watched folders | "
                f"New: {sum(item.applied_new_count for item in results):,} | "
                f"Changed: "
                f"{sum(item.applied_changed_count for item in results):,} | "
                f"Missing: "
                f"{sum(item.applied_missing_count for item in results):,} | "
                f"Safely skipped: "
                f"{sum(len(item.safely_skipped) for item in results):,}."
            )
            self.current_file_label.setText(
                "Each watched folder has its own verified backup and Undo "
                "history. Ebook files were unchanged."
            )
            self.refresh_sources()
        self.source_table.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._refresh_source_actions()
        if (
            self.scan_thread is None
            and self.analysis_thread is None
            and self.connection_thread is None
        ):
            self.scan_stopped.emit()

    def _prepare_interface_for_scan(self) -> None:
        """Reset controls and results before a new scan."""
        self.scan_tabs.setCurrentWidget(self.preview_tab)
        self.results_table.setRowCount(0)

        self.scan_started_at = monotonic()
        self.processed_count = 0
        self.total_count = 0

        self.select_button.setEnabled(False)
        self.source_table.setEnabled(False)
        self.edit_source_button.setEnabled(False)
        self.test_source_button.setEnabled(False)
        self.toggle_source_button.setEnabled(False)
        self.remove_source_button.setEnabled(False)
        self.scan_button.setEnabled(False)
        self.scan_all_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.discard_button.setEnabled(False)
        self.apply_button.setEnabled(False)

        self.status_label.setText("Starting scan…")
        self.current_file_label.setText("Current file: —")

        self.progress_bar.setRange(0, 0)
        self.statistics_label.setText(
            "Processed: 0 | Total: 0 | Elapsed: 00:00:00"
        )

    def _cancel_scan(self) -> None:
        """Ask the worker to stop safely."""
        if (
            self.scan_worker is None
            and self.analysis_worker is None
            and self.apply_worker is None
        ):
            return

        self.cancel_button.setEnabled(False)
        self.status_label.setText("Cancelling safely…")
        if self.scan_worker is not None:
            self.scan_worker.request_cancel()
        if self.analysis_worker is not None:
            self.analysis_worker.request_cancel()
        if self.apply_worker is not None:
            self.apply_worker.request_cancel()

    def _on_discovery_started(self) -> None:
        """Show an indeterminate progress bar during discovery."""
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFormat("Discovering files…")

    def _on_processing_started(self, total_books: int) -> None:
        """Configure progress once the number of books is known."""
        self.total_count = total_books
        self.progress_bar.setRange(0, max(1, total_books))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v of %m books — %p%")
        self._update_statistics()

    def _on_progress_changed(
        self,
        processed: int,
        total: int,
    ) -> None:
        """Update progress information from the worker."""
        self.processed_count = processed
        self.total_count = total
        self.progress_bar.setValue(processed)
        self._update_statistics()

    def _on_current_file_changed(self, filename: str) -> None:
        """Display the file currently being processed."""
        self.current_file_label.setText(
            f"Current file: {filename}"
        )

    def _add_book_to_table(self, book: BookFile) -> None:
        """Append a processed book to the results table."""
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)

        values = (
            "Processed",
            book.name,
            book.extension,
            book.size_display,
            str(book.path.parent),
        )

        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))

            if column in (0, 2, 3):
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )

            self.results_table.setItem(row, column, item)

        self.results_table.scrollToBottom()

    def _on_scan_completed(
        self,
        total_books: int,
        metadata_count: int,
    ) -> None:
        """Display a successful scan summary."""
        logger.info(
            "Scan completion received books=%s metadata=%s "
            "thread_running=%s",
            total_books,
            metadata_count,
            bool(self.scan_thread and self.scan_thread.isRunning()),
        )
        self.processed_count = total_books
        self.total_count = total_books

        if total_books == 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("No books found")
        else:
            self.progress_bar.setValue(total_books)

        self.status_label.setText(
            f"Scan complete — {total_books:,} books found; "
            f"embedded metadata extracted from "
            f"{metadata_count:,} books."
        )
        self.current_file_label.setText("Current file: Complete")
        self._update_statistics()

    def _on_scan_cancelled(
        self,
        processed: int,
        total: int,
    ) -> None:
        """Display the cancellation summary."""
        self.processed_count = processed
        self.total_count = total

        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(processed)
            self.progress_bar.setFormat(
                "%v of %m books — Cancelled"
            )
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Cancelled")

        self.status_label.setText(
            f"Scan cancelled after processing "
            f"{processed:,} of {total:,} books."
        )
        self.current_file_label.setText("Current file: Cancelled")
        self._update_statistics()

    def _on_scan_failed(self, message: str) -> None:
        """Show a scan error."""
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Scan failed")
        self.status_label.setText("Scan failed.")

        QMessageBox.critical(
            self,
            "Scan Failed",
            message,
        )

    def _on_thread_finished(self) -> None:
        """Release scan objects and restore controls after thread shutdown."""
        thread = self.scan_thread
        logger.info("Scan QThread finished")

        self.scan_thread = None
        self.scan_worker = None

        if thread is not None:
            thread.deleteLater()

        self.select_button.setEnabled(True)
        self.source_table.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._refresh_source_actions()
        if (
            self.connection_thread is None
            and self.analysis_thread is None
            and self.apply_thread is None
        ):
            self.scan_stopped.emit()

    def is_scanning(self) -> bool:
        """Return whether scan-page background work is still active."""
        return (
            self.scan_thread is not None
            or self.analysis_thread is not None
            or self.apply_thread is not None
            or self.connection_thread is not None
            or self.removal_thread is not None
            or self._batch_analysis_active
            or self._batch_apply_active
        )

    def cancel_active_scan(self) -> None:
        """Request cancellation without blocking the GUI thread."""
        if self.scan_worker is not None:
            self.scan_worker.request_cancel()
        if self.analysis_worker is not None:
            self.analysis_worker.request_cancel()
        if self.apply_worker is not None:
            self.apply_worker.request_cancel()

    def _update_statistics(self) -> None:
        """Refresh processed, total and elapsed information."""
        self.statistics_label.setText(
            f"Processed: {self.processed_count:,} | "
            f"Total: {self.total_count:,} | "
            f"Elapsed: {format_elapsed_time(self._elapsed_seconds())}"
        )

    def _elapsed_seconds(self) -> float:
        if self.scan_started_at is None:
            return 0.0
        return monotonic() - self.scan_started_at

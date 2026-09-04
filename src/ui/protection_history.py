"""Human-readable RC6.7 change-plan preview and audit history."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from services.protection_models import (
    ConfirmationRequirement,
    OperationRecord,
    OperationStatus,
    PlanConfirmation,
    Reversibility,
)
from preferences import PreferencesStore, ProtectionMode
from services.protection_service import ProtectionService
from ui.theme import configure_table
from workers.audit_export_worker import AuditExportWorker
from workers.protection_executor_worker import ProtectionExecutorWorker


STATUS_LABELS = {
    OperationStatus.PLANNED: "Planned",
    OperationStatus.APPROVED: "Approved",
    OperationStatus.CANCELLED: "Cancelled",
    OperationStatus.APPLYING: "Applying",
    OperationStatus.APPLIED: "Applied",
    OperationStatus.FAILED: "Failed",
    OperationStatus.ROLLED_BACK: "Rolled Back",
    OperationStatus.PARTIAL: "Partial",
    OperationStatus.UNDONE: "Undone",
}
STATUS_COLOURS = {
    OperationStatus.PLANNED: "#8fc7ef",
    OperationStatus.APPROVED: "#86d99a",
    OperationStatus.CANCELLED: "#b8c9d9",
    OperationStatus.APPLYING: "#efc270",
    OperationStatus.APPLIED: "#86d99a",
    OperationStatus.FAILED: "#f08a91",
    OperationStatus.ROLLED_BACK: "#efc270",
    OperationStatus.PARTIAL: "#efc270",
    OperationStatus.UNDONE: "#b69ce8",
}


class ProtectionHistoryPanel(QWidget):
    """Reusable plan preview and persistent audit presentation."""

    background_stopped = Signal()
    evidence_changed = Signal()
    catalogue_changed = Signal()
    catalogue_restored = Signal()
    database_replacement_active = Signal(bool)

    def __init__(
        self,
        service_factory: Callable[[], ProtectionService],
        presentation_service: ProtectionService,
        preferences: PreferencesStore,
        restore_idle_check: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__()
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Expanding,
        )
        self.service_factory = service_factory
        self.service = presentation_service
        self.preferences = preferences
        self.restore_idle_check = restore_idle_check or (lambda: True)
        self.current_record: OperationRecord | None = None
        self.export_thread: QThread | None = None
        self.export_worker: AuditExportWorker | None = None
        self.executor_thread: QThread | None = None
        self.executor_worker: ProtectionExecutorWorker | None = None
        self._executing_operation_id: int | None = None
        self._executing_operation_type = ""
        self._forced_compact: bool | None = None

        self.preview_button = QPushButton("Preview Safety Check")
        self.preview_button.setObjectName("previewPlanAction")
        self.preview_button.setToolTip(
            "Create a no-catalogue-change plan to exercise preview and "
            "history safely."
        )
        self.preview_button.clicked.connect(self._preview_safety_check)
        self.reversible_button = QPushButton("Preview Test Change")
        self.reversible_button.setObjectName("previewReversibleAction")
        self.reversible_button.setToolTip(
            "Preview creation of one empty test collection with a complete "
            "persistent Undo."
        )
        self.reversible_button.clicked.connect(
            self._preview_reversible_change
        )
        self.undo_button = QPushButton("Preview Undo")
        self.undo_button.setObjectName("previewUndoAction")
        self.undo_button.setToolTip(
            "Create a separate Undo plan for the selected applied operation."
        )
        self.undo_button.clicked.connect(self._preview_undo_current)
        self.approve_button = QPushButton("Approve Plan")
        self.approve_button.setObjectName("approvePlanAction")
        self.approve_button.setToolTip(
            "Record approval for this exact plan without applying it yet."
        )
        self.approve_button.clicked.connect(self._approve_current)
        self.apply_button = QPushButton("Apply Plan")
        self.apply_button.setObjectName("applyPlanAction")
        self.apply_button.setToolTip(
            "Create a verified backup, revalidate the plan, then run one "
            "atomic database transaction."
        )
        self.apply_button.clicked.connect(self._apply_current)
        self.cancel_plan_button = QPushButton("Cancel Plan")
        self.cancel_plan_button.setObjectName("cancelPlanAction")
        self.cancel_plan_button.clicked.connect(self._cancel_current)
        for button in (
            self.preview_button,
            self.reversible_button,
            self.undo_button,
            self.approve_button,
            self.apply_button,
            self.cancel_plan_button,
        ):
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )

        self.plan_actions = QGridLayout()
        self.plan_actions.setContentsMargins(0, 0, 0, 0)
        self.plan_actions.setSpacing(8)

        self.execution_progress = QProgressBar()
        self.execution_progress.setObjectName("protectedExecutionProgress")
        self.execution_progress.setRange(0, 100)
        self.execution_progress.setValue(0)
        self.execution_progress.setVisible(False)

        self.plan_panel = QFrame()
        self.plan_panel.setObjectName("changePlanPanel")
        plan_layout = QVBoxLayout(self.plan_panel)
        plan_layout.setContentsMargins(18, 16, 18, 16)
        plan_layout.setSpacing(8)
        self.plan_title = QLabel("No change plan selected")
        self.plan_title.setObjectName("changePlanTitle")
        self.plan_title.setWordWrap(True)
        self.plan_facts = QLabel(
            "Use Preview Safety Check or select a history row."
        )
        self.plan_facts.setObjectName("changePlanFacts")
        self.plan_facts.setWordWrap(True)
        self.plan_details = QTextBrowser()
        self.plan_details.setObjectName("changePlanDetails")
        self.plan_details.setOpenExternalLinks(False)
        self.plan_details.setMinimumHeight(80)
        self.plan_details.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Expanding,
        )
        plan_layout.addWidget(self.plan_title)
        plan_layout.addWidget(self.plan_facts)
        plan_layout.addWidget(self.plan_details, 1)

        self.history_heading = QLabel(
            "Select a row to inspect it in Plan Preview"
        )
        self.history_heading.setObjectName("fieldLabel")
        self.refresh_button = QPushButton("Refresh History")
        self.refresh_button.setObjectName("refreshHistoryAction")
        self.refresh_button.clicked.connect(self.refresh_history)
        self.export_button = QPushButton("Export Selected Report")
        self.export_button.setObjectName("exportReportAction")
        self.export_button.clicked.connect(self._export_selected)
        for button in (self.refresh_button, self.export_button):
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        self.history_actions = QGridLayout()
        self.history_actions.setContentsMargins(0, 0, 0, 0)
        self.history_actions.setSpacing(8)

        self.history_table = QTableWidget(0, 6)
        self.history_table.setObjectName("operationHistoryTable")
        self.history_table.setHorizontalHeaderLabels(
            ("Updated", "Operation", "Status", "Risk", "Books", "Component")
        )
        configure_table(self.history_table, row_height=32)
        self.history_table.setMinimumHeight(100)
        self.history_table.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Expanding,
        )
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.itemSelectionChanged.connect(
            self._history_selection_changed
        )

        self.history_status = QLabel()
        self.history_status.setObjectName("historyStatus")
        self.history_status.setWordWrap(True)
        self.history_status.setMaximumHeight(48)

        self.plan_tab = QWidget()
        plan_tab_layout = QVBoxLayout(self.plan_tab)
        plan_tab_layout.setContentsMargins(12, 12, 12, 12)
        plan_tab_layout.setSpacing(8)
        plan_tab_layout.addLayout(self.plan_actions)
        plan_tab_layout.addWidget(self.execution_progress)
        plan_tab_layout.addWidget(self.plan_panel, 1)

        self.history_tab = QWidget()
        history_tab_layout = QVBoxLayout(self.history_tab)
        history_tab_layout.setContentsMargins(12, 12, 12, 12)
        history_tab_layout.setSpacing(8)
        history_tab_layout.addLayout(self.history_actions)
        history_tab_layout.addWidget(self.history_table, 1)

        self.view_tabs = QTabWidget()
        self.view_tabs.setObjectName("protectionHistoryTabs")
        self.view_tabs.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Expanding,
        )
        self.view_tabs.addTab(self.plan_tab, "Plan Preview")
        self.view_tabs.addTab(self.history_tab, "Operation History")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.view_tabs, 1)
        layout.addWidget(self.history_status)

        self.refresh_history()
        self._refresh_actions()
        self._apply_responsive_layout(self.width())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = (
            self._forced_compact
            if self._forced_compact is not None
            else event.size().width() < 560
        )
        self._arrange_actions(compact)
        self._set_compact_columns(event.size().width() < 760)

    def _apply_responsive_layout(self, width: int) -> None:
        self._arrange_actions(width < 560)
        self._set_compact_columns(width < 760)

    def set_compact_mode(self, compact: bool) -> None:
        """Follow the containing page width, avoiding layout-size feedback."""
        self._forced_compact = bool(compact)
        self._arrange_actions(self._forced_compact)
        self._set_compact_columns(compact or self.width() < 760)

    def set_available_width(self, width: int) -> None:
        """Adapt to the page viewport instead of child size hints."""
        self._forced_compact = width < 560
        self._arrange_actions(self._forced_compact)
        self._set_compact_columns(width < 780)

    def _set_compact_columns(self, compact: bool) -> None:
        """Omit secondary history facts before the table needs side-scroll."""
        self.history_table.setColumnHidden(4, compact)
        self.history_table.setColumnHidden(5, compact)
        header = self.history_table.horizontalHeader()
        if compact:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(0, 145)
            header.resizeSection(2, 95)
            header.resizeSection(3, 75)
        else:
            header.setSectionResizeMode(
                0,
                QHeaderView.ResizeMode.ResizeToContents,
            )
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            for column in (2, 3, 4, 5):
                header.setSectionResizeMode(
                    column,
                    QHeaderView.ResizeMode.ResizeToContents,
                )

    def _arrange_actions(self, compact: bool) -> None:
        for widget in (
            self.preview_button,
            self.reversible_button,
            self.undo_button,
            self.approve_button,
            self.apply_button,
            self.cancel_plan_button,
        ):
            self.plan_actions.removeWidget(widget)
        for widget in (
            self.history_heading,
            self.refresh_button,
            self.export_button,
        ):
            self.history_actions.removeWidget(widget)
        if compact:
            self.plan_actions.addWidget(self.preview_button, 0, 0)
            self.plan_actions.addWidget(self.reversible_button, 0, 1)
            self.plan_actions.addWidget(self.undo_button, 1, 0)
            self.plan_actions.addWidget(self.approve_button, 1, 1)
            self.plan_actions.addWidget(self.apply_button, 2, 0)
            self.plan_actions.addWidget(self.cancel_plan_button, 2, 1)
            self.plan_actions.setColumnStretch(0, 1)
            self.plan_actions.setColumnStretch(1, 1)
            self.plan_actions.setColumnStretch(2, 0)
            self.history_actions.addWidget(
                self.history_heading,
                0,
                0,
                1,
                2,
            )
            self.history_actions.addWidget(self.refresh_button, 1, 0)
            self.history_actions.addWidget(self.export_button, 1, 1)
        else:
            self.plan_actions.addWidget(self.preview_button, 0, 0)
            self.plan_actions.addWidget(self.reversible_button, 0, 1)
            self.plan_actions.addWidget(self.undo_button, 0, 2)
            self.plan_actions.addWidget(self.approve_button, 1, 0)
            self.plan_actions.addWidget(self.apply_button, 1, 1)
            self.plan_actions.addWidget(self.cancel_plan_button, 1, 2)
            for column in range(3):
                self.plan_actions.setColumnStretch(column, 1)
            self.history_actions.addWidget(self.history_heading, 0, 0)
            self.history_actions.addWidget(self.refresh_button, 0, 1)
            self.history_actions.addWidget(self.export_button, 0, 2)
        self.history_actions.setColumnStretch(0, 1)

    def activate(self) -> None:
        if not self.is_busy():
            self.refresh_history(
                self.current_record.operation_id
                if self.current_record is not None
                else None
            )

    def show_operation(self, operation_id: int) -> OperationRecord:
        """Select one audit record and reveal its readable details."""
        record = self.service.get_operation(operation_id)
        self.current_record = record
        self._render_record(record)
        self.refresh_history(record.operation_id)
        self.view_tabs.setCurrentWidget(self.plan_tab)
        return record

    def start_approved_operation(self, operation_id: int) -> None:
        """Start an already approved internal operation."""
        self.show_operation(operation_id)
        self._start_execution(operation_id)

    def _preview_safety_check(self) -> None:
        if self.is_busy():
            return
        try:
            record = self.service.record_change_plan(
                self.service.build_safety_check_plan()
            )
        except Exception as error:
            self.history_status.setText(
                f"The safety plan could not be recorded: {error}"
            )
            return
        self.current_record = record
        self._render_record(record)
        self.refresh_history(record.operation_id)
        self.history_status.setText(
            "Safety-check preview recorded. No catalogue, metadata, or "
            "ebook-file change occurred."
        )

    def _preview_reversible_change(self) -> None:
        if self.is_busy():
            return
        try:
            record = self.service.record_change_plan(
                self.service.build_reversible_test_plan()
            )
        except Exception as error:
            self.history_status.setText(
                f"The reversible plan could not be recorded: {error}"
            )
            return
        self.current_record = record
        self._render_record(record)
        self.refresh_history(record.operation_id)
        self.history_status.setText(
            "Reversible test change previewed. Review it, then Approve and "
            "Apply separately."
        )

    def _preview_undo_current(self) -> None:
        record = self.current_record
        if record is None or self.is_busy():
            return
        try:
            undo = self.service.preview_undo_operation(record.operation_id)
        except Exception as error:
            self.history_status.setText(
                f"Undo could not be previewed: {error}"
            )
            return
        self.current_record = undo
        self._render_record(undo)
        self.refresh_history(undo.operation_id)
        self.view_tabs.setCurrentWidget(self.plan_tab)
        self.history_status.setText(
            "Undo preview recorded. Review it, then Approve and Apply "
            "separately."
        )

    def _approve_current(self) -> None:
        record = self.current_record
        if record is None or record.status != OperationStatus.PLANNED:
            return
        plan = record.plan
        text = ""
        requirement = plan.confirmation_requirement
        if requirement == ConfirmationRequirement.EXPLICIT:
            answer = QMessageBox.question(
                self,
                "Approve Change Plan",
                "Record approval for this exact plan?\n\n"
                "Approval does not apply it. You will still choose Apply "
                "separately.",
                (
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                ),
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        elif requirement == ConfirmationRequirement.TYPE_PHRASE:
            text, accepted = QInputDialog.getText(
                self,
                "Confirm High-Risk Plan",
                f"Type exactly:\n{plan.confirmation_phrase}",
            )
            if not accepted:
                return
        confirmation = PlanConfirmation(
            plan_token=plan.plan_token,
            approved=True,
            confirmer="user",
            confirmation_text=text,
        )
        try:
            updated = self.service.approve_change_plan(
                record.operation_id,
                confirmation,
                current_basis_token=self.service.current_basis_token(record),
            )
        except Exception as error:
            self.history_status.setText(
                f"The plan could not be approved: {error}"
            )
            return
        self.current_record = updated
        self._render_record(updated)
        self.refresh_history(updated.operation_id)
        self.history_status.setText(
            "Plan approval recorded. Nothing was applied. Use Apply "
            "Plan when this plan has an available executor."
        )

    def _apply_current(self) -> None:
        record = self.current_record
        if (
            record is None
            or record.status != OperationStatus.APPROVED
            or self.is_busy()
        ):
            return
        if (
            record.plan.operation_type == "database_restore"
            and not self.restore_idle_check()
        ):
            self.history_status.setText(
                "Finish the current scan or Library loading first, then "
                "try Restore again."
            )
            return
        if record.plan.operation_type == "database_restore":
            prompt = (
                "Restore the selected catalogue backup?\n\n"
                "Twano will check the backup again and automatically make "
                "a safety copy of the current catalogue first. Ebook files "
                "will not be changed."
            )
        elif record.plan.operation_type == "backup_retention_cleanup":
            prompt = (
                "Delete the exact old backups shown in this review?\n\n"
                "Twano will check every backup again. Unrelated or changed "
                "files will not be deleted."
            )
        else:
            prompt = (
                "Create and verify a catalogue backup, revalidate this exact "
                "plan, then apply its database change atomically?\n\n"
                "No ebook file will be changed."
            )
        answer = QMessageBox.question(
            self,
            "Apply Protected Plan",
            prompt,
            (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start_execution(record.operation_id)

    def _start_execution(self, operation_id: int) -> None:
        if self.is_busy():
            return
        stored = self.preferences.load_protection_preferences()
        folder = (
            Path(stored.backup_folder)
            if stored.backup_folder
            else self.service.default_backup_folder()
        )
        try:
            policy = self.service.build_policy(
                folder,
                stored.retention_days,
            )
            mode = ProtectionMode(
                self.preferences.load_home_preferences().protection_mode
            )
        except (OSError, ValueError) as error:
            self.history_status.setText(str(error))
            return
        if mode == ProtectionMode.READ_ONLY:
            self.history_status.setText(
                "Protected Apply is unavailable in Read-Only mode."
            )
            return
        try:
            record = self.service.get_operation(operation_id)
        except Exception as error:
            self.history_status.setText(str(error))
            return
        if (
            record.plan.operation_type == "database_restore"
            and not self.restore_idle_check()
        ):
            self.history_status.setText(
                "Finish the current scan or Library loading first, then "
                "try Restore again."
            )
            return

        self._executing_operation_id = int(operation_id)
        self._executing_operation_type = record.plan.operation_type
        self.execution_progress.setValue(0)
        self.execution_progress.setVisible(True)
        self.history_status.setText(
            "Preparing the required verified backup…"
        )
        thread = QThread(self)
        worker = ProtectionExecutorWorker(
            operation_id,
            policy,
            mode,
            self.service_factory,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress_changed.connect(self._execution_progress_changed)
        worker.completed.connect(self._execution_completed)
        worker.cancelled.connect(self._execution_cancelled)
        worker.failed.connect(self._execution_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._execution_thread_finished)
        self.executor_thread = thread
        self.executor_worker = worker
        if self._executing_operation_type == "database_restore":
            self.database_replacement_active.emit(True)
        self._refresh_actions()
        thread.start()

    def _execution_progress_changed(
        self,
        percent: int,
        message: str,
    ) -> None:
        self.execution_progress.setValue(percent)
        self.history_status.setText(message)

    def _execution_completed(self, record: OperationRecord) -> None:
        self.execution_progress.setValue(100)
        self.current_record = record
        self._render_record(record)
        self.refresh_history(record.operation_id)
        if record.plan.operation_type == "database_restore":
            action = (
                "Catalogue restored. Twano kept a verified safety copy of "
                "the previous catalogue."
            )
        elif record.plan.operation_type == "backup_retention_cleanup":
            action = "The reviewed old backups were removed."
        elif record.plan.operation_type == "undo_collection_create":
            action = "Undo completed atomically."
        else:
            action = (
                "Protected change applied atomically. Persistent Undo is "
                "now available."
            )
        self.history_status.setText(
            action
        )
        self.evidence_changed.emit()
        if record.plan.operation_type == "database_restore":
            self.catalogue_restored.emit()
        elif record.plan.operation_type != "backup_retention_cleanup":
            self.catalogue_changed.emit()

    def _execution_cancelled(self, message: str) -> None:
        self.execution_progress.setValue(0)
        self.history_status.setText(message)
        self._refresh_executing_record()
        self.evidence_changed.emit()

    def _execution_failed(self, message: str) -> None:
        self.execution_progress.setValue(0)
        self.history_status.setText(message)
        self._refresh_executing_record()
        self.evidence_changed.emit()

    def _refresh_executing_record(self) -> None:
        if self._executing_operation_id is None:
            return
        try:
            record = self.service.get_operation(
                self._executing_operation_id
            )
        except Exception:
            self.refresh_history()
            return
        self.current_record = record
        self._render_record(record)
        self.refresh_history(record.operation_id)

    def _execution_thread_finished(self) -> None:
        if self._executing_operation_type == "database_restore":
            self.database_replacement_active.emit(False)
        self.executor_thread = None
        self.executor_worker = None
        self._executing_operation_id = None
        self._executing_operation_type = ""
        self.execution_progress.setVisible(False)
        self._refresh_actions()
        self.background_stopped.emit()

    def _cancel_current(self) -> None:
        if self.executor_worker is not None:
            self.history_status.setText(
                "Cancelling before the atomic database transaction…"
            )
            self.executor_worker.request_cancel()
            self.cancel_plan_button.setEnabled(False)
            return
        if self.is_busy():
            return
        record = self.current_record
        if record is None or record.status not in {
            OperationStatus.PLANNED,
            OperationStatus.APPROVED,
        }:
            return
        try:
            updated = self.service.cancel_change_plan(
                record.operation_id
            )
        except Exception as error:
            self.history_status.setText(
                f"The plan could not be cancelled: {error}"
            )
            return
        self.current_record = updated
        self._render_record(updated)
        self.refresh_history(updated.operation_id)
        self.history_status.setText(
            "Plan cancelled. No intended database or file change was "
            "executed."
        )

    def refresh_history(self, selected_id: int | None = None) -> None:
        try:
            records = self.service.list_operation_history(limit=100)
        except Exception as error:
            self.history_table.setRowCount(0)
            self.history_status.setText(
                f"Operation history could not be loaded: {error}"
            )
            self._refresh_actions()
            return
        self.history_table.setRowCount(len(records))
        selected_row = -1
        for row, record in enumerate(records):
            updated_item = QTableWidgetItem(
                self._format_time(record.updated_at)
            )
            updated_item.setData(
                Qt.ItemDataRole.UserRole,
                record.operation_id,
            )
            title_item = QTableWidgetItem(record.plan.title)
            status_item = QTableWidgetItem(
                STATUS_LABELS[record.status]
            )
            status_item.setForeground(
                QColor(STATUS_COLOURS[record.status])
            )
            risk_item = QTableWidgetItem(
                record.plan.risk.value.title()
            )
            books_item = QTableWidgetItem(
                str(record.plan.affected_book_count)
            )
            component_item = QTableWidgetItem(
                record.plan.component.replace("_", " ").title()
            )
            for column, item in enumerate(
                (
                    updated_item,
                    title_item,
                    status_item,
                    risk_item,
                    books_item,
                    component_item,
                )
            ):
                self.history_table.setItem(row, column, item)
            if record.operation_id == selected_id:
                selected_row = row
        if selected_row >= 0:
            self.history_table.selectRow(selected_row)
        elif records and selected_id is None:
            self.history_table.selectRow(0)
        elif not records:
            self.current_record = None
            self._render_empty()
        self._refresh_actions()

    def _history_selection_changed(self) -> None:
        operation_id = self._selected_operation_id()
        if operation_id is None:
            self._refresh_actions()
            return
        try:
            record = self.service.get_operation(operation_id)
        except Exception as error:
            self.history_status.setText(
                f"Operation details could not be loaded: {error}"
            )
            return
        self.current_record = record
        self._render_record(record)
        self._refresh_actions()

    def _render_empty(self) -> None:
        self.plan_title.setText("No change plan selected")
        self.plan_facts.setText(
            "Use Preview Safety Check or select a history row."
        )
        self.plan_details.setHtml(
            "<p>No persistent operations have been recorded yet.</p>"
        )

    def _render_record(self, record: OperationRecord) -> None:
        plan = record.plan
        recovery_label = {
            Reversibility.FULL: "Undo available",
            Reversibility.PARTIAL: "Limited recovery",
            Reversibility.NONE: "No Undo",
            Reversibility.NOT_APPLICABLE: "Not applicable",
        }[plan.reversibility]
        if plan.operation_type == "scan_apply":
            recovery_label = "No one-click Undo; safety backup available"
        self.plan_title.setText(plan.title)
        self.plan_facts.setText(
            f"Status: {STATUS_LABELS[record.status]}  •  "
            f"Safety level: {plan.risk.value.title()}  •  "
            f"Recovery: {recovery_label}  •  "
            f"Affected books: {plan.affected_book_count}"
        )
        database_items = self._items_html(plan.database_changes)
        file_items = self._items_html(plan.file_changes)
        warnings = "".join(
            f"<li>{escape(warning)}</li>" for warning in plan.warnings
        ) or "<li>None recorded.</li>"
        outcome = (
            f"<p><b>Error:</b> "
            f"{escape(record.error_summary or 'None')}<br>"
            f"<b>Rollback:</b> "
            f"{escape(record.rollback_outcome or 'Not required')}<br>"
            f"<b>Backup:</b> "
            f"{escape(record.backup_identity or 'None')}<br>"
            f"<b>Source operation:</b> "
            f"{record.source_operation_id or 'None'}<br>"
            f"<b>Validated inverse:</b> "
            f"{'Stored' if any(item.inverse_json for item in record.items) else 'None'}"
            "</p>"
        )
        self.plan_details.setHtml(
            f"<p>{escape(plan.summary)}</p>"
            "<h4>Intended database changes</h4>"
            f"{database_items}"
            "<h4>Intended file changes</h4>"
            f"{file_items}"
            "<h4>Warnings</h4>"
            f"<ul>{warnings}</ul>"
            "<h4>Outcome evidence</h4>"
            f"{outcome}"
        )

    @staticmethod
    def _items_html(items) -> str:
        if not items:
            return "<p>None.</p>"
        values = "".join(
            (
                f"<li><b>"
                f"{escape(item.action.replace('_', ' ').title())}</b> — "
                f"{escape(item.description)}</li>"
            )
            for item in items
        )
        return f"<ol>{values}</ol>"

    def _export_selected(self) -> None:
        operation_id = self._selected_operation_id()
        if operation_id is None or self.is_busy():
            return
        destination, _filter = QFileDialog.getSaveFileName(
            self,
            "Export Operation Report",
            str(
                Path.home()
                / "Documents"
                / f"Twano-operation-{operation_id}.md"
            ),
            "Markdown report (*.md);;Text report (*.txt)",
        )
        if not destination:
            return
        self._start_export(operation_id, Path(destination))

    def _start_export(
        self,
        operation_id: int,
        destination: Path,
    ) -> None:
        if self.is_busy():
            return
        self.history_status.setText("Exporting operation report…")
        self._refresh_actions()
        thread = QThread(self)
        worker = AuditExportWorker(
            operation_id,
            destination,
            self.service_factory,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._export_completed)
        worker.cancelled.connect(self.history_status.setText)
        worker.failed.connect(self.history_status.setText)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._export_thread_finished)
        self.export_thread = thread
        self.export_worker = worker
        self._refresh_actions()
        thread.start()

    def _export_completed(self, destination: str) -> None:
        self.history_status.setText(
            f"Operation report exported to {destination}"
        )

    def _export_thread_finished(self) -> None:
        self.export_thread = None
        self.export_worker = None
        self._refresh_actions()
        self.background_stopped.emit()

    def is_busy(self) -> bool:
        return (
            self.export_thread is not None
            or self.executor_thread is not None
        )

    def cancel_active_operation(self) -> None:
        if self.executor_worker is not None:
            self.history_status.setText(
                "Cancelling before the atomic database transaction…"
            )
            self.executor_worker.request_cancel()
        if self.export_worker is not None:
            self.history_status.setText(
                "Cancelling operation-report export…"
            )
            self.export_worker.request_cancel()

    def cancel_active_export(self) -> None:
        """Compatibility wrapper for the former export-only lifecycle."""
        self.cancel_active_operation()

    def _refresh_actions(self) -> None:
        busy = self.is_busy()
        status = (
            self.current_record.status
            if self.current_record is not None
            else None
        )
        self.preview_button.setEnabled(not busy)
        self.reversible_button.setEnabled(not busy)
        self.approve_button.setEnabled(
            not busy and status == OperationStatus.PLANNED
        )
        executable = (
            self.current_record is not None
            and self.current_record.plan.operation_type
            in {
                "collection_create",
                "undo_collection_create",
                "database_restore",
                "backup_retention_cleanup",
            }
        )
        standard_mode = (
            self.preferences.load_home_preferences().protection_mode
            == ProtectionMode.STANDARD
        )
        self.apply_button.setEnabled(
            not busy
            and status == OperationStatus.APPROVED
            and executable
            and standard_mode
        )
        undo_available = (
            not busy
            and self.current_record is not None
            and self.service.can_preview_undo(
                self.current_record.operation_id
            )
        )
        self.undo_button.setEnabled(undo_available)
        executing = self.executor_thread is not None
        self.cancel_plan_button.setText(
            "Cancel Operation" if executing else "Cancel Plan"
        )
        self.cancel_plan_button.setEnabled(
            executing
            or (
                not busy
                and status in {
                    OperationStatus.PLANNED,
                    OperationStatus.APPROVED,
                }
            )
        )
        self.refresh_button.setEnabled(not busy)
        self.export_button.setEnabled(
            not busy and self._selected_operation_id() is not None
        )

    def _selected_operation_id(self) -> int | None:
        row = self.history_table.currentRow()
        if row < 0:
            return None
        item = self.history_table.item(row, 0)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    @staticmethod
    def _format_time(value: str) -> str:
        try:
            timestamp = datetime.fromisoformat(value)
            if timestamp.tzinfo is not None:
                timestamp = timestamp.astimezone()
            return timestamp.strftime("%d %b %Y %H:%M")
        except (TypeError, ValueError):
            return "Unknown"

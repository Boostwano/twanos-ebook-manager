"""RC6.7 Protection Centre for verified catalogue backups."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from preferences import (
    PreferencesStore,
    ProtectionMode,
    ProtectionPreferences,
)
from services.protection_models import PlanConfirmation
from services.protection_service import (
    BackupPolicy,
    BackupRecord,
    BackupStatus,
    ProtectionService,
    RetentionPreview,
)
from ui.protection_history import ProtectionHistoryPanel
from ui.theme import configure_table
from workers.backup_worker import BackupWorker
from workers.protection_executor_worker import ProtectionExecutorWorker


STATUS_LABELS = {
    BackupStatus.VERIFIED: "Verified",
    BackupStatus.MODIFIED: "Changed",
    BackupStatus.INVALID: "Invalid",
    BackupStatus.UNVERIFIED: "Unverified",
    BackupStatus.MISSING: "Missing",
}
STATUS_COLOURS = {
    BackupStatus.VERIFIED: "#86d99a",
    BackupStatus.MODIFIED: "#efc270",
    BackupStatus.INVALID: "#f08a91",
    BackupStatus.UNVERIFIED: "#b8c9d9",
    BackupStatus.MISSING: "#f08a91",
}


class ProtectionPage(QWidget):
    """Responsive UI for backup policy, creation, and verification."""

    backup_stopped = Signal()
    catalogue_changed = Signal()
    catalogue_restored = Signal()
    database_replacement_active = Signal(bool)

    def __init__(
        self,
        preferences: PreferencesStore,
        service_factory: Callable[[], ProtectionService] | None = None,
        restore_idle_check: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__()
        self.preferences = preferences
        self.service_factory = service_factory or ProtectionService
        self.restore_idle_check = restore_idle_check or (lambda: True)
        self.presentation_service = self.service_factory()
        self.backup_thread: QThread | None = None
        self.backup_worker: BackupWorker | None = None
        self.maintenance_thread: QThread | None = None
        self.maintenance_worker: ProtectionExecutorWorker | None = None
        self._maintenance_operation_id: int | None = None
        self._maintenance_operation_type = ""
        self._pending_cleanup_preview: RetentionPreview | None = None
        self._active_operation = ""

        title = QLabel("Protection & Undo")
        title.setObjectName("pageTitle")
        title.setTextFormat(Qt.TextFormat.PlainText)
        description = QLabel(
            "Create safety copies, restore an earlier catalogue, or review "
            "old backups. Ebook files are never changed here."
        )
        description.setObjectName("pageDescription")
        description.setWordWrap(True)

        policy_panel = QFrame()
        policy_panel.setObjectName("protectionPolicyPanel")
        self.policy_layout = QGridLayout(policy_panel)
        self.policy_layout.setContentsMargins(20, 18, 20, 18)
        self.policy_layout.setHorizontalSpacing(12)
        self.policy_layout.setVerticalSpacing(10)

        self.database_heading = QLabel("Live catalogue")
        self.database_heading.setObjectName("fieldLabel")
        self.database_path_label = QLineEdit(
            str(self.presentation_service.live_database_path)
        )
        self.database_path_label.setObjectName("protectedPath")
        self.database_path_label.setReadOnly(True)
        self.database_path_label.setMinimumWidth(0)

        self.folder_heading = QLabel("Backup folder")
        self.folder_heading.setObjectName("fieldLabel")
        self.backup_folder_edit = QLineEdit()
        self.backup_folder_edit.setObjectName("backupFolder")
        self.backup_folder_edit.setPlaceholderText(
            "Choose an absolute folder for verified backups"
        )
        self.browse_button = QPushButton("Browse…")
        self.browse_button.setObjectName("browseBackupAction")
        self.browse_button.clicked.connect(self._browse_for_folder)
        self.folder_controls = QWidget()
        self.folder_controls.setObjectName("inlineControls")
        folder_layout = QHBoxLayout(self.folder_controls)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(8)
        folder_layout.addWidget(self.backup_folder_edit, 1)
        folder_layout.addWidget(self.browse_button)

        self.retention_heading = QLabel("Keep backups for")
        self.retention_heading.setObjectName("fieldLabel")
        self.retention_days = QSpinBox()
        self.retention_days.setObjectName("backupRetentionDays")
        self.retention_days.setRange(0, 36500)
        self.retention_days.setSpecialValueText("Keep all backups")
        self.retention_days.setSuffix(" days")
        self.retention_days.setToolTip(
            "0 keeps every verified backup. Automatic cleanup is not "
            "enabled in this checkpoint."
        )
        self.save_policy_button = QPushButton("Save Backup Settings")
        self.save_policy_button.setObjectName("saveBackupPolicyAction")
        self.save_policy_button.clicked.connect(self._save_policy)

        self.action_layout = QGridLayout()
        self.action_layout.setContentsMargins(0, 0, 0, 0)
        self.action_layout.setHorizontalSpacing(8)
        self.action_layout.setVerticalSpacing(8)
        self.create_button = QPushButton("Create Verified Backup")
        self.create_button.setObjectName("createBackupAction")
        self.create_button.clicked.connect(self._create_backup)
        self.verify_button = QPushButton("Verify Selected Backup")
        self.verify_button.setObjectName("verifyBackupAction")
        self.verify_button.clicked.connect(self._verify_selected_backup)
        self.restore_button = QPushButton("Restore Backup")
        self.restore_button.setObjectName("restoreBackupAction")
        self.restore_button.clicked.connect(self._restore_selected_backup)
        self.cleanup_button = QPushButton("Review Old Backups")
        self.cleanup_button.setObjectName("reviewOldBackupsAction")
        self.cleanup_button.clicked.connect(self._preview_cleanup)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancelBackupAction")
        self.cancel_button.clicked.connect(self.cancel_active_operation)
        for button in (
            self.create_button,
            self.verify_button,
            self.restore_button,
            self.cleanup_button,
            self.cancel_button,
        ):
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("backupProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)

        self.status_label = QLabel()
        self.status_label.setObjectName("backupStatus")
        self.status_label.setWordWrap(True)

        self.backup_table = QTableWidget(0, 4)
        self.backup_table.setObjectName("backupTable")
        self.backup_table.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Expanding,
        )
        self.backup_table.setHorizontalHeaderLabels(
            ("Created", "Size", "Status", "File")
        )
        configure_table(self.backup_table, row_height=32)
        header = self.backup_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.backup_table.itemSelectionChanged.connect(
            self._selection_changed
        )

        self.history_panel = ProtectionHistoryPanel(
            self.service_factory,
            self.presentation_service,
            self.preferences,
            self.restore_idle_check,
        )
        self.history_panel.background_stopped.connect(
            self.backup_stopped.emit
        )
        self.history_panel.evidence_changed.connect(
            self.refresh_backups
        )
        self.history_panel.catalogue_changed.connect(
            self.catalogue_changed.emit
        )
        self.history_panel.catalogue_restored.connect(
            self.catalogue_restored.emit
        )
        self.history_panel.database_replacement_active.connect(
            self.database_replacement_active.emit
        )

        self.backup_tab = QWidget()
        self.backup_tab.setObjectName("protectionBackupTab")
        self.backup_tab.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Expanding,
        )
        backup_layout = QVBoxLayout(self.backup_tab)
        backup_layout.setContentsMargins(14, 14, 14, 14)
        backup_layout.setSpacing(9)
        backup_layout.addWidget(policy_panel)
        backup_layout.addLayout(self.action_layout)
        backup_layout.addWidget(self.progress_bar)
        backup_layout.addWidget(self.status_label)
        backup_layout.addWidget(self.backup_table, 1)

        self.page_tabs = QTabWidget()
        self.page_tabs.setObjectName("protectionTabs")
        self.page_tabs.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Expanding,
        )
        self.page_tabs.addTab(self.backup_tab, "Backups && Restore")
        self.page_tabs.addTab(self.history_panel, "Activity && Undo")
        self.page_tabs.setCurrentWidget(self.backup_tab)

        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(32, 24, 32, 24)
        self.content_layout.setSpacing(8)
        self.content_layout.addWidget(title)
        self.content_layout.addWidget(description)
        self.content_layout.addWidget(self.page_tabs, 1)

        self._load_policy()
        self.refresh_backups()
        self._set_busy(False)
        self._apply_responsive_layout(self.width())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())

    def _apply_responsive_layout(self, page_width: int) -> None:
        """Reflow controls before restored windows can clip the right edge."""
        policy_widgets = (
            self.database_heading,
            self.database_path_label,
            self.folder_heading,
            self.folder_controls,
            self.retention_heading,
            self.retention_days,
            self.save_policy_button,
        )
        for widget in policy_widgets:
            self.policy_layout.removeWidget(widget)
        for button in (
            self.create_button,
            self.verify_button,
            self.restore_button,
            self.cleanup_button,
            self.cancel_button,
        ):
            self.action_layout.removeWidget(button)

        compact = page_width < 560
        margin = 16 if compact else 32
        self.content_layout.setContentsMargins(
            margin,
            16 if compact else 24,
            margin,
            16 if compact else 24,
        )
        if hasattr(self, "history_panel"):
            self.history_panel.set_available_width(page_width)
        if compact:
            self.policy_layout.addWidget(
                self.database_heading,
                0,
                0,
                1,
                3,
            )
            self.policy_layout.addWidget(
                self.database_path_label,
                1,
                0,
                1,
                3,
            )
            self.policy_layout.addWidget(
                self.folder_heading,
                2,
                0,
                1,
                3,
            )
            self.policy_layout.addWidget(
                self.folder_controls,
                3,
                0,
                1,
                3,
            )
            self.policy_layout.addWidget(
                self.retention_heading,
                4,
                0,
            )
            self.policy_layout.addWidget(
                self.retention_days,
                4,
                1,
                1,
                2,
            )
            self.policy_layout.addWidget(
                self.save_policy_button,
                5,
                0,
                1,
                3,
            )
            self.action_layout.addWidget(self.create_button, 0, 0)
            self.action_layout.addWidget(self.verify_button, 0, 1)
            self.action_layout.addWidget(self.restore_button, 1, 0)
            self.action_layout.addWidget(self.cleanup_button, 1, 1)
            self.action_layout.addWidget(
                self.cancel_button,
                2,
                0,
                1,
                2,
            )
            self.action_layout.setColumnStretch(0, 1)
            self.action_layout.setColumnStretch(1, 1)
            self.action_layout.setColumnStretch(2, 0)
        else:
            self.policy_layout.addWidget(
                self.database_heading,
                0,
                0,
            )
            self.policy_layout.addWidget(
                self.database_path_label,
                0,
                1,
                1,
                2,
            )
            self.policy_layout.addWidget(
                self.folder_heading,
                1,
                0,
            )
            self.policy_layout.addWidget(
                self.folder_controls,
                1,
                1,
                1,
                2,
            )
            self.policy_layout.addWidget(
                self.retention_heading,
                2,
                0,
            )
            self.policy_layout.addWidget(
                self.retention_days,
                2,
                1,
            )
            self.policy_layout.addWidget(
                self.save_policy_button,
                2,
                2,
            )
            self.action_layout.addWidget(self.create_button, 0, 0)
            self.action_layout.addWidget(self.verify_button, 0, 1)
            self.action_layout.addWidget(self.restore_button, 0, 2)
            self.action_layout.addWidget(self.cleanup_button, 1, 0, 1, 2)
            self.action_layout.addWidget(self.cancel_button, 1, 2)
            for column in range(3):
                self.action_layout.setColumnStretch(column, 1)
        self.policy_layout.setColumnStretch(1, 1)

    def activate(self) -> None:
        """Refresh cheap backup evidence whenever the page is opened."""
        if not self.is_busy():
            self._load_policy()
            self.refresh_backups()
            self.history_panel.activate()

    def _load_policy(self) -> None:
        stored = self.preferences.load_protection_preferences()
        folder = (
            Path(stored.backup_folder)
            if stored.backup_folder
            else self.presentation_service.default_backup_folder()
        )
        self.backup_folder_edit.setText(str(folder))
        self.retention_days.setValue(stored.retention_days)

    def _browse_for_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose Backup Folder",
            self.backup_folder_edit.text().strip(),
        )
        if folder:
            self.backup_folder_edit.setText(folder)

    def _policy_from_form(self, *, save: bool) -> BackupPolicy | None:
        try:
            policy = self.presentation_service.build_policy(
                self.backup_folder_edit.text().strip(),
                self.retention_days.value(),
            )
            if save:
                self.preferences.save_protection_preferences(
                    ProtectionPreferences(
                        backup_folder=str(policy.folder),
                        retention_days=policy.retention_days,
                    )
                )
                self.preferences.sync()
        except (OSError, ValueError) as error:
            self.status_label.setText(str(error))
            return None
        return policy

    def _save_policy(self) -> None:
        policy = self._policy_from_form(save=True)
        if policy is None:
            return
        self.status_label.setText(
            "Backup settings saved. "
            + (
                "All verified backups will be retained."
                if policy.retention_days == 0
                else (
                    f"Backups older than {policy.retention_days} days can "
                    "be reviewed before removal."
                )
            )
        )
        self.refresh_backups()

    def refresh_backups(
        self,
        selected_path: Path | None = None,
    ) -> None:
        policy = self._policy_from_form(save=False)
        records = (
            self.presentation_service.list_backups(policy)
            if policy is not None
            else ()
        )
        self.backup_table.setRowCount(len(records))
        selected_row = -1
        for row, record in enumerate(records):
            created_item = QTableWidgetItem(
                self._format_created_at(record.created_at)
            )
            created_item.setData(
                Qt.ItemDataRole.UserRole,
                str(record.path),
            )
            size_item = QTableWidgetItem(
                self._format_size(record.size_bytes)
            )
            status_item = QTableWidgetItem(
                STATUS_LABELS[record.status]
            )
            status_item.setData(
                Qt.ItemDataRole.UserRole,
                record.status.value,
            )
            status_item.setForeground(
                QColor(STATUS_COLOURS[record.status])
            )
            status_item.setToolTip(record.message)
            file_item = QTableWidgetItem(record.path.name)
            file_item.setToolTip(str(record.path))
            for column, item in enumerate(
                (created_item, size_item, status_item, file_item)
            ):
                self.backup_table.setItem(row, column, item)
            if (
                selected_path is not None
                and record.path == selected_path
            ):
                selected_row = row
        if selected_row >= 0:
            self.backup_table.selectRow(selected_row)
        self._selection_changed()

    def _create_backup(self) -> None:
        policy = self._policy_from_form(save=True)
        if policy is None:
            return
        self._start_worker("create", policy=policy)

    def _verify_selected_backup(self) -> None:
        path = self._selected_backup_path()
        if path is None:
            self.status_label.setText(
                "Select a backup in the table before verifying it."
            )
            return
        self._start_worker("verify", backup_path=path)

    def _restore_selected_backup(self) -> None:
        if self.is_busy():
            self.status_label.setText(
                "Wait for the current Protection task to finish."
            )
            return
        path = self._selected_backup_path()
        if path is None:
            self.status_label.setText(
                "Select a verified backup before restoring it."
            )
            return
        if not self._changes_allowed():
            return
        if not self.restore_idle_check():
            self.status_label.setText(
                "Finish the current scan or Library loading first, then "
                "try Restore again."
            )
            return
        inspected = self.presentation_service.inspect_backup(path)
        if inspected.status != BackupStatus.VERIFIED:
            self.status_label.setText(
                "This backup is not currently verified. Select Verify "
                "Selected Backup first."
            )
            return
        answer = QMessageBox.question(
            self,
            "Restore Backup",
            (
                f"Restore the catalogue saved on "
                f"{self._format_created_at(inspected.created_at)}?\n\n"
                "Twano will check this backup again and automatically make "
                "a safety copy of your current catalogue first.\n\n"
                "Your ebook files will not be changed."
            ),
            (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            planned = self.presentation_service.preview_restore_operation(
                path
            )
            approved = self.presentation_service.approve_change_plan(
                planned.operation_id,
                PlanConfirmation(
                    plan_token=planned.plan.plan_token,
                    approved=True,
                    confirmer="user",
                ),
                current_basis_token=(
                    self.presentation_service.current_basis_token(planned)
                ),
            )
        except Exception as error:
            self.status_label.setText(
                f"Restore could not start: {error}"
            )
            self.history_panel.refresh_history()
            return
        self._start_maintenance_operation(approved.operation_id)

    def _preview_cleanup(self) -> None:
        if self.is_busy():
            self.status_label.setText(
                "Wait for the current Protection task to finish."
            )
            return
        if not self._changes_allowed():
            return
        policy = self._policy_from_form(save=True)
        if policy is None:
            return
        if policy.retention_days == 0:
            self.status_label.setText(
                "All backups are currently being kept. Choose a number of "
                "days before reviewing old backups."
            )
            return
        self._start_worker("preview_cleanup", policy=policy)

    def _changes_allowed(self) -> bool:
        mode = self.preferences.load_home_preferences().protection_mode
        if mode == ProtectionMode.READ_ONLY:
            self.status_label.setText(
                "Switch protection mode to Standard before restoring or "
                "removing backups."
            )
            return False
        return True

    def _start_worker(
        self,
        operation: str,
        *,
        policy: BackupPolicy | None = None,
        backup_path: Path | None = None,
    ) -> None:
        if self.is_busy():
            return
        self._active_operation = operation
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText(
            "Starting verified backup…"
            if operation == "create"
            else "Starting backup verification…"
        )
        if operation == "preview_cleanup":
            self.status_label.setText("Reviewing old backups...")
        self._set_busy(True)

        thread = QThread(self)
        worker = BackupWorker(
            operation,
            self.service_factory,
            policy=policy,
            backup_path=backup_path,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress_changed.connect(self._progress_changed)
        worker.completed.connect(self._operation_completed)
        worker.cancelled.connect(self._operation_cancelled)
        worker.failed.connect(self._operation_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_finished)
        self.backup_thread = thread
        self.backup_worker = worker
        thread.start()

    def _progress_changed(self, percent: int, message: str) -> None:
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def _operation_completed(
        self,
        result: BackupRecord | RetentionPreview,
    ) -> None:
        self.progress_bar.setValue(100)
        if isinstance(result, RetentionPreview):
            self._pending_cleanup_preview = result
            self.status_label.setText("Old-backup review is ready.")
            return
        record = result
        self.refresh_backups(record.path)
        self.history_panel.refresh_history()
        if record.status == BackupStatus.VERIFIED:
            action = (
                "created and verified"
                if self._active_operation == "create"
                else "passed verification"
            )
            self.status_label.setText(
                f"{record.path.name} {action}. {record.message}"
            )
        else:
            self.status_label.setText(
                f"{record.path.name}: "
                f"{STATUS_LABELS[record.status]}. {record.message}"
            )

    def _cleanup_review_completed(
        self,
        preview: RetentionPreview,
    ) -> None:
        self.refresh_backups()
        self.history_panel.refresh_history()
        if preview.operation is None:
            self.status_label.setText(
                "No verified old backups need removing. Changed, "
                "unverified, and unrelated files were left alone."
            )
            return
        answer = QMessageBox.question(
            self,
            "Review Old Backups",
            (
                f"Twano found {preview.candidate_count} verified old "
                f"backup(s), using "
                f"{self._format_size(preview.candidate_bytes)}.\n\n"
                "Delete these reviewed backups?\n\n"
                "Changed, unverified, recent, and unrelated files will stay."
            ),
            (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.presentation_service.cancel_change_plan(
                preview.operation.operation_id
            )
            self.history_panel.refresh_history()
            self.status_label.setText(
                "Cleanup cancelled. No backup was removed."
            )
            return
        try:
            approved = self.presentation_service.approve_change_plan(
                preview.operation.operation_id,
                PlanConfirmation(
                    plan_token=preview.operation.plan.plan_token,
                    approved=True,
                    confirmer="user",
                ),
                current_basis_token=(
                    self.presentation_service.current_basis_token(
                        preview.operation
                    )
                ),
            )
        except Exception as error:
            self.status_label.setText(
                f"Cleanup could not start: {error}"
            )
            self.history_panel.refresh_history()
            return
        self.status_label.setText("Starting safe cleanup...")
        self._start_maintenance_operation(approved.operation_id)

    def _operation_cancelled(self, message: str) -> None:
        self.progress_bar.setValue(0)
        self.status_label.setText(message)
        self.refresh_backups()
        self.history_panel.refresh_history()

    def _operation_failed(self, message: str) -> None:
        self.progress_bar.setValue(0)
        self.status_label.setText(message)
        self.refresh_backups()
        self.history_panel.refresh_history()

    def _thread_finished(self) -> None:
        pending_preview = self._pending_cleanup_preview
        self._pending_cleanup_preview = None
        self.backup_thread = None
        self.backup_worker = None
        self._active_operation = ""
        self.progress_bar.setVisible(False)
        self._set_busy(False)
        if pending_preview is not None:
            QTimer.singleShot(
                0,
                lambda preview=pending_preview: (
                    self._cleanup_review_completed(preview)
                ),
            )
        else:
            self.backup_stopped.emit()

    def _start_maintenance_operation(self, operation_id: int) -> None:
        if self.is_busy():
            return
        stored = self.preferences.load_protection_preferences()
        folder = (
            Path(stored.backup_folder)
            if stored.backup_folder
            else self.presentation_service.default_backup_folder()
        )
        try:
            policy = self.presentation_service.build_policy(
                folder,
                stored.retention_days,
            )
            mode = ProtectionMode(
                self.preferences.load_home_preferences().protection_mode
            )
            record = self.presentation_service.get_operation(operation_id)
        except Exception as error:
            self.status_label.setText(str(error))
            return
        if mode != ProtectionMode.STANDARD:
            self.status_label.setText(
                "Switch protection mode to Standard before continuing."
            )
            return
        if (
            record.plan.operation_type == "database_restore"
            and not self.restore_idle_check()
        ):
            self.status_label.setText(
                "Finish the current scan or Library loading first, then "
                "try Restore again."
            )
            return

        self._maintenance_operation_id = operation_id
        self._maintenance_operation_type = record.plan.operation_type
        self._active_operation = self._maintenance_operation_type
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText(
            "Preparing Restore..."
            if self._maintenance_operation_type == "database_restore"
            else "Checking reviewed backups..."
        )
        self._set_busy(True)
        thread = QThread(self)
        worker = ProtectionExecutorWorker(
            operation_id,
            policy,
            mode,
            self.service_factory,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress_changed.connect(self._progress_changed)
        worker.completed.connect(self._maintenance_completed)
        worker.cancelled.connect(self._operation_cancelled)
        worker.failed.connect(self._operation_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._maintenance_thread_finished)
        self.maintenance_thread = thread
        self.maintenance_worker = worker
        if self._maintenance_operation_type == "database_restore":
            self.database_replacement_active.emit(True)
        thread.start()

    def _maintenance_completed(self, record) -> None:
        self.progress_bar.setValue(100)
        self.refresh_backups()
        self.history_panel.show_operation(record.operation_id)
        self.page_tabs.setCurrentWidget(self.backup_tab)
        if record.plan.operation_type == "database_restore":
            self.status_label.setText(
                "Catalogue restored. Twano kept a verified safety copy of "
                "the previous catalogue."
            )
            self.catalogue_restored.emit()
        else:
            self.status_label.setText(
                "The reviewed old backups were removed."
            )

    def _maintenance_thread_finished(self) -> None:
        if self._maintenance_operation_type == "database_restore":
            self.database_replacement_active.emit(False)
        self.maintenance_thread = None
        self.maintenance_worker = None
        self._maintenance_operation_id = None
        self._maintenance_operation_type = ""
        self._active_operation = ""
        self.progress_bar.setVisible(False)
        self._set_busy(False)
        self.backup_stopped.emit()

    def _selection_changed(self) -> None:
        selected = self._selected_backup_path() is not None
        verified = self._selected_backup_status() == BackupStatus.VERIFIED
        self.verify_button.setEnabled(not self.is_busy() and selected)
        self.restore_button.setEnabled(not self.is_busy() and verified)

    def _set_busy(self, busy: bool) -> None:
        self.backup_folder_edit.setEnabled(not busy)
        self.browse_button.setEnabled(not busy)
        self.retention_days.setEnabled(not busy)
        self.save_policy_button.setEnabled(not busy)
        self.create_button.setEnabled(not busy)
        self.cleanup_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.verify_button.setEnabled(
            not busy and self._selected_backup_path() is not None
        )
        self.restore_button.setEnabled(
            not busy
            and self._selected_backup_status() == BackupStatus.VERIFIED
        )

    def is_busy(self) -> bool:
        """Return whether a backup worker thread is active."""
        return (
            self.backup_thread is not None
            or self.maintenance_thread is not None
            or self.history_panel.is_busy()
        )

    def cancel_active_operation(self) -> None:
        """Request safe cancellation without waiting on the GUI thread."""
        if self.backup_worker is not None:
            self.status_label.setText(
                "Cancelling at the next safe backup boundary…"
            )
            self.cancel_button.setEnabled(False)
            self.backup_worker.request_cancel()
        if self.maintenance_worker is not None:
            self.status_label.setText(
                "Cancelling before the next safe boundary..."
            )
            self.cancel_button.setEnabled(False)
            self.maintenance_worker.request_cancel()
        self.history_panel.cancel_active_operation()

    def _selected_backup_status(self) -> BackupStatus | None:
        row = self.backup_table.currentRow()
        if row < 0:
            return None
        item = self.backup_table.item(row, 2)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        try:
            return BackupStatus(str(value))
        except ValueError:
            return None

    def _selected_backup_path(self) -> Path | None:
        row = self.backup_table.currentRow()
        if row < 0:
            return None
        item = self.backup_table.item(row, 0)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return Path(value) if value else None

    @staticmethod
    def _format_created_at(value: str) -> str:
        try:
            created_at = datetime.fromisoformat(value)
            if created_at.tzinfo is not None:
                created_at = created_at.astimezone()
            return created_at.strftime("%d %b %Y %H:%M")
        except (TypeError, ValueError):
            return "Unknown"

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        value = float(max(0, size_bytes))
        units = ("B", "KB", "MB", "GB", "TB")
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return (
                    f"{int(value)} {unit}"
                    if unit == "B"
                    else f"{value:.1f} {unit}"
                )
            value /= 1024
        return f"{size_bytes} B"

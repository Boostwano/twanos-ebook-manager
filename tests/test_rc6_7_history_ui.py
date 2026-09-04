"""RC6.7 change-plan preview, history, and report UI tests."""

from pathlib import Path
from time import monotonic, sleep

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea

from database.database import DatabaseManager
from preferences import PreferencesStore
from services.protection_models import OperationStatus
from services.protection_service import ProtectionService
from ui.protection_page import ProtectionPage


def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = monotonic() + timeout
    application = QApplication.instance()
    while monotonic() < deadline:
        application.processEvents()
        if predicate():
            return
        sleep(0.01)
    raise AssertionError("Timed out waiting for history worker")


def _page(
    tmp_path: Path,
) -> tuple[ProtectionPage, DatabaseManager]:
    database_path = tmp_path / "library.db"
    database = DatabaseManager(database_path)
    factory = lambda: ProtectionService(
        DatabaseManager(database_path)
    )
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "settings.ini"),
            QSettings.Format.IniFormat,
        )
    )
    return ProtectionPage(preferences, factory), database


def test_safety_preview_and_cancel_are_persistent_and_non_mutating(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, database = _page(tmp_path)
    panel = page.history_panel
    database.create_collection("Existing")

    panel.preview_button.click()

    assert panel.history_table.rowCount() == 1
    assert panel.current_record is not None
    assert panel.current_record.status == OperationStatus.PLANNED
    assert "No catalogue" in panel.history_status.text()
    assert panel.approve_button.isEnabled()
    assert panel.cancel_plan_button.isEnabled()
    assert database.count_books(include_missing=True) == 0

    panel.cancel_plan_button.click()

    assert panel.current_record.status == OperationStatus.CANCELLED
    assert panel.history_table.item(0, 2).text() == "Cancelled"
    assert "No intended database or file change" in (
        panel.history_status.text()
    )
    assert [row["name"] for row in database.list_collections()] == [
        "Existing"
    ]
    page.deleteLater()
    application.processEvents()


def test_approval_records_intent_only_and_history_survives_page_recreation(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, database = _page(tmp_path)
    panel = page.history_panel
    panel.preview_button.click()
    operation_id = panel.current_record.operation_id

    panel.approve_button.click()

    assert panel.current_record.status == OperationStatus.APPROVED
    assert "Nothing was applied" in panel.history_status.text()
    assert database.count_books(include_missing=True) == 0
    page.deleteLater()
    application.processEvents()

    recreated, _database = _page(tmp_path)
    recreated_panel = recreated.history_panel

    assert recreated_panel.history_table.rowCount() == 1
    assert recreated_panel.current_record.operation_id == operation_id
    assert recreated_panel.current_record.status == OperationStatus.APPROVED
    recreated.deleteLater()
    application.processEvents()


def test_operation_report_exports_off_gui_thread(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, _database = _page(tmp_path)
    panel = page.history_panel
    panel.preview_button.click()
    operation_id = panel.current_record.operation_id
    destination = tmp_path / "operation-report.md"

    panel._start_export(operation_id, destination)

    assert panel.is_busy()
    assert not panel.preview_button.isEnabled()
    _wait_until(lambda: not panel.is_busy())

    assert destination.is_file()
    assert "# Twano Operation Report" in destination.read_text(
        encoding="utf-8"
    )
    assert "exported to" in panel.history_status.text()
    assert panel.preview_button.isEnabled()
    page.deleteLater()
    application.processEvents()


def test_history_actions_are_distinct_and_compact_safe(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, _database = _page(tmp_path)
    panel = page.history_panel
    page.resize(690, 600)
    page.show()
    page.page_tabs.setCurrentWidget(panel)
    panel.view_tabs.setCurrentWidget(panel.plan_tab)
    application.processEvents()

    assert {
        panel.preview_button.objectName(),
        panel.reversible_button.objectName(),
        panel.undo_button.objectName(),
        panel.approve_button.objectName(),
        panel.apply_button.objectName(),
        panel.cancel_plan_button.objectName(),
        panel.refresh_button.objectName(),
        panel.export_button.objectName(),
    } == {
        "previewPlanAction",
        "previewReversibleAction",
        "previewUndoAction",
        "approvePlanAction",
        "applyPlanAction",
        "cancelPlanAction",
        "refreshHistoryAction",
        "exportReportAction",
    }
    assert panel.preview_button.width() > 140
    assert panel.reversible_button.width() > 140
    assert panel.undo_button.width() > 140
    assert panel.approve_button.width() > 140
    assert panel.apply_button.width() > 140
    assert panel.cancel_plan_button.width() > 140
    panel.view_tabs.setCurrentWidget(panel.history_tab)
    application.processEvents()
    assert panel.history_table.isColumnHidden(4)
    assert panel.history_table.isColumnHidden(5)
    assert panel.history_table.horizontalScrollBar().maximum() == 0
    assert not page.findChildren(QScrollArea)
    page.deleteLater()
    application.processEvents()


def test_reversible_apply_and_undo_run_off_gui_thread(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, database = _page(tmp_path)
    panel = page.history_panel
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    panel.reversible_button.click()
    source_id = panel.current_record.operation_id
    panel.approve_button.click()
    assert panel.current_record.status == OperationStatus.APPROVED
    assert panel.apply_button.isEnabled()

    panel._start_execution(source_id)
    assert panel.is_busy()
    assert not panel.reversible_button.isEnabled()
    assert panel.cancel_plan_button.isEnabled()
    assert panel.cancel_plan_button.text() == "Cancel Operation"
    _wait_until(lambda: not panel.is_busy())

    applied = panel.service.get_operation(source_id)
    assert applied.status == OperationStatus.APPLIED
    assert panel.undo_button.isEnabled()
    assert database.list_collections()
    assert page.backup_table.rowCount() == 1

    panel.undo_button.click()
    undo_id = panel.current_record.operation_id
    assert panel.current_record.source_operation_id == source_id
    panel.approve_button.click()
    panel._start_execution(undo_id)
    _wait_until(lambda: not panel.is_busy())

    assert panel.service.get_operation(source_id).status == (
        OperationStatus.UNDONE
    )
    assert panel.service.get_operation(undo_id).status == (
        OperationStatus.APPLIED
    )
    assert database.list_collections() == []
    assert page.backup_table.rowCount() == 2
    page.deleteLater()
    application.processEvents()

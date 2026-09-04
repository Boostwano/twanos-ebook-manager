"""RC6.7 Protection Centre and worker lifecycle tests."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic, sleep

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea

from database.database import DatabaseManager
from preferences import PreferencesStore
from services.protection_service import BackupStatus, ProtectionService
from ui.protection_page import ProtectionPage
from ui.sidebar import NAVIGATION_PAGE_IDS, ResponsiveSidebar


def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = monotonic() + timeout
    application = QApplication.instance()
    while monotonic() < deadline:
        application.processEvents()
        if predicate():
            return
        sleep(0.01)
    raise AssertionError("Timed out waiting for backup worker")


def _page(
    tmp_path: Path,
) -> tuple[ProtectionPage, PreferencesStore]:
    database_path = tmp_path / "live" / "library.db"
    factory = lambda: ProtectionService(
        DatabaseManager(database_path)
    )
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    return ProtectionPage(preferences, factory), preferences


def test_protection_page_exposes_clear_bounded_actions(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, _preferences = _page(tmp_path)
    page.resize(690, 600)
    page.show()
    application.processEvents()

    assert {
        page.browse_button.objectName(),
            page.save_policy_button.objectName(),
            page.create_button.objectName(),
            page.verify_button.objectName(),
            page.restore_button.objectName(),
            page.cleanup_button.objectName(),
            page.cancel_button.objectName(),
        } == {
            "browseBackupAction",
            "saveBackupPolicyAction",
            "createBackupAction",
            "verifyBackupAction",
            "restoreBackupAction",
            "reviewOldBackupsAction",
            "cancelBackupAction",
        }
    assert not page.verify_button.isEnabled()
    assert not page.restore_button.isEnabled()
    assert not page.cancel_button.isEnabled()
    assert "protection" not in NAVIGATION_PAGE_IDS
    assert page.page_tabs.currentWidget() is page.backup_tab
    assert page.page_tabs.tabText(0) == "Backups && Restore"
    assert page.page_tabs.tabText(1) == "Activity && Undo"
    page.deleteLater()
    application.processEvents()


def test_policy_saves_and_survives_page_recreation(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, preferences = _page(tmp_path)
    backup_folder = tmp_path / "Chosen Backups"
    page.backup_folder_edit.setText(str(backup_folder))
    page.retention_days.setValue(45)

    page._save_policy()
    reloaded = preferences.load_protection_preferences()

    assert reloaded.backup_folder == str(backup_folder)
    assert reloaded.retention_days == 45
    assert "reviewed before removal" in page.status_label.text()
    page.deleteLater()
    application.processEvents()


def test_page_creates_verifies_and_repeats_backups_off_gui_thread(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, _preferences = _page(tmp_path)
    backup_folder = tmp_path / "Backups"
    page.backup_folder_edit.setText(str(backup_folder))
    page.retention_days.setValue(0)

    for expected_rows in (1, 2):
        page._create_backup()
        assert page.is_busy()
        assert not page.create_button.isEnabled()
        assert page.cancel_button.isEnabled()
        _wait_until(lambda: not page.is_busy())
        assert page.backup_table.rowCount() == expected_rows
        assert page.create_button.isEnabled()
        assert not page.cancel_button.isEnabled()

    page.backup_table.selectRow(0)
    assert page.verify_button.isEnabled()
    page._verify_selected_backup()
    _wait_until(lambda: not page.is_busy())

    assert "passed verification" in page.status_label.text()
    assert page.backup_table.item(0, 2).text() == "Verified"
    records = page.presentation_service.list_backups(
        page.presentation_service.build_policy(backup_folder, 0)
    )
    assert all(
        record.status == BackupStatus.VERIFIED for record in records
    )
    page.deleteLater()
    application.processEvents()


def test_restore_is_one_plain_confirmation_and_runs_off_gui_thread(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, _preferences = _page(tmp_path)
    database = page.presentation_service.database
    database.create_collection("Saved")
    backup_folder = tmp_path / "Backups"
    page.backup_folder_edit.setText(str(backup_folder))
    page.retention_days.setValue(0)
    page._save_policy()
    policy = page.presentation_service.build_policy(backup_folder, 0)
    selected = page.presentation_service.create_verified_backup(policy)
    database.create_collection("Current")
    page.refresh_backups(selected.path)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    restored_signals: list[bool] = []
    page.catalogue_restored.connect(
        lambda: restored_signals.append(True)
    )

    page.restore_button.click()

    assert page.is_busy()
    assert not page.restore_button.isEnabled()
    _wait_until(lambda: not page.is_busy())
    assert restored_signals == [True]
    assert database.get_collection_by_name("Saved") is not None
    assert database.get_collection_by_name("Current") is None
    assert "Catalogue restored" in page.status_label.text()
    assert page.page_tabs.currentWidget() is page.backup_tab
    page.deleteLater()
    application.processEvents()


def test_old_backup_review_confirms_summary_then_cleans_exact_pair(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, _preferences = _page(tmp_path)
    backup_folder = tmp_path / "Backups"
    page.backup_folder_edit.setText(str(backup_folder))
    page.retention_days.setValue(30)
    page._save_policy()
    policy = page.presentation_service.build_policy(backup_folder, 30)
    expired = page.presentation_service.create_verified_backup(policy)
    manifest = json.loads(
        expired.manifest_path.read_text(encoding="utf-8")
    )
    manifest["created_at"] = (
        datetime.now(timezone.utc) - timedelta(days=60)
    ).isoformat()
    expired.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    prompts: list[str] = []

    def approve_cleanup(_parent, _title, message, *_args, **_kwargs):
        prompts.append(message)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", approve_cleanup)

    page.cleanup_button.click()

    _wait_until(
        lambda: not expired.path.exists() and not page.is_busy()
    )
    assert len(prompts) == 1
    assert "1 verified old backup" in prompts[0]
    assert not expired.manifest_path.exists()
    assert "reviewed old backups were removed" in (
        page.status_label.text()
    )
    page.deleteLater()
    application.processEvents()


def test_sidebar_keeps_protection_card_visible_at_minimum_height(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    sidebar = ResponsiveSidebar()
    sidebar.apply_responsive_size(900, 600)
    sidebar.setFixedHeight(600)
    sidebar.show()
    application.processEvents()

    assert "protection" not in sidebar.page_ids
    assert not sidebar.navigation.verticalScrollBar().isVisible()
    assert sidebar.protection_panel.isVisible()
    page_requests: list[str] = []
    sidebar.page_requested.connect(page_requests.append)
    QTest.mouseClick(
        sidebar.protection_panel,
        Qt.MouseButton.LeftButton,
    )
    assert page_requests == ["protection"]
    assert not sidebar.select_page("protection")
    sidebar.deleteLater()
    application.processEvents()


def test_compact_protection_controls_reflow_without_right_clipping(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    page, _preferences = _page(tmp_path)
    page.resize(690, 600)
    page.show()
    application.processEvents()

    assert page.save_policy_button.width() > 150
    assert page.create_button.width() > 150
    assert page.verify_button.width() > 150
    assert page.restore_button.width() > 150
    assert page.cleanup_button.width() > 150
    assert page.cancel_button.width() > 70
    assert page.browse_button.geometry().right() <= (
        page.folder_controls.width()
    )
    assert page.page_tabs.geometry().right() <= page.width()
    assert page.page_tabs.geometry().bottom() <= page.height()
    assert page.backup_table.horizontalScrollBar().maximum() == 0
    assert not page.findChildren(QScrollArea)
    page.deleteLater()
    application.processEvents()

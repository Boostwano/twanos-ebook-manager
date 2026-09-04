"""RC6.7 Milestone 5 Scan Apply protection integration tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from time import monotonic, sleep

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea

from database.database import DatabaseManager
from metadata.provider_manager import ProviderManager
from preferences import (
    PreferencesStore,
    ProtectionMode,
    ProtectionPreferences,
)
from services.protection_models import OperationStatus, Reversibility
from services.protection_service import BackupStatus, ProtectionService
from services.scan_service import ScanApplyStatus, ScanService
from ui.scan_page import ScanPage


def _service(database: DatabaseManager) -> ScanService:
    return ScanService(database, ProviderManager())


def _preview_new_book(
    tmp_path: Path,
    *,
    database_name: str,
) -> tuple[DatabaseManager, ScanService, object]:
    folder = tmp_path / database_name
    folder.mkdir()
    (folder / "New Book.epub").write_bytes(b"new book")
    database = DatabaseManager(tmp_path / f"{database_name}.db")
    service = _service(database)
    source = service.add_source(folder, display_name=database_name)
    preview = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )
    return database, service, preview


def test_scan_history_link_migrates_additively(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-scan.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE libraries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_path TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                last_scanned_at TEXT
            );
            CREATE TABLE books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                library_id INTEGER NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                file_name TEXT NOT NULL,
                title TEXT,
                author TEXT,
                isbn TEXT,
                file_format TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_modified_at TEXT,
                discovered_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                metadata_status TEXT NOT NULL DEFAULT 'pending',
                review_required INTEGER NOT NULL DEFAULT 0,
                is_missing INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE scan_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                library_id INTEGER NOT NULL,
                scan_token TEXT NOT NULL UNIQUE,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                discovered_count INTEGER NOT NULL DEFAULT 0,
                new_count INTEGER NOT NULL DEFAULT 0,
                changed_count INTEGER NOT NULL DEFAULT 0,
                missing_count INTEGER NOT NULL DEFAULT 0,
                unchanged_count INTEGER NOT NULL DEFAULT 0,
                unreadable_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                applied_new_count INTEGER NOT NULL DEFAULT 0,
                applied_changed_count INTEGER NOT NULL DEFAULT 0,
                applied_missing_count INTEGER NOT NULL DEFAULT 0,
                refreshed_count INTEGER NOT NULL DEFAULT 0,
                safely_skipped_count INTEGER NOT NULL DEFAULT 0,
                error_summary TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO libraries (
                folder_path, created_at
            ) VALUES ('C:/Books', '2026-07-01T00:00:00+00:00');
            INSERT INTO scan_history (
                library_id, scan_token, started_at, finished_at, status,
                duration_ms
            ) VALUES (
                1, 'legacy-token', '2026-07-01T00:00:00+00:00',
                '2026-07-01T00:00:01+00:00', 'applied', 1000
            );
            """
        )

    database = DatabaseManager(database_path)
    row = database.list_scan_history(1)[0]

    assert row["scan_token"] == "legacy-token"
    assert row["protection_operation_id"] is None
    with database.connection() as connection:
        columns = {
            column["name"]
            for column in connection.execute("PRAGMA table_info(scan_history)")
        }
    assert "protection_operation_id" in columns


def test_scan_apply_links_both_histories_and_verified_backup_after_restart(
    tmp_path: Path,
) -> None:
    database, service, preview = _preview_new_book(
        tmp_path,
        database_name="Success",
    )
    backup_folder = tmp_path / "Safety Backups"

    result = service.apply_analysis(
        preview,
        is_cancelled=lambda: False,
        backup_folder=backup_folder,
    )

    assert result.status == ScanApplyStatus.APPLIED
    assert result.protection_operation_id is not None
    scan_row = database.list_scan_history(
        preview.source.source_id
    )[0]
    assert scan_row["protection_operation_id"] == (
        result.protection_operation_id
    )

    recreated = ProtectionService(DatabaseManager(database.database_path))
    operation = recreated.get_operation(result.protection_operation_id)
    assert operation.status == OperationStatus.APPLIED
    assert operation.plan.operation_type == "scan_apply"
    assert operation.plan.component == "scan"
    assert operation.plan.reversibility == Reversibility.PARTIAL
    assert operation.plan.affected_book_count == 1
    assert operation.backup_identity
    assert recreated.inspect_backup(
        Path(operation.backup_identity),
        verify_contents=True,
    ).status == BackupStatus.VERIFIED
    assert not recreated.can_preview_undo(operation.operation_id)
    scan_operations = [
        record
        for record in recreated.list_operation_history()
        if record.plan.operation_type == "scan_apply"
    ]
    assert [record.operation_id for record in scan_operations] == [
        result.protection_operation_id
    ]


def test_scan_apply_cancellation_updates_both_histories_without_backup(
    tmp_path: Path,
) -> None:
    database, service, preview = _preview_new_book(
        tmp_path,
        database_name="Cancelled",
    )
    backup_folder = tmp_path / "Unused Backups"

    result = service.apply_analysis(
        preview,
        is_cancelled=lambda: True,
        backup_folder=backup_folder,
    )

    assert result.status == ScanApplyStatus.CANCELLED
    assert database.count_books(include_missing=True) == 0
    scan_row = database.list_scan_history(
        preview.source.source_id
    )[0]
    assert scan_row["status"] == "cancelled"
    assert scan_row["protection_operation_id"] == (
        result.protection_operation_id
    )
    operation = ProtectionService(database).get_operation(
        result.protection_operation_id
    )
    assert operation.status == OperationStatus.CANCELLED
    assert not operation.backup_identity
    assert not backup_folder.exists()


def test_scan_apply_failure_keeps_catalogue_atomic_and_records_recovery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, service, preview = _preview_new_book(
        tmp_path,
        database_name="Failed",
    )
    backup_folder = tmp_path / "Failure Backups"

    def fail_apply(**_kwargs):
        raise RuntimeError("forced scan transaction failure")

    monkeypatch.setattr(database, "apply_scan_preview", fail_apply)

    with pytest.raises(
        RuntimeError,
        match="forced scan transaction failure",
    ):
        service.apply_analysis(
            preview,
            is_cancelled=lambda: False,
            backup_folder=backup_folder,
        )

    assert database.count_books(include_missing=True) == 0
    scan_row = database.list_scan_history(
        preview.source.source_id
    )[0]
    assert scan_row["status"] == "failed"
    assert scan_row["protection_operation_id"] is not None
    operation = ProtectionService(database).get_operation(
        int(scan_row["protection_operation_id"])
    )
    assert operation.status == OperationStatus.FAILED
    assert "forced scan transaction failure" in operation.error_summary
    assert "no partial scan update" in operation.rollback_outcome
    assert Path(operation.backup_identity).is_file()


def test_stale_scan_source_records_one_linked_failure_before_backup(
    tmp_path: Path,
) -> None:
    database, service, preview = _preview_new_book(
        tmp_path,
        database_name="Stale",
    )
    service.update_source(
        preview.source.source_id,
        display_name="Stale",
        include_subfolders=False,
        include_patterns="*.epub",
        exclude_patterns=(),
    )
    backup_folder = tmp_path / "Stale Backups"

    with pytest.raises(ValueError, match="settings changed"):
        service.apply_analysis(
            preview,
            is_cancelled=lambda: False,
            backup_folder=backup_folder,
        )

    row = database.list_scan_history(preview.source.source_id)[0]
    operation = ProtectionService(database).get_operation(
        int(row["protection_operation_id"])
    )
    assert row["status"] == "failed"
    assert operation.status == OperationStatus.FAILED
    assert not operation.backup_identity
    assert not backup_folder.exists()


def test_read_only_blocks_scan_apply_before_plan_backup_or_mutation(
    tmp_path: Path,
) -> None:
    database, service, preview = _preview_new_book(
        tmp_path,
        database_name="Read Only",
    )
    backup_folder = tmp_path / "Read Only Backups"

    with pytest.raises(ValueError, match="Read-Only"):
        service.apply_analysis(
            preview,
            is_cancelled=lambda: False,
            backup_folder=backup_folder,
            protection_mode=ProtectionMode.READ_ONLY,
        )

    assert database.count_books(include_missing=True) == 0
    assert not backup_folder.exists()
    assert not [
        operation
        for operation in ProtectionService(database).list_operation_history()
        if operation.plan.operation_type == "scan_apply"
    ]


def test_scan_page_keeps_read_only_guidance_simple(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    database_path = tmp_path / "read-only-ui.db"
    factory = lambda: _service(DatabaseManager(database_path))
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "scan-preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    preferences.set_protection_mode(ProtectionMode.READ_ONLY)
    folder = tmp_path / "Read Only UI"
    folder.mkdir()
    (folder / "Book.epub").write_bytes(b"book")
    page = ScanPage(factory, preferences)
    source = page.source_service.add_source(
        folder,
        display_name="Read Only UI",
    )
    page.refresh_sources(source.source_id)
    page.current_analysis = page.source_service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )
    page._refresh_source_actions()

    assert not page.apply_button.isEnabled()
    assert "Standard" in page.apply_button.toolTip()

    page.set_protection_mode(ProtectionMode.STANDARD)

    assert page.apply_button.isEnabled()
    assert "safety backup" in page.apply_button.toolTip()
    page.deleteLater()
    application.processEvents()


def test_scan_page_applies_all_watched_folder_previews_sequentially(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    database_path = tmp_path / "apply-all.db"
    factory = lambda: _service(DatabaseManager(database_path))
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "apply-all.ini"),
            QSettings.Format.IniFormat,
        )
    )
    preferences.save_protection_preferences(
        ProtectionPreferences(
            backup_folder=str((tmp_path / "Backups").resolve()),
            retention_days=0,
        )
    )
    page = ScanPage(factory, preferences)
    sources = []
    for name in ("First", "Second"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / f"{name}.epub").write_bytes(name.encode("utf-8"))
        sources.append(
            page.source_service.add_source(folder, display_name=name)
        )
    page.refresh_sources(sources[0].source_id)

    page._start_all_scans()
    deadline = monotonic() + 5.0
    while page.is_scanning() and monotonic() < deadline:
        application.processEvents()
        sleep(0.01)

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    page._apply_preview()
    deadline = monotonic() + 8.0
    while page.is_scanning() and monotonic() < deadline:
        application.processEvents()
        sleep(0.01)

    database = DatabaseManager(database_path)
    assert not page.is_scanning()
    assert database.count_books() == 2
    assert all(
        database.list_scan_history(source.source_id)[0]["status"] == "applied"
        for source in sources
    )
    assert "Apply All complete" in page.status_label.text()
    assert page.current_analyses == ()
    page.deleteLater()
    application.processEvents()


def test_scan_tasks_fit_without_a_page_scrollbar(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    database_path = tmp_path / "responsive-scan.db"
    page = ScanPage(
        lambda: _service(DatabaseManager(database_path))
    )
    folder = tmp_path / "Responsive Source With A Long Name"
    folder.mkdir()
    source = page.source_service.add_source(
        folder,
        display_name="Responsive Source With A Long Name",
    )
    page.refresh_sources(source.source_id)
    page.resize(690, 600)
    page.show()
    application.processEvents()

    assert page.findChildren(QScrollArea) == []
    assert page.scan_tabs.count() == 3
    assert [
        page.scan_tabs.tabText(index).replace("&&", "&")
        for index in range(page.scan_tabs.count())
    ] == ["Sources", "Preview & Apply", "History"]
    for tab in (
        page.sources_tab,
        page.preview_tab,
        page.history_tab,
    ):
        page.scan_tabs.setCurrentWidget(tab)
        application.processEvents()
        assert tab.height() <= page.scan_tabs.height()
        assert tab.width() <= page.scan_tabs.width()
    assert page.results_table.horizontalScrollBar().maximum() == 0
    assert page.history_table.horizontalScrollBar().maximum() == 0
    assert page.source_table.horizontalScrollBar().maximum() == 0

    page.deleteLater()
    application.processEvents()

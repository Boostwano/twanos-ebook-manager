"""RC6.7 additive persistent operation-history and report tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from database.database import DatabaseManager
from services.protection_models import (
    OperationStatus,
    PlanConfirmation,
    PlanValidationError,
)
from services.protection_service import (
    BackupCancelled,
    ProtectionService,
    ReportExportCancelled,
)


def _service(database_path: Path) -> ProtectionService:
    return ProtectionService(DatabaseManager(database_path))


def test_audit_schema_is_additive_and_preserves_existing_catalogue(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy.db"
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
            INSERT INTO libraries (
                folder_path, created_at
            ) VALUES ('C:/Books', '2026-07-01T00:00:00+00:00');
            INSERT INTO books (
                library_id, file_path, file_name, title, file_format,
                file_size, discovered_at, last_seen_at
            ) VALUES (
                1, 'C:/Books/Example.epub', 'Example.epub', 'Example',
                'EPUB', 100, '2026-07-01T00:00:00+00:00',
                '2026-07-01T00:00:00+00:00'
            );
            """
        )

    database = DatabaseManager(database_path)

    assert database.count_books() == 1
    with database.connection() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }
    assert "protection_operations" in tables
    assert "protection_operation_items" in tables


def test_plan_history_survives_service_recreation_with_items(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "library.db"
    service = _service(database_path)
    plan = service.build_safety_check_plan()

    created = service.record_change_plan(plan)
    recreated = _service(database_path)
    restored = recreated.get_operation(created.operation_id)
    history = recreated.list_operation_history()

    assert restored.plan == plan
    assert restored.status == OperationStatus.PLANNED
    assert len(restored.items) == 1
    assert restored.items[0].action == "record_audit_evidence"
    assert history[0].operation_id == created.operation_id


def test_duplicate_plan_token_and_repeated_approval_are_rejected(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "library.db")
    plan = service.build_safety_check_plan()
    record = service.record_change_plan(plan)

    with pytest.raises(sqlite3.IntegrityError):
        service.record_change_plan(plan)

    confirmation = PlanConfirmation(
        plan_token=plan.plan_token,
        approved=True,
        confirmer="user",
    )
    approved = service.approve_change_plan(
        record.operation_id,
        confirmation,
        current_basis_token=plan.basis_token,
    )

    assert approved.status == OperationStatus.APPROVED
    assert approved.confirmation == confirmation
    with pytest.raises(PlanValidationError, match="pending"):
        service.approve_change_plan(
            record.operation_id,
            confirmation,
            current_basis_token=plan.basis_token,
        )


def test_cancelled_plan_records_terminal_outcome_without_catalogue_change(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "library.db"
    database = DatabaseManager(database_path)
    database.create_collection("Existing")
    service = ProtectionService(database)
    record = service.record_change_plan(
        service.build_safety_check_plan()
    )
    before_count = database.count_books(include_missing=True)

    cancelled = service.cancel_change_plan(record.operation_id)

    assert cancelled.status == OperationStatus.CANCELLED
    assert cancelled.finished_at
    assert database.count_books(include_missing=True) == before_count
    assert [row["name"] for row in database.list_collections()] == [
        "Existing"
    ]
    with pytest.raises(ValueError, match="status changed"):
        service.cancel_change_plan(record.operation_id)


def test_report_is_readable_atomic_and_does_not_overwrite_by_default(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "library.db")
    record = service.record_change_plan(
        service.build_safety_check_plan()
    )
    record = service.cancel_change_plan(record.operation_id)
    report_path = tmp_path / "Reports" / "operation.md"
    report_path.parent.mkdir()

    exported = service.export_operation_report(
        record.operation_id,
        report_path,
    )
    text = exported.read_text(encoding="utf-8")

    assert "# Twano Operation Report" in text
    assert f"Operation ID: {record.operation_id}" in text
    assert "Status: cancelled" in text
    assert "Affected books: 0" in text
    assert "Intended database changes" in text
    assert "does not mean the changes were applied" in text
    with pytest.raises(FileExistsError):
        service.export_operation_report(
            record.operation_id,
            report_path,
        )


def test_cancelled_report_export_leaves_no_partial_file(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "library.db")
    record = service.record_change_plan(
        service.build_safety_check_plan()
    )
    report_path = tmp_path / "operation.md"

    with pytest.raises(ReportExportCancelled):
        service.export_operation_report(
            record.operation_id,
            report_path,
            is_cancelled=lambda: True,
        )

    assert not report_path.exists()
    assert not tuple(tmp_path.glob("*.partial"))


def test_backup_creation_records_applied_audit_and_backup_identity(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "library.db")
    backup_folder = tmp_path / "Backups"

    backup = service.create_verified_backup(
        service.build_policy(backup_folder, 0)
    )
    history = service.list_operation_history()
    record = service.get_operation(history[0].operation_id)

    assert record.plan.operation_type == "database_backup"
    assert record.status == OperationStatus.APPLIED
    assert record.backup_identity == str(backup.path)
    assert record.items[0].status == OperationStatus.APPLIED.value
    assert record.rollback_outcome.startswith("Not required")


def test_cancelled_backup_records_cleanup_evidence(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "library.db")
    backup_folder = tmp_path / "Backups"
    cancel_state = {"requested": False}

    def cancel_during_copy(percent: int, _message: str) -> None:
        if percent >= 5:
            cancel_state["requested"] = True

    with pytest.raises(BackupCancelled, match="cancel"):
        service.create_verified_backup(
            service.build_policy(backup_folder, 0),
            is_cancelled=lambda: cancel_state["requested"],
            on_progress=cancel_during_copy,
        )

    record = service.get_operation(
        service.list_operation_history()[0].operation_id
    )
    assert record.status == OperationStatus.CANCELLED
    assert "removed" in record.rollback_outcome
    assert not tuple(backup_folder.iterdir())

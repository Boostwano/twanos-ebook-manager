"""RC6.7 protected Restore and bounded retention-cleanup tests."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from database.database import DatabaseManager
from preferences import ProtectionMode
from services.protection_models import (
    OperationStatus,
    PlanConfirmation,
    PlanValidationError,
)
from services.protection_service import (
    BackupCancelled,
    BackupStatus,
    ProtectedExecutionError,
    ProtectionService,
)


def _service(database_path: Path) -> ProtectionService:
    return ProtectionService(DatabaseManager(database_path))


def _approve(service: ProtectionService, record):
    return service.approve_change_plan(
        record.operation_id,
        PlanConfirmation(
            plan_token=record.plan.plan_token,
            approved=True,
            confirmer="user",
        ),
        current_basis_token=service.current_basis_token(record),
    )


def test_restore_rechecks_backup_keeps_recovery_and_refreshes_history(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "live" / "library.db"
    service = _service(database_path)
    service.database.create_collection("Saved State")
    policy = service.build_policy(tmp_path / "Backups", 0)
    selected = service.create_verified_backup(policy)
    service.database.create_collection("Current State")
    approved = _approve(
        service,
        service.preview_restore_operation(selected.path),
    )

    restored = service.apply_approved_operation(
        approved.operation_id,
        policy,
        ProtectionMode.STANDARD,
    )

    assert restored.status == OperationStatus.APPLIED
    assert restored.plan.operation_type == "database_restore"
    assert service.database.get_collection_by_name("Saved State") is not None
    assert service.database.get_collection_by_name("Current State") is None
    recovery_path = Path(restored.backup_identity)
    assert recovery_path.is_file()
    assert recovery_path != selected.path
    assert service.verify_backup(recovery_path).status == BackupStatus.VERIFIED
    with sqlite3.connect(recovery_path) as recovery_database:
        names = {
            row[0]
            for row in recovery_database.execute(
                "SELECT name FROM collections"
            )
        }
    assert {"Saved State", "Current State"}.issubset(names)
    inverse = json.loads(restored.items[0].inverse_json)
    assert inverse["action"] == "restore_database"
    assert Path(inverse["backup_path"]) == recovery_path
    recreated = _service(database_path)
    assert recreated.get_operation(restored.operation_id).status == (
        OperationStatus.APPLIED
    )
    assert all(
        operation.status != OperationStatus.APPLYING
        for operation in recreated.list_operation_history()
    )


def test_restore_rejects_read_only_before_recovery_or_replacement(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "live" / "library.db")
    service.database.create_collection("Original")
    policy = service.build_policy(tmp_path / "Backups", 0)
    selected = service.create_verified_backup(policy)
    service.database.create_collection("Still Current")
    approved = _approve(
        service,
        service.preview_restore_operation(selected.path),
    )
    before = set(path.name for path in policy.folder.iterdir())

    with pytest.raises(PlanValidationError, match="Read-Only"):
        service.apply_approved_operation(
            approved.operation_id,
            policy,
            ProtectionMode.READ_ONLY,
        )

    assert set(path.name for path in policy.folder.iterdir()) == before
    assert service.database.get_collection_by_name("Still Current") is not None
    assert service.get_operation(approved.operation_id).status == (
        OperationStatus.APPROVED
    )


def test_restore_stops_if_selected_backup_changes_after_approval(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "live" / "library.db")
    service.database.create_collection("Original")
    policy = service.build_policy(tmp_path / "Backups", 0)
    selected = service.create_verified_backup(policy)
    service.database.create_collection("Current")
    approved = _approve(
        service,
        service.preview_restore_operation(selected.path),
    )
    with sqlite3.connect(selected.path) as backup:
        backup.execute(
            "INSERT INTO collections (name, created_at) VALUES (?, ?)",
            ("Changed Backup", datetime.now(timezone.utc).isoformat()),
        )
        backup.commit()

    with pytest.raises(
        (PlanValidationError, ProtectedExecutionError),
    ):
        service.apply_approved_operation(
            approved.operation_id,
            policy,
            ProtectionMode.STANDARD,
        )

    assert service.database.get_collection_by_name("Current") is not None
    assert len(service.list_backups(policy)) == 1


def test_restore_cancellation_before_replacement_keeps_approved_plan(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "live" / "library.db")
    service.database.create_collection("Current")
    policy = service.build_policy(tmp_path / "Backups", 0)
    selected = service.create_verified_backup(policy)
    approved = _approve(
        service,
        service.preview_restore_operation(selected.path),
    )

    with pytest.raises(BackupCancelled):
        service.apply_approved_operation(
            approved.operation_id,
            policy,
            ProtectionMode.STANDARD,
            is_cancelled=lambda: True,
        )

    assert service.database.get_collection_by_name("Current") is not None
    assert service.get_operation(approved.operation_id).status == (
        OperationStatus.APPROVED
    )


def test_restore_post_swap_failure_recovers_pre_restore_catalogue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _service(tmp_path / "live" / "library.db")
    service.database.create_collection("Saved")
    policy = service.build_policy(tmp_path / "Backups", 0)
    selected = service.create_verified_backup(policy)
    service.database.create_collection("Must Survive")
    approved = _approve(
        service,
        service.preview_restore_operation(selected.path),
    )
    monkeypatch.setattr(
        service,
        "_persist_completed_restore_operation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("forced post-swap failure")
        ),
    )

    with pytest.raises(ProtectedExecutionError, match="recovered"):
        service.apply_approved_operation(
            approved.operation_id,
            policy,
            ProtectionMode.STANDARD,
        )

    assert service.database.get_collection_by_name("Must Survive") is not None
    failed = service.get_operation(approved.operation_id)
    assert failed.status == OperationStatus.FAILED
    assert "recovered" in failed.rollback_outcome
    assert Path(failed.backup_identity).is_file()


def test_retention_review_deletes_only_expired_verified_owned_pairs(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "live" / "library.db")
    policy = service.build_policy(tmp_path / "Backups", 30)
    expired = service.create_verified_backup(policy)
    recent = service.create_verified_backup(policy)
    expired_manifest = json.loads(
        expired.manifest_path.read_text(encoding="utf-8")
    )
    now = datetime.now(timezone.utc)
    expired_manifest["created_at"] = (
        now - timedelta(days=60)
    ).isoformat()
    expired.manifest_path.write_text(
        json.dumps(expired_manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    unverified = (
        policy.folder
        / "Twano-library-20260101-000000-legacy.sqlite3"
    )
    service.database.backup_database(unverified)
    unrelated = policy.folder / "family-notes.txt"
    unrelated.write_text("keep me", encoding="utf-8")

    preview = service.preview_retention_cleanup(policy, now=now)

    assert preview.candidate_count == 1
    assert preview.operation is not None
    assert expired.path.name in (
        preview.operation.plan.file_changes[0].description
    )
    approved = _approve(service, preview.operation)
    applied = service.apply_approved_operation(
        approved.operation_id,
        policy,
        ProtectionMode.STANDARD,
    )

    assert applied.status == OperationStatus.APPLIED
    assert not expired.path.exists()
    assert not expired.manifest_path.exists()
    assert recent.path.exists()
    assert recent.manifest_path.exists()
    assert unverified.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep me"


def test_retention_stops_if_candidate_changes_after_review(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "live" / "library.db")
    policy = service.build_policy(tmp_path / "Backups", 30)
    expired = service.create_verified_backup(policy)
    manifest = json.loads(
        expired.manifest_path.read_text(encoding="utf-8")
    )
    now = datetime.now(timezone.utc)
    manifest["created_at"] = (now - timedelta(days=60)).isoformat()
    expired.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    preview = service.preview_retention_cleanup(policy, now=now)
    approved = _approve(service, preview.operation)
    with expired.path.open("ab") as stream:
        stream.write(b"changed")

    with pytest.raises(PlanValidationError, match="changed|stale"):
        service.apply_approved_operation(
            approved.operation_id,
            policy,
            ProtectionMode.STANDARD,
        )

    assert expired.path.exists()
    assert expired.manifest_path.exists()
    assert service.get_operation(approved.operation_id).status == (
        OperationStatus.APPROVED
    )


def test_retention_move_failure_returns_all_artifacts_and_records_rollback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _service(tmp_path / "live" / "library.db")
    policy = service.build_policy(tmp_path / "Backups", 30)
    expired = service.create_verified_backup(policy)
    manifest = json.loads(
        expired.manifest_path.read_text(encoding="utf-8")
    )
    now = datetime.now(timezone.utc)
    manifest["created_at"] = (now - timedelta(days=60)).isoformat()
    expired.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    preview = service.preview_retention_cleanup(policy, now=now)
    approved = _approve(service, preview.operation)
    real_replace = __import__("os").replace
    calls = {"count": 0}

    def fail_second_move(source, destination):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("forced manifest move failure")
        return real_replace(source, destination)

    monkeypatch.setattr(
        "services.protection_service.os.replace",
        fail_second_move,
    )

    with pytest.raises(ProtectedExecutionError, match="move"):
        service.apply_approved_operation(
            approved.operation_id,
            policy,
            ProtectionMode.STANDARD,
        )

    assert expired.path.exists()
    assert expired.manifest_path.exists()
    outcome = service.get_operation(approved.operation_id)
    assert outcome.status == OperationStatus.ROLLED_BACK
    assert "returned" in outcome.rollback_outcome
    assert not tuple(policy.folder.glob(".twano-retention-*"))

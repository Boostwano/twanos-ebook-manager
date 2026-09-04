"""RC6.7 protected executor and persistent Undo tests."""

from __future__ import annotations

import json
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
    ProtectedExecutionError,
    ProtectionService,
)


def _service(database_path: Path) -> ProtectionService:
    return ProtectionService(DatabaseManager(database_path))


def _approved_test_change(
    service: ProtectionService,
    collection_name: str = "Protected Test Collection",
):
    plan = service.build_reversible_test_plan(collection_name)
    record = service.record_change_plan(plan)
    confirmation = PlanConfirmation(
        plan_token=plan.plan_token,
        approved=True,
        confirmer="user",
    )
    return service.approve_change_plan(
        record.operation_id,
        confirmation,
        current_basis_token=service.current_basis_token(record),
    )


def _apply(
    service: ProtectionService,
    operation_id: int,
    backup_folder: Path,
):
    return service.apply_approved_operation(
        operation_id,
        service.build_policy(backup_folder, 0),
        ProtectionMode.STANDARD,
    )


def test_protected_apply_requires_backup_and_stores_validated_inverse(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "library.db")
    approved = _approved_test_change(service)

    applied = _apply(service, approved.operation_id, tmp_path / "Backups")

    assert applied.status == OperationStatus.APPLIED
    assert Path(applied.backup_identity).is_file()
    assert service.verify_backup(applied.backup_identity).status.value == (
        "verified"
    )
    collection = service.database.get_collection_by_name(
        "Protected Test Collection"
    )
    assert collection is not None
    inverse = json.loads(applied.items[0].inverse_json)
    assert inverse == {
        "action": "delete_collection",
        "collection_id": int(collection["id"]),
        "collection_name": "Protected Test Collection",
        "schema_version": 1,
    }
    assert applied.rollback_outcome.startswith("Not required")


def test_read_only_mode_rejects_apply_before_backup_or_mutation(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "library.db")
    approved = _approved_test_change(service)
    backup_folder = tmp_path / "Backups"

    with pytest.raises(PlanValidationError, match="Read-Only"):
        service.apply_approved_operation(
            approved.operation_id,
            service.build_policy(backup_folder, 0),
            ProtectionMode.READ_ONLY,
        )

    assert service.get_operation(approved.operation_id).status == (
        OperationStatus.APPROVED
    )
    assert service.database.get_collection_by_name(
        "Protected Test Collection"
    ) is None
    assert not backup_folder.exists()


def test_approved_non_allowlisted_plan_has_no_executor(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "library.db")
    plan = service.build_safety_check_plan()
    record = service.record_change_plan(plan)
    approved = service.approve_change_plan(
        record.operation_id,
        PlanConfirmation(
            plan_token=plan.plan_token,
            approved=True,
            confirmer="user",
        ),
        current_basis_token=service.current_basis_token(record),
    )
    backup_folder = tmp_path / "Backups"

    with pytest.raises(PlanValidationError, match="no protected executor"):
        service.apply_approved_operation(
            approved.operation_id,
            service.build_policy(backup_folder, 0),
            ProtectionMode.STANDARD,
        )

    assert service.get_operation(approved.operation_id).status == (
        OperationStatus.APPROVED
    )
    assert not backup_folder.exists()


def test_stale_collection_basis_is_rejected_before_approval(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "library.db")
    plan = service.build_reversible_test_plan("Stale Collection")
    record = service.record_change_plan(plan)
    service.database.create_collection("Stale Collection")
    confirmation = PlanConfirmation(
        plan_token=plan.plan_token,
        approved=True,
        confirmer="user",
    )

    with pytest.raises(PlanValidationError, match="basis changed"):
        service.approve_change_plan(
            record.operation_id,
            confirmation,
            current_basis_token=service.current_basis_token(record),
        )

    assert service.get_operation(record.operation_id).status == (
        OperationStatus.PLANNED
    )


def test_failed_executor_rolls_back_and_records_recovery_evidence(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "library.db")
    approved = _approved_test_change(service, "Rollback Collection")
    with service.database.connection() as connection:
        connection.execute(
            f"""
            CREATE TRIGGER force_inverse_failure
            BEFORE UPDATE OF inverse_json
            ON protection_operation_items
            WHEN NEW.operation_id = {approved.operation_id}
            BEGIN
                SELECT RAISE(ABORT, 'forced inverse failure');
            END;
            """
        )

    with pytest.raises(ProtectedExecutionError, match="rolled back"):
        _apply(service, approved.operation_id, tmp_path / "Backups")

    failed = service.get_operation(approved.operation_id)
    assert failed.status == OperationStatus.FAILED
    assert failed.backup_identity
    assert "forced inverse failure" in failed.error_summary
    assert "rolled back" in failed.rollback_outcome
    assert service.database.get_collection_by_name(
        "Rollback Collection"
    ) is None


def test_cancel_before_backup_keeps_approved_plan_retryable(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "library.db")
    approved = _approved_test_change(service, "Cancelled Collection")

    with pytest.raises(BackupCancelled):
        service.apply_approved_operation(
            approved.operation_id,
            service.build_policy(tmp_path / "Backups", 0),
            ProtectionMode.STANDARD,
            is_cancelled=lambda: True,
        )

    assert service.get_operation(approved.operation_id).status == (
        OperationStatus.APPROVED
    )
    assert service.database.get_collection_by_name(
        "Cancelled Collection"
    ) is None


def test_undo_survives_recreation_and_keeps_both_audit_records(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "library.db"
    service = _service(database_path)
    applied = _apply(
        service,
        _approved_test_change(service, "Persistent Undo").operation_id,
        tmp_path / "Backups",
    )

    recreated = _service(database_path)
    undo = recreated.preview_undo_operation(applied.operation_id)
    confirmation = PlanConfirmation(
        plan_token=undo.plan.plan_token,
        approved=True,
        confirmer="user",
    )
    undo = recreated.approve_change_plan(
        undo.operation_id,
        confirmation,
        current_basis_token=recreated.current_basis_token(undo),
    )
    undone = _apply(
        recreated,
        undo.operation_id,
        tmp_path / "Backups",
    )

    source = recreated.get_operation(applied.operation_id)
    assert source.status == OperationStatus.UNDONE
    assert source.items[0].status == OperationStatus.UNDONE.value
    assert undone.status == OperationStatus.APPLIED
    assert undone.source_operation_id == source.operation_id
    assert Path(undone.backup_identity).is_file()
    assert recreated.database.get_collection_by_name(
        "Persistent Undo"
    ) is None
    assert not recreated.can_preview_undo(source.operation_id)
    assert recreated.get_operation(undone.operation_id).plan.operation_type == (
        "undo_collection_create"
    )


def test_undo_basis_rejects_collection_changed_after_preview(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path / "library.db")
    applied = _apply(
        service,
        _approved_test_change(service, "Changing Undo").operation_id,
        tmp_path / "Backups",
    )
    undo = service.preview_undo_operation(applied.operation_id)
    collection = service.database.get_collection_by_name("Changing Undo")
    with service.database.connection() as connection:
        connection.execute(
            "UPDATE collections SET name = ? WHERE id = ?",
            ("Changed After Preview", int(collection["id"])),
        )

    with pytest.raises(PlanValidationError, match="stale"):
        service.current_basis_token(undo)
    assert service.get_operation(applied.operation_id).status == (
        OperationStatus.APPLIED
    )

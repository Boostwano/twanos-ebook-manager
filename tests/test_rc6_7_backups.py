"""RC6.7 verified online database backup tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from database.database import DatabaseManager
from services.protection_service import (
    BackupCancelled,
    BackupStatus,
    ProtectionService,
)


def _service(tmp_path: Path) -> tuple[ProtectionService, Path]:
    database_path = tmp_path / "live" / "library.db"
    database = DatabaseManager(database_path)
    database.create_collection("Before Backup")
    return ProtectionService(database), tmp_path / "Backups"


def test_online_backup_is_consistent_and_has_verification_manifest(
    tmp_path: Path,
) -> None:
    service, backup_folder = _service(tmp_path)
    policy = service.build_policy(backup_folder, 0)
    open_source = sqlite3.connect(service.live_database_path)
    open_source.execute(
        "INSERT INTO collections (name, created_at) VALUES (?, ?)",
        ("Committed While Open", "2026-07-28T00:00:00+00:00"),
    )
    open_source.commit()

    record = service.create_verified_backup(policy)

    open_source.close()
    assert record.status == BackupStatus.VERIFIED
    assert record.path.is_file()
    assert record.manifest_path.is_file()
    with sqlite3.connect(record.path) as backup:
        names = {
            row[0]
            for row in backup.execute(
                "SELECT name FROM collections ORDER BY name"
            )
        }
    assert names == {"Before Backup", "Committed While Open"}
    manifest = json.loads(
        record.manifest_path.read_text(encoding="utf-8")
    )
    assert manifest["backup_file"] == record.path.name
    assert manifest["size_bytes"] == record.path.stat().st_size
    assert manifest["sqlite_integrity_check"] == "ok"
    assert manifest["sha256"] == hashlib.sha256(
        record.path.read_bytes()
    ).hexdigest()


def test_repeated_backups_are_unique_and_list_newest_first(
    tmp_path: Path,
) -> None:
    service, backup_folder = _service(tmp_path)
    policy = service.build_policy(backup_folder, 30)

    first = service.create_verified_backup(policy)
    second = service.create_verified_backup(policy)
    records = service.list_backups(policy)

    assert first.path != second.path
    assert {record.path for record in records} == {
        first.path,
        second.path,
    }
    assert all(
        record.status == BackupStatus.VERIFIED for record in records
    )


def test_full_verification_detects_database_modified_after_creation(
    tmp_path: Path,
) -> None:
    service, backup_folder = _service(tmp_path)
    record = service.create_verified_backup(
        service.build_policy(backup_folder, 0)
    )
    with sqlite3.connect(record.path) as backup:
        backup.execute(
            "INSERT INTO collections (name, created_at) VALUES (?, ?)",
            ("Changed Backup", "2026-07-28T00:00:00+00:00"),
        )
        backup.commit()

    result = service.verify_backup(record.path)

    assert result.status == BackupStatus.MODIFIED
    assert "no longer matches" in result.message


def test_verification_distinguishes_corrupt_and_legacy_files(
    tmp_path: Path,
) -> None:
    service, backup_folder = _service(tmp_path)
    policy = service.build_policy(backup_folder, 0)
    corrupt = (
        backup_folder
        / "Twano-library-20260728-100000-corrupt.sqlite3"
    )
    legacy = (
        backup_folder
        / "Twano-library-20260728-100001-legacy.sqlite3"
    )
    backup_folder.mkdir()
    corrupt.write_bytes(b"not a sqlite database")
    service.database.backup_database(legacy)

    corrupt_result = service.verify_backup(corrupt)
    legacy_result = service.verify_backup(legacy)
    listed = {record.path: record for record in service.list_backups(policy)}

    assert corrupt_result.status == BackupStatus.INVALID
    assert legacy_result.status == BackupStatus.UNVERIFIED
    assert listed[corrupt].status == BackupStatus.UNVERIFIED
    assert listed[legacy].status == BackupStatus.UNVERIFIED


def test_cancelled_backup_leaves_no_final_or_partial_artifacts(
    tmp_path: Path,
) -> None:
    service, backup_folder = _service(tmp_path)
    policy = service.build_policy(backup_folder, 0)

    with pytest.raises(BackupCancelled):
        service.create_verified_backup(
            policy,
            is_cancelled=lambda: True,
        )

    assert not backup_folder.exists()


def test_cancellation_during_copy_removes_partial_artifacts(
    tmp_path: Path,
) -> None:
    service, backup_folder = _service(tmp_path)
    policy = service.build_policy(backup_folder, 0)
    cancel_state = {"requested": False}

    def request_cancel(percent: int, _message: str) -> None:
        if percent >= 5:
            cancel_state["requested"] = True

    with pytest.raises(BackupCancelled):
        service.create_verified_backup(
            policy,
            is_cancelled=lambda: cancel_state["requested"],
            on_progress=request_cancel,
        )

    assert backup_folder.is_dir()
    assert tuple(backup_folder.iterdir()) == ()


def test_failure_after_partial_copy_is_cleaned_up(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, backup_folder = _service(tmp_path)
    policy = service.build_policy(backup_folder, 0)

    def fail_after_writing(destination, **_kwargs):
        Path(destination).write_bytes(b"partial")
        raise OSError("simulated copy failure")

    monkeypatch.setattr(
        service.database,
        "backup_database",
        fail_after_writing,
    )

    with pytest.raises(OSError, match="simulated"):
        service.create_verified_backup(policy)

    assert tuple(backup_folder.iterdir()) == ()


def test_policy_requires_absolute_location_and_storage_aware_age(
    tmp_path: Path,
) -> None:
    service, _backup_folder = _service(tmp_path)

    assert service.build_policy(tmp_path / "Backups", 0).retention_days == 0
    assert (
        service.build_policy(tmp_path / "Backups", 36500).retention_days
        == 36500
    )
    with pytest.raises(ValueError, match="absolute"):
        service.build_policy("relative/backups", 0)
    with pytest.raises(ValueError, match="between"):
        service.build_policy(tmp_path / "Backups", 36501)

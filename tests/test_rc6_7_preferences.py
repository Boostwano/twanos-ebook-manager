"""RC6.7 backup-policy persistence and migration tests."""

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from preferences import PreferencesStore, ProtectionPreferences


def _store(path: Path) -> PreferencesStore:
    return PreferencesStore(
        QSettings(str(path), QSettings.Format.IniFormat)
    )


def test_protection_preferences_round_trip_and_keep_all(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "preferences.ini"
    backup_folder = tmp_path / "Backups"
    store = _store(settings_path)

    store.save_protection_preferences(
        ProtectionPreferences(
            backup_folder=str(backup_folder),
            retention_days=0,
        )
    )
    store.sync()

    reloaded = _store(settings_path).load_protection_preferences()

    assert reloaded == ProtectionPreferences(
        backup_folder=str(backup_folder),
        retention_days=0,
    )


def test_invalid_protection_preferences_migrate_to_safe_defaults(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "preferences.ini"
    settings = QSettings(
        str(settings_path),
        QSettings.Format.IniFormat,
    )
    settings.setValue("protection/backup_folder", "relative/backups")
    settings.setValue("protection/retention_days", -30)
    settings.sync()

    preferences = _store(settings_path).load_protection_preferences()

    assert preferences == ProtectionPreferences()
    repaired = QSettings(
        str(settings_path),
        QSettings.Format.IniFormat,
    )
    assert repaired.value("protection/backup_folder") == ""
    assert int(repaired.value("protection/retention_days")) == 0


@pytest.mark.parametrize("retention_days", (-1, 36501, "invalid"))
def test_invalid_saved_retention_is_rejected(
    tmp_path: Path,
    retention_days,
) -> None:
    store = _store(tmp_path / "preferences.ini")

    with pytest.raises(ValueError, match="between 0 and 36500"):
        store.save_protection_preferences(
            ProtectionPreferences(
                backup_folder=str(tmp_path / "Backups"),
                retention_days=retention_days,
            )
        )


def test_relative_saved_backup_folder_is_rejected(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "preferences.ini")

    with pytest.raises(ValueError, match="absolute"):
        store.save_protection_preferences(
            ProtectionPreferences(
                backup_folder="relative/backups",
                retention_days=0,
            )
        )

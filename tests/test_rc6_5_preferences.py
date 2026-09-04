"""RC6.5 validated Library preference tests."""

from pathlib import Path

from PySide6.QtCore import QSettings

from preferences import (
    LibraryDensity,
    LibraryPreferences,
    LibrarySortDirection,
    LibrarySortField,
    LibraryViewMode,
    PreferencesStore,
)


def _store(tmp_path: Path) -> tuple[PreferencesStore, QSettings]:
    settings = QSettings(
        str(tmp_path / "settings.ini"),
        QSettings.Format.IniFormat,
    )
    settings.clear()
    return PreferencesStore(settings), settings


def test_library_preferences_round_trip(tmp_path: Path) -> None:
    store, _settings = _store(tmp_path)
    expected = LibraryPreferences(
        view_mode=LibraryViewMode.LIST,
        density=LibraryDensity.SPACIOUS,
        sort_field=LibrarySortField.SERIES,
        sort_direction=LibrarySortDirection.DESCENDING,
        details_visible=False,
    )

    store.save_library_preferences(expected)
    store.sync()

    assert store.load_library_preferences() == expected


def test_invalid_library_preferences_fall_back_and_migrate(
    tmp_path: Path,
) -> None:
    store, settings = _store(tmp_path)
    settings.setValue("library/view_mode", "shelf")
    settings.setValue("library/density", "huge")
    settings.setValue("library/sort_field", "DROP TABLE")
    settings.setValue("library/sort_direction", "random")
    settings.setValue("library/details_visible", "false")

    loaded = store.load_library_preferences()

    assert loaded == LibraryPreferences(details_visible=False)
    assert settings.value("library/view_mode") == "grid"
    assert settings.value("library/density") == "comfortable"
    assert settings.value("library/sort_field") == "title"
    assert settings.value("library/sort_direction") == "ascending"

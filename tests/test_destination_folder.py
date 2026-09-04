"""A configurable global destination folder for organised and deleted books."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox
import pytest

from core.scanner import BookFile
from database.database import DatabaseManager
from main_window import MainWindow
from preferences import (
    OrganizationPreferences,
    PreferencesStore,
    ProtectionMode,
)
from services.dashboard_service import DashboardService
from services.library_service import DELETED_FOLDER_NAME, LibraryService
from services.protection_models import PlanConfirmation
from services.protection_service import ProtectionService
from services.scan_service import ScanService
from ui.settings import SettingsPage


def _book(path: Path) -> BookFile:
    return BookFile(
        name=path.stem,
        extension=path.suffix.removeprefix(".").upper(),
        size_bytes=path.stat().st_size,
        path=path,
    )


def _store(tmp_path: Path) -> PreferencesStore:
    settings = QSettings(
        str(tmp_path / "preferences.ini"),
        QSettings.Format.IniFormat,
    )
    return PreferencesStore(settings)


def test_organization_preferences_round_trip_and_reject_relative_paths(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    assert store.load_organization_preferences() == OrganizationPreferences()

    destination = tmp_path / "Destination"
    store.save_organization_preferences(
        OrganizationPreferences(
            destination_folder=str(destination),
            destination_prompt_shown=True,
        )
    )
    reloaded = store.load_organization_preferences()
    assert reloaded.destination_folder == str(destination)
    assert reloaded.destination_prompt_shown is True

    with pytest.raises(ValueError):
        store.save_organization_preferences(
            OrganizationPreferences(destination_folder="relative/path")
        )


def test_metadata_apply_organises_into_configured_destination_and_relinks_library(
    tmp_path: Path,
) -> None:
    watched = tmp_path / "Watched"
    watched.mkdir()
    destination = tmp_path / "Destination"
    source = watched / "Some Book.epub"
    source.write_bytes(b"data")

    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(watched, [_book(source)])
    book_id = int(database.get_books()[0]["id"])
    before_library_id = int(database.get_book_by_id(book_id)["library_id"])

    preferences = _store(tmp_path)
    preferences.save_organization_preferences(
        OrganizationPreferences(destination_folder=str(destination))
    )
    protection = ProtectionService(database, preferences=preferences)

    plan = protection.build_metadata_update_plan(
        book_id,
        {"title": "Some Book", "author": "Some Author"},
        organise_file=True,
    )
    expected = (
        destination / "Some Author" / "Some Book - Some Author.epub"
    ).resolve()
    assert Path(plan.file_changes[0].after_summary) == expected

    preview = protection.record_change_plan(plan)
    approved = protection.approve_change_plan(
        preview.operation_id,
        PlanConfirmation(
            plan_token=plan.plan_token,
            approved=True,
            confirmer="test",
        ),
        current_basis_token=protection.current_basis_token(preview),
    )
    protection.apply_approved_operation(
        approved.operation_id,
        protection.build_policy(tmp_path / "backups", 0),
        ProtectionMode.STANDARD,
    )

    after = database.get_book_by_id(book_id)
    assert Path(after["file_path"]).resolve() == expected
    assert expected.is_file()
    assert int(after["library_id"]) != before_library_id
    assert (
        Path(after["library_folder"]).resolve() == destination.resolve()
    )


def test_metadata_apply_snaps_series_name_to_already_catalogued_wording(
    tmp_path: Path,
) -> None:
    """A second volume's differently-worded series must join the first's folder.

    Reproduces a real case: book #1 was organised as "Alfred Hitchcock and
    The Three Investigators". A later book #24 resolves the same series as
    "alfred hitchcock and the three investigators series" (a web-search
    fallback's wording, lowercase with a redundant trailing "series"). It
    must land in the SAME existing folder, not a new near-duplicate one.
    """
    watched = tmp_path / "Watched"
    watched.mkdir()
    destination = tmp_path / "Destination"
    first_source = watched / "First Book.epub"
    first_source.write_bytes(b"data one")
    second_source = watched / "Second Book.epub"
    second_source.write_bytes(b"data two")

    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(
        watched, [_book(first_source), _book(second_source)]
    )
    books = {row["file_name"]: int(row["id"]) for row in database.get_books()}

    preferences = _store(tmp_path)
    preferences.save_organization_preferences(
        OrganizationPreferences(destination_folder=str(destination))
    )
    protection = ProtectionService(database, preferences=preferences)

    def _apply(book_id: int, values: dict[str, object]) -> None:
        plan = protection.build_metadata_update_plan(
            book_id, values, organise_file=True
        )
        preview = protection.record_change_plan(plan)
        approved = protection.approve_change_plan(
            preview.operation_id,
            PlanConfirmation(
                plan_token=plan.plan_token,
                approved=True,
                confirmer="test",
            ),
            current_basis_token=protection.current_basis_token(preview),
        )
        protection.apply_approved_operation(
            approved.operation_id,
            protection.build_policy(tmp_path / "backups", 0),
            ProtectionMode.STANDARD,
        )

    _apply(
        books["First Book.epub"],
        {
            "title": "The Secret of Terror Castle",
            "author": "Robert Arthur",
            "series": "Alfred Hitchcock and The Three Investigators",
            "series_number": 1,
        },
    )
    _apply(
        books["Second Book.epub"],
        {
            "title": "The Mystery of Death Trap Mine",
            "author": "M. V. Carey",
            "series": "alfred hitchcock and the three investigators series",
            "series_number": 24,
        },
    )

    second_after = database.get_book_by_id(books["Second Book.epub"])
    assert second_after["series"] == "Alfred Hitchcock and The Three Investigators"
    expected = (
        destination
        / "-=Series=-"
        / "Alfred Hitchcock and The Three Investigators"
        / "24 - The Mystery of Death Trap Mine - M. V. Carey.epub"
    ).resolve()
    assert Path(second_after["file_path"]).resolve() == expected
    assert expected.is_file()

    series_folder = destination / "-=Series=-"
    assert [child.name for child in series_folder.iterdir()] == [
        "Alfred Hitchcock and The Three Investigators"
    ]


def test_move_book_to_deleted_uses_configured_destination(
    tmp_path: Path,
) -> None:
    watched = tmp_path / "Watched"
    watched.mkdir()
    destination = tmp_path / "Destination"
    source = watched / "Unwanted.epub"
    source.write_bytes(b"data")

    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(watched, [_book(source)])
    book_id = int(database.get_books()[0]["id"])

    preferences = _store(tmp_path)
    preferences.save_organization_preferences(
        OrganizationPreferences(destination_folder=str(destination))
    )
    library_service = LibraryService(database, preferences=preferences)

    result = library_service.move_book_to_deleted(book_id)

    expected = destination / DELETED_FOLDER_NAME / "Unwanted.epub"
    assert Path(result.destination_path) == expected.resolve()
    assert expected.is_file()
    assert not source.exists()
    assert database.get_book_by_id(book_id) is None


def test_relink_missing_books_from_exact_relative_path(
    tmp_path: Path,
) -> None:
    old_root = tmp_path / "OldWatched"
    organized = old_root / "-=Series=-" / "Three Investigators"
    organized.mkdir(parents=True)
    source = organized / "01 - The Secret of Terror Castle - Robert Arthur.epub"
    source.write_bytes(b"book content")

    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(old_root, [_book(source)])
    book_id = int(database.get_books()[0]["id"])

    new_root = tmp_path / "NewDestination"
    new_organized = new_root / "-=Series=-" / "Three Investigators"
    new_organized.mkdir(parents=True)
    relocated = (
        new_organized / "01 - The Secret of Terror Castle - Robert Arthur.epub"
    )
    source.rename(relocated)
    with database.connection() as connection:
        connection.execute(
            "UPDATE books SET is_missing = 1 WHERE id = ?",
            (book_id,),
        )

    library_service = LibraryService(database)
    summary = library_service.relink_missing_books_from(new_root)

    assert summary.relinked_book_ids == (book_id,)
    assert summary.still_missing_count == 0
    after = database.get_book_by_id(book_id)
    assert Path(after["file_path"]).resolve() == relocated.resolve()
    assert bool(after["is_missing"]) is False
    assert Path(after["library_folder"]).resolve() == new_root.resolve()


def test_relink_missing_books_falls_back_to_name_and_size_search(
    tmp_path: Path,
) -> None:
    old_root = tmp_path / "OldWatched"
    old_root.mkdir()
    source = old_root / "Some Book.epub"
    source.write_bytes(b"book content")

    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(old_root, [_book(source)])
    book_id = int(database.get_books()[0]["id"])

    # Moved into a differently structured folder tree, not the same
    # relative path — only the exact filename and size are preserved.
    new_root = tmp_path / "NewDestination"
    nested = new_root / "Some Author" / "Nested"
    nested.mkdir(parents=True)
    relocated = nested / "Some Book.epub"
    source.rename(relocated)
    with database.connection() as connection:
        connection.execute(
            "UPDATE books SET is_missing = 1 WHERE id = ?",
            (book_id,),
        )

    library_service = LibraryService(database)
    summary = library_service.relink_missing_books_from(new_root)

    assert summary.relinked_book_ids == (book_id,)
    after = database.get_book_by_id(book_id)
    assert Path(after["file_path"]).resolve() == relocated.resolve()
    assert bool(after["is_missing"]) is False


def test_relink_missing_books_does_not_match_a_different_sized_file(
    tmp_path: Path,
) -> None:
    old_root = tmp_path / "OldWatched"
    old_root.mkdir()
    source = old_root / "Some Book.epub"
    source.write_bytes(b"original content")

    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(old_root, [_book(source)])
    book_id = int(database.get_books()[0]["id"])
    with database.connection() as connection:
        connection.execute(
            "UPDATE books SET is_missing = 1 WHERE id = ?",
            (book_id,),
        )
    source.unlink()

    # A same-named but different-sized file must not be mistaken for it.
    new_root = tmp_path / "NewDestination"
    new_root.mkdir()
    (new_root / "Some Book.epub").write_bytes(b"unrelated file")

    library_service = LibraryService(database)
    summary = library_service.relink_missing_books_from(new_root)

    assert summary.relinked_book_ids == ()
    assert summary.still_missing_count == 1
    after = database.get_book_by_id(book_id)
    assert bool(after["is_missing"]) is True


def test_find_books_with_missing_files_checks_the_whole_catalogue(
    tmp_path: Path,
) -> None:
    """Unlike a per-source scan, this must catch a book organised outside
    any watched source -- the exact gap that let stale catalogue rows
    accumulate silently."""
    watched = tmp_path / "Watched"
    watched.mkdir()
    present = watched / "Present Book.epub"
    present.write_bytes(b"data")
    gone = watched / "Gone Book.epub"
    gone.write_bytes(b"data")
    outside_destination = tmp_path / "Destination" / "Organised Book.epub"
    outside_destination.parent.mkdir(parents=True)
    outside_destination.write_bytes(b"data")

    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(
        watched, [_book(present), _book(gone)]
    )
    gone_id = int(
        next(
            row["id"] for row in database.get_books()
            if row["file_name"] == "Gone Book.epub"
        )
    )
    gone.unlink()

    # Simulate a book already organised outside any watched source, the
    # same as a real destination-folder book -- a normal per-source scan
    # never revisits this path at all.
    with database.connection() as connection:
        connection.execute(
            "UPDATE books SET file_path = ? WHERE file_name = ?",
            (str(outside_destination), "Present Book.epub"),
        )
    outside_destination.unlink()

    library_service = LibraryService(database)
    entries = library_service.find_books_with_missing_files()

    assert {entry.book_id for entry in entries} == {gone_id} | {
        row["id"]
        for row in database.get_books()
        if row["file_name"] == "Present Book.epub"
    }
    found_titles = {entry.title for entry in entries}
    assert "Gone Book" in found_titles
    assert "Present Book" in found_titles


def test_remove_books_from_catalogue_deletes_rows_only(
    tmp_path: Path,
) -> None:
    watched = tmp_path / "Watched"
    watched.mkdir()
    source = watched / "Some Book.epub"
    source.write_bytes(b"data")

    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(watched, [_book(source)])
    book_id = int(database.get_books()[0]["id"])

    library_service = LibraryService(database)
    removed = library_service.remove_books_from_catalogue([book_id])

    assert removed == 1
    assert database.get_book_by_id(book_id) is None
    # The file itself is never touched by removing the catalogue row.
    assert source.is_file()


def test_remove_books_from_catalogue_ignores_already_removed_ids(
    tmp_path: Path,
) -> None:
    database = DatabaseManager(tmp_path / "library.db")
    library_service = LibraryService(database)

    removed = library_service.remove_books_from_catalogue([999999])

    assert removed == 0


def test_scan_completion_relinks_missing_books_without_resaving_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A book only found missing after the destination was last saved must
    still get relinked once the next scan/apply completes, not just when
    the user re-saves the destination folder field.

    Reproduces: the user moves already-organised files to a newly chosen
    destination first, then saves the destination folder setting (which
    finds nothing missing yet, since no scan has noticed the move), and
    only later runs a normal scan of the original source, which is the
    first thing to flag those books missing.
    """
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    old_root = tmp_path / "OldWatched"
    old_root.mkdir()
    source = old_root / "Some Book.epub"
    source.write_bytes(b"book content")

    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(old_root, [_book(source)])
    book_id = int(database.get_books()[0]["id"])

    new_root = tmp_path / "NewDestination"
    new_root.mkdir()
    relocated = new_root / "Some Book.epub"
    source.rename(relocated)

    preferences = _store(tmp_path)
    preferences.save_organization_preferences(
        OrganizationPreferences(destination_folder=str(new_root))
    )

    # Only a later scan of the original source notices the file is gone.
    with database.connection() as connection:
        connection.execute(
            "UPDATE books SET is_missing = 1 WHERE id = ?",
            (book_id,),
        )

    window = MainWindow(
        library_service=LibraryService(database),
        dashboard_service=DashboardService(database),
        preferences=preferences,
        scan_service_factory=lambda: ScanService(database),
        protection_service_factory=lambda: ProtectionService(database),
    )

    window.scan_page.catalogue_changed.emit()

    after = database.get_book_by_id(book_id)
    assert Path(after["file_path"]).resolve() == relocated.resolve()
    assert bool(after["is_missing"]) is False

    window.close()


def test_settings_page_emits_destination_change_on_every_save(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    store = _store(tmp_path)
    page = SettingsPage(store)
    changes: list[str] = []
    page.destination_folder_changed.connect(changes.append)

    destination = tmp_path / "Destination"
    page.destination_folder_edit.setText(str(destination))
    page.save()

    assert changes == [str(destination)]

    # Saving again with the same, unchanged path still re-emits: it's
    # what lets the user re-check for books they moved into the folder
    # themselves since the last save, without editing the path.
    changes.clear()
    page.save()

    assert changes == [str(destination)]
    page.close()


def test_settings_page_does_not_emit_when_destination_is_empty(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    store = _store(tmp_path)
    page = SettingsPage(store)
    changes: list[str] = []
    page.destination_folder_changed.connect(changes.append)

    page.save()

    assert changes == []
    page.close()


def test_settings_page_saves_destination_folder(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    store = _store(tmp_path)
    page = SettingsPage(store)

    destination = tmp_path / "Destination"
    page.destination_folder_edit.setText(str(destination))
    page.save()

    saved = store.load_organization_preferences()
    assert saved.destination_folder == str(destination)
    assert saved.destination_prompt_shown
    page.close()

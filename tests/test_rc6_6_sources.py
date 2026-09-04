"""RC6.6 watched-source database and service contracts."""

from pathlib import Path
import sqlite3
from time import monotonic, sleep

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from core.scanner import BookFile
from database.database import DatabaseManager
from services.scan_service import (
    ScanService,
    SourceConnectionStatus,
)
from ui.scan_page import ScanPage


def test_rc6_5_library_schema_migrates_to_source_defaults(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy.db"
    source_path = str((tmp_path / "Legacy Books").resolve())
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE libraries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_path TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                last_scanned_at TEXT
            );
            """
        )
        connection.execute(
            """
            INSERT INTO libraries (
                folder_path,
                created_at,
                last_scanned_at
            )
            VALUES (?, '2026-07-28T00:00:00+00:00', NULL)
            """,
            (source_path,),
        )

    service = ScanService(DatabaseManager(database_path))
    sources = service.get_sources()

    assert len(sources) == 1
    assert sources[0].folder_path == source_path
    assert sources[0].display_name == "Legacy Books"
    assert sources[0].enabled
    assert sources[0].include_subfolders
    assert sources[0].include_patterns == ()
    assert sources[0].exclude_patterns == ()
    assert (
        sources[0].connection_status
        == SourceConnectionStatus.NOT_TESTED
    )


def test_source_removal_drops_catalogue_books_but_preserves_files(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Books"
    folder.mkdir()
    book_path = folder / "Example.epub"
    book_path.write_bytes(b"example")
    database = DatabaseManager(tmp_path / "library.db")
    service = ScanService(database)

    source = service.add_source(
        folder,
        display_name="Main Library",
        include_patterns="*.epub; *.pdf; *.EPUB",
        exclude_patterns="Temp/**; **/Drafts/**",
    )
    database.save_scan_results(
        folder,
        [
            BookFile(
                name="Example",
                extension="EPUB",
                size_bytes=book_path.stat().st_size,
                path=book_path,
            )
        ],
    )

    with pytest.raises(ValueError, match="already being watched"):
        service.add_source(folder)

    edited = service.update_source(
        source.source_id,
        display_name="Edited Library",
        include_subfolders=False,
        include_patterns=("*.epub",),
        exclude_patterns=("Archive/**",),
    )
    disabled = service.set_source_enabled(source.source_id, False)
    enabled = service.set_source_enabled(source.source_id, True)

    assert edited.display_name == "Edited Library"
    assert not edited.include_subfolders
    assert edited.include_patterns == ("*.epub",)
    assert disabled.connection_status == SourceConnectionStatus.DISABLED
    assert not disabled.enabled
    assert enabled.enabled

    result = service.remove_source(source.source_id)

    assert service.get_sources() == ()
    assert result.removed_book_count == 1
    assert database.count_library_source_books(source.source_id) == 0
    assert database.count_books() == 0
    assert book_path.is_file()
    dashboard = database.get_dashboard_statistics()
    assert dashboard["library_count"] == 0
    assert dashboard["library_locations"] == []
    assert dashboard["last_scanned_at"] is None

    restored = service.add_source(folder, display_name="Restored Library")

    assert restored.source_id == source.source_id
    assert restored.display_name == "Restored Library"
    assert restored.enabled
    assert not restored.archived_at
    assert database.count_library_source_books(source.source_id) == 0


def test_source_removal_does_not_change_other_library_sources(
    tmp_path: Path,
) -> None:
    first_folder = tmp_path / "First"
    second_folder = tmp_path / "Second"
    first_folder.mkdir()
    second_folder.mkdir()
    first_book = first_folder / "First.epub"
    second_book = second_folder / "Second.epub"
    first_book.write_bytes(b"first")
    second_book.write_bytes(b"second")
    database = DatabaseManager(tmp_path / "library.db")
    service = ScanService(database)
    first_source = service.add_source(first_folder, display_name="First")
    second_source = service.add_source(second_folder, display_name="Second")
    database.save_scan_results(first_folder, [
        BookFile("First", "EPUB", first_book.stat().st_size, first_book)
    ])
    database.save_scan_results(second_folder, [
        BookFile("Second", "EPUB", second_book.stat().st_size, second_book)
    ])

    result = service.remove_source(first_source.source_id)

    assert result.removed_book_count == 1
    assert tuple(source.source_id for source in service.get_sources()) == (
        second_source.source_id,
    )
    assert database.count_library_source_books(first_source.source_id) == 0
    assert database.count_library_source_books(second_source.source_id) == 1
    assert database.count_books() == 1
    assert first_book.is_file()
    assert second_book.is_file()


def test_source_removal_refuses_active_quarantine_records(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Books"
    folder.mkdir()
    book_path = folder / "Quarantined.epub"
    book_path.write_bytes(b"book")
    database = DatabaseManager(tmp_path / "library.db")
    service = ScanService(database)
    source = service.add_source(folder, display_name="Books")
    database.save_scan_results(folder, [
        BookFile(
            "Quarantined",
            "EPUB",
            book_path.stat().st_size,
            book_path,
        )
    ])
    book_id = int(database.get_books()[0]["id"])
    database.record_quarantine_item(
        book_id=book_id,
        original_path=str(book_path),
        quarantine_path=str(tmp_path / "quarantine" / "Quarantined.epub"),
    )

    with pytest.raises(ValueError, match="Restore.*quarantined books"):
        service.remove_source(source.source_id)

    assert service.get_source(source.source_id).source_id == source.source_id
    assert database.count_books(include_missing=True) == 1


def test_connection_results_distinguish_common_source_states(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Readable"
    folder.mkdir()
    file_path = tmp_path / "not-a-folder.txt"
    file_path.write_text("file", encoding="utf-8")
    missing = tmp_path / "missing"
    service = ScanService(DatabaseManager(tmp_path / "library.db"))

    available_source = service.add_source(
        folder,
        display_name="Readable",
    )
    file_source = service.add_source(
        file_path,
        display_name="File",
    )
    missing_source = service.add_source(
        missing,
        display_name="Missing",
    )

    available = service.test_source(available_source.source_id)
    not_folder = service.test_source(file_source.source_id)
    unavailable = service.test_source(missing_source.source_id)
    service.set_source_enabled(available_source.source_id, False)
    disabled = service.test_source(available_source.source_id)

    assert available.available
    assert not_folder.status == SourceConnectionStatus.NOT_FOLDER
    assert unavailable.status == SourceConnectionStatus.UNAVAILABLE
    assert disabled.status == SourceConnectionStatus.DISABLED
    assert (
        service.get_source(missing_source.source_id).connection_status
        == SourceConnectionStatus.UNAVAILABLE
    )


def test_permission_failure_is_reported_without_book_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    folder = tmp_path / "Protected"
    folder.mkdir()
    database = DatabaseManager(tmp_path / "library.db")
    service = ScanService(database)
    source = service.add_source(folder, display_name="Protected")

    def deny_access(_folder):
        raise PermissionError("denied")

    monkeypatch.setattr("services.scan_service.os.scandir", deny_access)

    result = service.test_source(source.source_id)

    assert result.status == SourceConnectionStatus.PERMISSION_DENIED
    assert database.count_books(include_missing=True) == 0


def test_source_paths_and_rules_validate_local_mapped_and_unc_shapes(
    tmp_path: Path,
) -> None:
    local = ScanService.normalise_source_path(tmp_path)
    mapped = ScanService.normalise_source_path(r"Z:\Ebooks")
    unc = ScanService.normalise_source_path(
        r"\\server\library\Ebooks"
    )
    patterns = ScanService.normalise_patterns(
        "*.epub; **/*.pdf\n*.EPUB"
    )

    assert local.is_absolute()
    assert str(mapped).lower().startswith("z:")
    assert str(unc).startswith("\\\\server\\library")
    assert patterns == ("*.epub", "**/*.pdf")

    with pytest.raises(ValueError, match="absolute"):
        ScanService.normalise_source_path("relative/books")
    with pytest.raises(ValueError, match="relative patterns"):
        ScanService.normalise_patterns("../outside/**")


def test_scan_page_remove_prompts_then_removes_only_catalogue_books(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    database_path = tmp_path / "ui.db"
    factory = lambda: ScanService(DatabaseManager(database_path))
    page = ScanPage(factory)
    source = page.source_service.add_source(
        tmp_path,
        display_name="UI Library",
        exclude_patterns="Temp/**",
    )
    book_path = tmp_path / "UI Book.epub"
    book_path.write_bytes(b"ebook stays on disk")
    DatabaseManager(database_path).save_scan_results(
        tmp_path,
        [
            BookFile(
                name="UI Book",
                extension="EPUB",
                size_bytes=book_path.stat().st_size,
                path=book_path,
            )
        ],
    )
    page.refresh_sources(source.source_id)

    assert page.source_table.rowCount() == 1
    assert page.source_table.item(0, 0).text() == "UI Library"
    assert page.selected_source_id == source.source_id
    assert page.edit_source_button.isEnabled()
    assert {
        page.select_button.objectName(),
        page.edit_source_button.objectName(),
        page.test_source_button.objectName(),
        page.toggle_source_button.objectName(),
        page.remove_source_button.objectName(),
        page.scan_button.objectName(),
        page.scan_all_button.objectName(),
        page.cancel_button.objectName(),
        page.discard_button.objectName(),
        page.apply_button.objectName(),
    } == {
        "addSourceAction",
        "editSourceAction",
        "testConnectionAction",
        "toggleSourceAction",
        "removeWatchAction",
        "previewScanAction",
        "previewAllSourcesAction",
        "cancelScanAction",
        "discardPreviewAction",
        "applyPreviewAction",
    }

    page._toggle_source()
    assert page.toggle_source_button.text() == "Enable Source"
    page._toggle_source()
    assert page.toggle_source_button.text() == "Disable Source"

    prompts: list[str] = []
    defaults: list[QMessageBox.StandardButton] = []
    answers = [
        QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    ]

    def confirm_removal(*args, **_kwargs):
        prompts.append(str(args[2]))
        defaults.append(args[4])
        return answers.pop(0)

    monkeypatch.setattr(
        "ui.scan_page.QMessageBox.question",
        confirm_removal,
    )
    catalogue_changes: list[bool] = []
    page.catalogue_changed.connect(lambda: catalogue_changes.append(True))
    page._remove_source()
    application.processEvents()

    assert page.source_table.rowCount() == 1
    assert DatabaseManager(database_path).count_books() == 1
    assert book_path.is_file()
    assert catalogue_changes == []

    page._remove_source()
    deadline = monotonic() + 3.0
    while page.removal_thread is not None and monotonic() < deadline:
        application.processEvents()
        sleep(0.01)

    assert page.source_table.rowCount() == 0
    assert len(prompts) == 2
    assert defaults == [
        QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    ]
    assert "remove 1 book" in prompts[0].casefold()
    assert "will not be deleted, moved, renamed, or modified" in prompts[0]
    assert "No other library sources will be affected" in prompts[0]
    assert DatabaseManager(database_path).count_books() == 0
    assert book_path.is_file()
    assert catalogue_changes == [True]
    assert "1 book" in page.status_label.text()
    assert "ebook files were unchanged" in page.status_label.text()
    page.deleteLater()
    application.processEvents()


def test_scan_page_connection_test_runs_off_gui_thread(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    database_path = tmp_path / "connection.db"
    factory = lambda: ScanService(DatabaseManager(database_path))
    page = ScanPage(factory)
    source = page.source_service.add_source(
        tmp_path,
        display_name="Connected",
    )
    page.refresh_sources(source.source_id)

    page._test_source_connection()
    deadline = monotonic() + 3.0
    while page.connection_thread is not None and monotonic() < deadline:
        application.processEvents()
        sleep(0.01)

    assert page.connection_thread is None
    assert (
        page.source_service.get_source(source.source_id).connection_status
        == SourceConnectionStatus.AVAILABLE
    )
    assert page.scan_button.isEnabled()
    assert page.scan_button.text() == "Preview Scan"
    assert "successful" in page.status_label.text()
    page.deleteLater()
    application.processEvents()

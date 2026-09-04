"""RC6.6 non-mutating source analysis tests."""

import os
from pathlib import Path
from time import monotonic, sleep

from PySide6.QtWidgets import QApplication

from core.scanner import BookFile
from database.database import DatabaseManager
from services.scan_service import (
    ScanItemStatus,
    ScanService,
)
from ui.library_source_dialog import MultipleLibrarySourcesDialog
from ui.scan_page import ScanPage
from workers.scan_analysis_worker import ScanAnalysisWorker


def _book(path: Path) -> BookFile:
    return BookFile(
        name=path.stem,
        extension=path.suffix.removeprefix(".").upper(),
        size_bytes=path.stat().st_size,
        path=path,
    )


def test_analysis_classifies_changes_without_database_mutation(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Books"
    folder.mkdir()
    unchanged_path = folder / "Unchanged.epub"
    changed_path = folder / "Changed.pdf"
    missing_path = folder / "Missing.txt"
    for path, content in (
        (unchanged_path, b"unchanged"),
        (changed_path, b"old"),
        (missing_path, b"missing"),
    ):
        path.write_bytes(content)

    database = DatabaseManager(tmp_path / "library.db")
    service = ScanService(database)
    source = service.add_source(folder, display_name="Books")
    database.save_scan_results(
        folder,
        [_book(unchanged_path), _book(changed_path), _book(missing_path)],
    )
    changed_path.write_bytes(b"changed and larger")
    missing_path.unlink()
    new_path = folder / "New.mobi"
    new_path.write_bytes(b"new")
    (folder / "Unsupported.docx").write_bytes(b"skip")

    before_books = [
        dict(row)
        for row in database.get_library_source_book_snapshot(
            source.source_id
        )
    ]
    before_source = dict(
        database.get_library_source(source.source_id)
    )

    result = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )

    statuses = {
        item.relative_path: item.status
        for item in result.items
    }
    assert result.completed
    assert result.connected
    assert not result.cancelled
    assert statuses == {
        "Changed.pdf": ScanItemStatus.CHANGED,
        "Missing.txt": ScanItemStatus.MISSING,
        "New.mobi": ScanItemStatus.NEW,
        "Unchanged.epub": ScanItemStatus.UNCHANGED,
    }
    assert result.skipped_count == 1
    assert result.applicable_count == 3

    after_books = [
        dict(row)
        for row in database.get_library_source_book_snapshot(
            source.source_id
        )
    ]
    after_source = dict(database.get_library_source(source.source_id))
    assert after_books == before_books
    assert after_source["last_scanned_at"] == before_source["last_scanned_at"]
    assert all(not row["is_missing"] for row in after_books)


def test_analysis_trusts_an_unchanged_organised_folder(
    tmp_path: Path,
) -> None:
    """An untouched author/-=Series=- folder is not re-examined file by file.

    A folder's own modified time only advances when an entry inside it is
    added, removed, or renamed — not when an existing file's contents are
    edited. ``Author A`` proves the fast path is really trusting that
    folder-level signal (by corrupting the file's on-disk bytes without
    touching the folder, which a genuine re-check would have caught) rather
    than actually re-reading it. ``Author B`` proves a real new file dropped
    into a different organised folder — which does bump that folder's own
    mtime — is still discovered, since the fast path never engages there.
    """
    folder = tmp_path / "Books"
    folder.mkdir()
    author_a = folder / "Author A"
    author_a.mkdir()
    book_a = author_a / "Book.epub"
    book_a.write_bytes(b"original content")
    author_b = folder / "Author B"
    author_b.mkdir()
    book_b = author_b / "Existing.epub"
    book_b.write_bytes(b"existing content")

    database = DatabaseManager(tmp_path / "library.db")
    service = ScanService(database)
    source = service.add_source(folder, display_name="Books")
    database.save_scan_results(folder, [_book(book_a), _book(book_b)])

    # save_scan_results alone does not record a fingerprint (that only
    # happens once real changes are applied); set one here to match what a
    # completed scan+apply cycle would already have stored, since the fast
    # path (like _candidate_status itself) only trusts a recorded
    # fingerprint.
    with database.connection() as connection:
        for book_path in (book_a, book_b):
            stat = book_path.stat()
            connection.execute(
                "UPDATE books SET file_fingerprint = ? WHERE file_path = ?",
                (
                    f"{stat.st_size}:{stat.st_mtime_ns}",
                    str(book_path.resolve()),
                ),
            )
            connection.commit()

    # Mutate Book.epub's bytes without adding/removing/renaming any entry
    # in Author A, then pin that folder's own mtime to guarantee it is not
    # newer than the scan that just completed, regardless of filesystem
    # timestamp resolution.
    book_a.write_bytes(b"corrupted without touching the folder")
    frozen_mtime = author_a.stat().st_mtime
    os.utime(author_a, (frozen_mtime, frozen_mtime))

    # A genuinely new file dropped into Author B bumps that folder's own
    # mtime, so it must still be discovered on the next scan.
    new_book_b = author_b / "New.epub"
    new_book_b.write_bytes(b"new")

    result = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )

    statuses = {
        item.relative_path: item.status for item in result.items
    }
    assert statuses["Author A/Book.epub"] == ScanItemStatus.UNCHANGED
    assert statuses["Author B/Existing.epub"] == ScanItemStatus.UNCHANGED
    assert statuses["Author B/New.epub"] == ScanItemStatus.NEW


def test_source_rules_keep_out_of_scope_books_from_missing_preview(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Rules"
    nested = folder / "Nested"
    excluded = folder / "Skip"
    nested.mkdir(parents=True)
    excluded.mkdir()
    root_book = folder / "Root.epub"
    nested_book = nested / "Nested.epub"
    excluded_book = excluded / "Excluded.epub"
    pdf_book = folder / "Ignored.pdf"
    for path in (root_book, nested_book, excluded_book, pdf_book):
        path.write_bytes(path.name.encode("utf-8"))

    database = DatabaseManager(tmp_path / "rules.db")
    service = ScanService(database)
    source = service.add_source(folder, display_name="Rules")
    database.save_scan_results(
        folder,
        [_book(root_book), _book(nested_book), _book(excluded_book)],
    )
    service.update_source(
        source.source_id,
        display_name="Rules",
        include_subfolders=False,
        include_patterns="*.epub",
        exclude_patterns="Skip/**",
    )
    nested_book.unlink()
    excluded_book.unlink()

    result = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )

    assert result.completed
    assert [
        (item.relative_path, item.status)
        for item in result.items
    ] == [("Root.epub", ScanItemStatus.UNCHANGED)]
    assert result.skipped_count == 1


def test_cancelled_analysis_never_infers_missing_or_updates_source(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Cancel"
    folder.mkdir()
    paths = [folder / f"Book {index}.epub" for index in range(4)]
    for path in paths:
        path.write_bytes(path.name.encode("utf-8"))
    database = DatabaseManager(tmp_path / "cancel.db")
    service = ScanService(database)
    source = service.add_source(folder, display_name="Cancel")
    database.save_scan_results(folder, [_book(path) for path in paths])
    paths[-1].unlink()
    cancelled = False

    def on_count(count: int) -> None:
        nonlocal cancelled
        cancelled = count >= 1

    before = [
        dict(row)
        for row in database.get_library_source_book_snapshot(
            source.source_id
        )
    ]
    result = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: cancelled,
        on_discovery_count=on_count,
    )

    assert result.cancelled
    assert not result.completed
    assert result.count(ScanItemStatus.MISSING) == 0
    assert [
        dict(row)
        for row in database.get_library_source_book_snapshot(
            source.source_id
        )
    ] == before


def test_unavailable_source_does_not_create_mass_missing_preview(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Network"
    folder.mkdir()
    book_path = folder / "Book.epub"
    book_path.write_bytes(b"book")
    database = DatabaseManager(tmp_path / "network.db")
    service = ScanService(database)
    source = service.add_source(folder, display_name="Network")
    database.save_scan_results(folder, [_book(book_path)])
    disconnected = tmp_path / "Disconnected"
    folder.rename(disconnected)

    result = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )

    assert not result.connected
    assert not result.completed
    assert result.items == ()
    assert result.count(ScanItemStatus.MISSING) == 0
    assert database.count_books() == 1


def test_unreadable_supported_file_is_reported_not_silently_lost(
    tmp_path: Path,
    monkeypatch,
) -> None:
    folder = tmp_path / "Unreadable"
    folder.mkdir()
    book_path = folder / "Protected.epub"
    book_path.write_bytes(b"book")
    service = ScanService(DatabaseManager(tmp_path / "unreadable.db"))
    source = service.add_source(folder, display_name="Unreadable")
    original_stat = Path.stat

    def guarded_stat(path: Path, *args, **kwargs):
        if path == book_path:
            raise PermissionError("denied")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", guarded_stat)

    result = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )

    assert result.completed
    assert result.count(ScanItemStatus.UNREADABLE) == 1
    assert result.issues[0].category == "unreadable"


def test_preview_ui_keeps_database_unchanged_until_discard(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    folder = tmp_path / "Preview"
    folder.mkdir()
    (folder / "New.epub").write_bytes(b"new")
    database_path = tmp_path / "preview.db"
    factory = lambda: ScanService(DatabaseManager(database_path))
    page = ScanPage(factory)
    source = page.source_service.add_source(
        folder,
        display_name="Preview",
    )
    page.refresh_sources(source.source_id)

    page._start_scan()
    deadline = monotonic() + 3.0
    while page.analysis_thread is not None and monotonic() < deadline:
        application.processEvents()
        sleep(0.01)

    assert page.analysis_thread is None
    assert page.current_analysis is not None
    assert page.current_analysis.completed
    assert page.results_table.rowCount() == 1
    assert page.results_table.item(0, 0).text() == "New"
    assert DatabaseManager(database_path).count_books() == 0
    assert "Nothing has been applied" in page.status_label.text()
    assert page.discard_button.isEnabled()
    assert page.apply_button.isEnabled()

    page.discard_button.click()

    assert page.current_analysis is None
    assert page.results_table.rowCount() == 0
    assert DatabaseManager(database_path).count_books() == 0
    assert not page.apply_button.isEnabled()
    page.deleteLater()
    application.processEvents()


def test_multiple_source_dialog_stages_unique_folders(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    first = tmp_path / "First"
    second = tmp_path / "Second"
    first.mkdir()
    second.mkdir()
    dialog = MultipleLibrarySourcesDialog()

    dialog.add_folder_path(str(first))
    dialog.add_folder_path(str(second))
    dialog.add_folder_path(str(first))

    assert dialog.folder_paths == (str(first.resolve()), str(second.resolve()))
    assert dialog.include_subfolders
    dialog.deleteLater()
    application.processEvents()


def test_preview_all_scans_every_enabled_watched_folder(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    database_path = tmp_path / "all-sources.db"
    factory = lambda: ScanService(DatabaseManager(database_path))
    page = ScanPage(factory)
    first = tmp_path / "First"
    second = tmp_path / "Second"
    disabled = tmp_path / "Disabled"
    for folder in (first, second, disabled):
        folder.mkdir()
        (folder / f"{folder.name}.epub").write_bytes(b"book")
    first_source = page.source_service.add_source(
        first,
        display_name="First",
    )
    page.source_service.add_source(second, display_name="Second")
    disabled_source = page.source_service.add_source(
        disabled,
        display_name="Disabled",
    )
    page.source_service.set_source_enabled(
        disabled_source.source_id,
        False,
    )
    page.refresh_sources(first_source.source_id)

    page._start_all_scans()
    deadline = monotonic() + 5.0
    while page.is_scanning() and monotonic() < deadline:
        application.processEvents()
        sleep(0.01)

    assert not page.is_scanning()
    assert len(page.current_analyses) == 2
    assert {
        analysis.source.display_name for analysis in page.current_analyses
    } == {"First", "Second"}
    assert page.results_table.rowCount() == 2
    locations = {
        page.results_table.item(row, 4).text()
        for row in range(page.results_table.rowCount())
    }
    assert any(location.startswith("First") for location in locations)
    assert any(location.startswith("Second") for location in locations)
    assert DatabaseManager(database_path).count_books() == 0
    assert "Combined preview ready" in page.status_label.text()
    assert page.apply_button.isEnabled()
    page.deleteLater()
    application.processEvents()


def test_analysis_worker_pre_cancel_returns_safe_cancelled_result(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Worker"
    folder.mkdir()
    (folder / "Book.epub").write_bytes(b"book")
    database_path = tmp_path / "worker.db"
    service = ScanService(DatabaseManager(database_path))
    source = service.add_source(folder, display_name="Worker")
    worker = ScanAnalysisWorker(
        source.source_id,
        lambda: ScanService(DatabaseManager(database_path)),
    )
    cancelled = []
    finished = []
    worker.cancelled.connect(cancelled.append)
    worker.finished.connect(lambda: finished.append(True))

    worker.request_cancel()
    worker.run()

    assert len(cancelled) == 1
    assert cancelled[0].cancelled
    assert cancelled[0].count(ScanItemStatus.MISSING) == 0
    assert finished == [True]
    assert DatabaseManager(database_path).count_books() == 0

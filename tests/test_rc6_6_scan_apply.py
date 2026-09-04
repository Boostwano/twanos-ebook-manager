"""RC6.6 guarded Apply, history, rollback, and UI tests."""

from pathlib import Path
from time import monotonic, sleep

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from core.scanner import BookFile
from database.database import DatabaseManager
from metadata.provider_manager import ProviderManager
from services.scan_service import (
    ScanApplyStatus,
    ScanItemStatus,
    ScanService,
)
from ui.scan_page import ScanPage
from workers.scan_apply_worker import ScanApplyWorker


def _book(path: Path) -> BookFile:
    return BookFile(
        name=path.stem,
        extension=path.suffix.removeprefix(".").upper(),
        size_bytes=path.stat().st_size,
        path=path,
    )


def _service(database: DatabaseManager) -> ScanService:
    return ScanService(database, ProviderManager())


def _wait_until(predicate, timeout: float = 3.0) -> None:
    application = QApplication.instance()
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        application.processEvents()
        if predicate():
            return
        sleep(0.01)
    raise AssertionError("Timed out waiting for Qt background work")


def test_apply_commits_new_changed_missing_and_history_atomically(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Books"
    folder.mkdir()
    unchanged = folder / "Unchanged.epub"
    changed = folder / "Changed.pdf"
    missing = folder / "Missing.txt"
    for path, content in (
        (unchanged, b"unchanged"),
        (changed, b"old"),
        (missing, b"missing"),
    ):
        path.write_bytes(content)

    database = DatabaseManager(tmp_path / "library.db")
    service = _service(database)
    source = service.add_source(folder, display_name="Books")
    database.save_scan_results(
        folder,
        [_book(unchanged), _book(changed), _book(missing)],
    )
    database.update_book_metadata(
        changed,
        title="Curated title",
        author="Known author",
        isbn=None,
        publisher=None,
        language=None,
        published_date=None,
        metadata_status="embedded",
    )
    changed.write_bytes(b"changed and larger")
    missing.unlink()
    added = folder / "Added.mobi"
    added.write_bytes(b"added")

    preview = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )
    backup_progress: list[tuple[int, str]] = []
    result = service.apply_analysis(
        preview,
        is_cancelled=lambda: False,
        on_backup_progress=(
            lambda percent, message: backup_progress.append(
                (percent, message)
            )
        ),
    )

    assert result.status == ScanApplyStatus.APPLIED
    assert result.applied_new_count == 1
    assert result.applied_changed_count == 1
    assert result.applied_missing_count == 1
    assert result.refreshed_count == 1
    assert result.safely_skipped == ()
    assert backup_progress[0][0] == 2
    assert backup_progress[-1][0] == 100
    assert any(
        "integrity" in message.casefold()
        for _percent, message in backup_progress
    )
    assert database.count_books() == 3
    assert database.count_books(include_missing=True) == 4

    rows = {
        row["file_name"]: dict(row)
        for row in database.get_books(include_missing=True)
    }
    assert rows["Changed.pdf"]["title"] == "Curated title"
    assert rows["Changed.pdf"]["author"] == "Known author"
    assert not rows["Changed.pdf"]["is_missing"]
    assert rows["Missing.txt"]["is_missing"]

    history = database.list_scan_history(source.source_id)
    assert len(history) == 1
    assert history[0]["status"] == "applied"
    assert history[0]["applied_new_count"] == 1
    assert history[0]["applied_changed_count"] == 1
    assert history[0]["applied_missing_count"] == 1
    assert history[0]["refreshed_count"] == 1
    source_row = database.get_library_source(source.source_id)
    assert source_row["last_scan_status"] == "applied"
    assert source_row["last_scanned_at"] == history[0]["finished_at"]


def test_repeat_preview_has_no_changes_and_creates_no_duplicates(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Repeat"
    folder.mkdir()
    book_path = folder / "Book.epub"
    book_path.write_bytes(b"book")
    database = DatabaseManager(tmp_path / "repeat.db")
    service = _service(database)
    source = service.add_source(folder, display_name="Repeat")

    first = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )
    service.apply_analysis(first, is_cancelled=lambda: False)
    second = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )

    assert second.count(ScanItemStatus.UNCHANGED) == 1
    assert second.applicable_count == 0
    with pytest.raises(ValueError, match="no catalogue changes"):
        service.apply_analysis(second, is_cancelled=lambda: False)
    assert database.count_books(include_missing=True) == 1
    assert len(database.list_scan_history(source.source_id)) == 2
    assert database.list_scan_history(source.source_id)[0]["status"] == "failed"


def test_vanished_candidate_is_safely_skipped_at_apply(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Vanished"
    folder.mkdir()
    book_path = folder / "Gone.epub"
    book_path.write_bytes(b"book")
    database = DatabaseManager(tmp_path / "vanished.db")
    service = _service(database)
    source = service.add_source(folder, display_name="Vanished")
    preview = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )
    book_path.unlink()

    result = service.apply_analysis(
        preview,
        is_cancelled=lambda: False,
    )

    assert result.status == ScanApplyStatus.APPLIED
    assert result.applied_new_count == 0
    assert len(result.safely_skipped) == 1
    assert "no longer readable" in result.safely_skipped[0].reason
    assert database.count_books(include_missing=True) == 0
    history = database.list_scan_history(source.source_id)[0]
    assert history["safely_skipped_count"] == 1


def test_reappeared_missing_file_is_not_marked_missing(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Reappeared"
    folder.mkdir()
    book_path = folder / "Book.txt"
    book_path.write_bytes(b"book")
    database = DatabaseManager(tmp_path / "reappeared.db")
    service = _service(database)
    source = service.add_source(folder, display_name="Reappeared")
    database.save_scan_results(folder, [_book(book_path)])
    original = book_path.read_bytes()
    book_path.unlink()
    preview = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )
    book_path.write_bytes(original)

    result = service.apply_analysis(
        preview,
        is_cancelled=lambda: False,
    )

    assert result.applied_missing_count == 0
    assert len(result.safely_skipped) == 1
    assert "reappeared" in result.safely_skipped[0].reason
    assert database.count_books() == 1


def test_cancelled_apply_records_history_without_changing_books(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Cancel"
    folder.mkdir()
    (folder / "Book.epub").write_bytes(b"book")
    database = DatabaseManager(tmp_path / "cancel.db")
    service = _service(database)
    source = service.add_source(folder, display_name="Cancel")
    preview = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )

    result = service.apply_analysis(
        preview,
        is_cancelled=lambda: True,
    )

    assert result.status == ScanApplyStatus.CANCELLED
    assert not result.changed_catalogue
    assert database.count_books(include_missing=True) == 0
    history = database.list_scan_history(source.source_id)
    assert len(history) == 1
    assert history[0]["status"] == "cancelled"
    assert database.get_library_source(
        source.source_id
    )["last_scanned_at"] is None


def test_database_apply_rolls_back_books_and_history_on_error(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Rollback"
    folder.mkdir()
    database = DatabaseManager(tmp_path / "rollback.db")
    source = _service(database).add_source(
        folder,
        display_name="Rollback",
    )
    valid_change = {
        "status": "new",
        "file_path": str(folder / "First.epub"),
        "file_name": "First.epub",
        "title": "First",
        "author": None,
        "isbn": None,
        "publisher": None,
        "language": None,
        "published_date": None,
        "file_format": "EPUB",
        "file_size": 1,
        "file_modified_at": "now",
        "file_fingerprint": "1:1",
        "metadata_status": "unavailable",
    }
    invalid_change = dict(valid_change)
    invalid_change["file_path"] = None
    invalid_change["file_name"] = "Broken.epub"

    with pytest.raises(Exception):
        database.apply_scan_preview(
            source_id=source.source_id,
            scan_token="rollback-token",
            started_at="2026-07-28T00:00:00+00:00",
            finished_at="2026-07-28T00:00:01+00:00",
            duration_ms=1000,
            preview_counts={"new": 2, "discovered": 2},
            changes=[valid_change, invalid_change],
            safely_skipped_count=0,
        )

    assert database.count_books(include_missing=True) == 0
    assert database.list_scan_history(source.source_id) == []


def test_scan_page_applies_preview_and_refreshes_history(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    folder = tmp_path / "UI"
    folder.mkdir()
    (folder / "New.epub").write_bytes(b"new")
    database_path = tmp_path / "ui.db"
    factory = lambda: ScanService(
        DatabaseManager(database_path),
        ProviderManager(),
    )
    page = ScanPage(factory)
    source = page.source_service.add_source(folder, display_name="UI")
    page.refresh_sources(source.source_id)
    changed = []
    page.catalogue_changed.connect(lambda: changed.append(True))
    monkeypatch.setattr(
        "ui.scan_page.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    page._start_scan()
    _wait_until(lambda: page.analysis_thread is None)
    assert page.apply_button.isEnabled()
    page.apply_button.click()
    _wait_until(lambda: page.apply_thread is None)

    assert DatabaseManager(database_path).count_books() == 1
    assert changed == [True]
    assert page.current_analysis is None
    assert page.results_table.item(0, 0).text() == "Applied — New"
    assert page.history_table.rowCount() == 1
    assert page.history_table.item(0, 1).text() == "Applied"
    assert "Apply complete" in page.status_label.text()
    assert not page.apply_button.isEnabled()
    page.deleteLater()
    application.processEvents()


def test_same_preview_token_cannot_be_applied_twice(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Token"
    folder.mkdir()
    (folder / "Book.epub").write_bytes(b"book")
    database = DatabaseManager(tmp_path / "token.db")
    service = _service(database)
    source = service.add_source(folder, display_name="Token")
    preview = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )

    service.apply_analysis(preview, is_cancelled=lambda: False)
    with pytest.raises(ValueError, match="already been handled"):
        service.apply_analysis(preview, is_cancelled=lambda: False)

    assert database.count_books(include_missing=True) == 1
    assert len(database.list_scan_history(source.source_id)) == 1


def test_source_rule_change_invalidates_preview_before_apply(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Changed Rules"
    folder.mkdir()
    (folder / "Book.epub").write_bytes(b"book")
    database = DatabaseManager(tmp_path / "rules.db")
    service = _service(database)
    source = service.add_source(folder, display_name="Rules")
    preview = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )
    service.update_source(
        source.source_id,
        display_name="Rules",
        include_subfolders=False,
        include_patterns="*.epub",
        exclude_patterns=(),
    )

    with pytest.raises(ValueError, match="settings changed"):
        service.apply_analysis(preview, is_cancelled=lambda: False)

    assert database.count_books(include_missing=True) == 0
    history = database.list_scan_history(source.source_id)
    assert len(history) == 1
    assert history[0]["status"] == "failed"


def test_apply_worker_pre_cancel_records_safe_terminal_outcome(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "Worker Cancel"
    folder.mkdir()
    (folder / "Book.epub").write_bytes(b"book")
    database_path = tmp_path / "worker-cancel.db"
    service = _service(DatabaseManager(database_path))
    source = service.add_source(folder, display_name="Worker Cancel")
    preview = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )
    worker = ScanApplyWorker(
        preview,
        lambda: _service(DatabaseManager(database_path)),
    )
    cancelled = []
    finished = []
    worker.cancelled.connect(cancelled.append)
    worker.finished.connect(lambda: finished.append(True))

    worker.request_cancel()
    worker.run()

    assert len(cancelled) == 1
    assert cancelled[0].status == ScanApplyStatus.CANCELLED
    assert finished == [True]
    database = DatabaseManager(database_path)
    assert database.count_books(include_missing=True) == 0
    assert database.list_scan_history(source.source_id)[0]["status"] == (
        "cancelled"
    )

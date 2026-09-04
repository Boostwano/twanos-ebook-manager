"""Tests for scan worker and QThread lifecycle stabilisation."""

from pathlib import Path
from time import monotonic, sleep

from PySide6.QtWidgets import QApplication

from database.database import DatabaseManager
from services.scan_service import ScanService
from ui.scan_page import ScanPage
from workers.scan_worker import ScanWorker


def wait_until(predicate, timeout: float = 3.0) -> None:
    """Process Qt events until a condition is true or the timeout expires."""
    deadline = monotonic() + timeout
    application = QApplication.instance()

    while monotonic() < deadline:
        application.processEvents()
        if predicate():
            return
        sleep(0.01)

    raise AssertionError("Timed out waiting for Qt lifecycle event")


def scan_service_factory(tmp_path: Path):
    """Create scan services using an isolated database."""
    database_path = tmp_path / "scan.db"
    return lambda: ScanService(DatabaseManager(database_path))


def test_scan_page_can_run_two_scans(tmp_path: Path) -> None:
    """A completed scan releases its objects and permits another scan."""
    application = QApplication.instance() or QApplication([])
    page = ScanPage(scan_service_factory(tmp_path))
    page.selected_folder = tmp_path
    page.scan_button.setEnabled(True)

    for _ in range(2):
        page._start_scan()
        assert page.scan_thread is not None
        assert not page.select_button.isEnabled()

        wait_until(lambda: page.scan_thread is None)

        assert page.scan_worker is None
        assert page.select_button.isEnabled()
        assert page.scan_button.isEnabled()
        assert not page.cancel_button.isEnabled()

    page.deleteLater()
    application.processEvents()


def test_scan_controls_restore_after_worker_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """An invalid scan folder still shuts down and restores controls."""
    application = QApplication.instance() or QApplication([])
    page = ScanPage(scan_service_factory(tmp_path))
    page.selected_folder = tmp_path / "missing"
    page.scan_button.setEnabled(True)

    monkeypatch.setattr(
        "ui.scan_page.QMessageBox.critical",
        lambda *args, **kwargs: None,
    )

    page._start_scan()
    wait_until(lambda: page.scan_thread is None)

    assert page.scan_worker is None
    assert page.select_button.isEnabled()
    assert page.scan_button.isEnabled()
    assert not page.cancel_button.isEnabled()
    assert page.status_label.text() == "Scan failed."

    page.deleteLater()
    application.processEvents()


def test_cancellation_does_not_block_gui_thread(tmp_path: Path) -> None:
    """Cancellation completes asynchronously and releases scan objects."""
    application = QApplication.instance() or QApplication([])
    page = ScanPage(scan_service_factory(tmp_path))
    page.selected_folder = tmp_path
    page.scan_button.setEnabled(True)
    page._start_scan()

    page.cancel_active_scan()
    wait_until(lambda: page.scan_thread is None)

    assert page.scan_thread is None
    assert page.scan_worker is None
    assert page.select_button.isEnabled()
    assert page.scan_button.isEnabled()
    assert not page.cancel_button.isEnabled()

    page.deleteLater()
    application.processEvents()


def test_worker_emits_cancelled_and_finished(tmp_path: Path) -> None:
    """A cancellation request always reaches the terminal worker signal."""
    worker = ScanWorker(tmp_path, scan_service_factory(tmp_path))
    cancelled = []
    finished = []

    worker.cancelled.connect(
        lambda processed, total: cancelled.append((processed, total))
    )
    worker.finished.connect(lambda: finished.append(True))

    worker.request_cancel()
    worker.run()

    assert cancelled == [(0, 0)]
    assert finished == [True]


def test_worker_commits_before_completed_signal(
    tmp_path: Path,
) -> None:
    """Completion observers can immediately read committed scan results."""
    library_folder = tmp_path / "books"
    library_folder.mkdir()
    (library_folder / "Example.txt").write_text(
        "example",
        encoding="utf-8",
    )
    database = DatabaseManager(tmp_path / "library.db")
    worker = ScanWorker(
        library_folder,
        lambda: ScanService(database),
    )
    visible_counts = []
    worker.completed.connect(
        lambda *_args: visible_counts.append(database.count_books())
    )

    worker.run()

    assert visible_counts == [1]

"""Capture deterministic RC6.6 watched-source milestone screenshots."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, sleep
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from database.database import DatabaseManager  # noqa: E402
from core.scanner import BookFile  # noqa: E402
from main_window import MainWindow  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from services.dashboard_service import DashboardService  # noqa: E402
from services.library_service import LibraryService  # noqa: E402
from services.protection_service import ProtectionService  # noqa: E402
from services.scan_service import ScanService  # noqa: E402


def _wait(application: QApplication, predicate, timeout: float = 5.0) -> None:
    deadline = perf_counter() + timeout
    while not predicate() and perf_counter() < deadline:
        application.processEvents()
        sleep(0.01)
    application.processEvents()
    if not predicate():
        raise RuntimeError("RC6.6 source smoke operation timed out.")


def _book(path: Path) -> BookFile:
    return BookFile(
        name=path.stem,
        extension=path.suffix.removeprefix(".").upper(),
        size_bytes=path.stat().st_size,
        path=path,
    )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: capture_rc6_6_sources.py OUTPUT_FOLDER")
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    application = QApplication.instance() or QApplication([])

    with TemporaryDirectory(
        prefix="Twano-RC66-sources-",
        ignore_cleanup_errors=True,
    ) as temp:
        folder = Path(temp)
        database_path = folder / "sources.db"
        database = DatabaseManager(database_path)
        settings = QSettings(
            str(folder / "settings.ini"),
            QSettings.Format.IniFormat,
        )
        factory = lambda: ScanService(DatabaseManager(database_path))
        window = MainWindow(
            library_service=LibraryService(database),
            dashboard_service=DashboardService(database),
            preferences=PreferencesStore(settings),
            scan_service_factory=factory,
            protection_service_factory=lambda: ProtectionService(
                DatabaseManager(database_path)
            ),
        )
        service = window.scan_page.source_service

        available_folder = folder / "Main Library"
        disabled_folder = folder / "Archive"
        available_folder.mkdir()
        disabled_folder.mkdir()
        unchanged_path = available_folder / "Unchanged.epub"
        changed_path = available_folder / "Changed.pdf"
        missing_path = available_folder / "Missing.mobi"
        for path, content in (
            (unchanged_path, b"unchanged"),
            (changed_path, b"before"),
            (missing_path, b"missing"),
        ):
            path.write_bytes(content)
        available = service.add_source(
            available_folder,
            display_name="Main Library",
            exclude_patterns="Temp/**; **/Drafts/**",
        )
        database.save_scan_results(
            available_folder,
            [
                _book(unchanged_path),
                _book(changed_path),
                _book(missing_path),
            ],
        )
        changed_path.write_bytes(b"changed and larger")
        missing_path.unlink()
        (available_folder / "New.epub").write_bytes(b"new")
        (available_folder / "Unsupported.docx").write_bytes(b"skip")
        service.test_source(available.source_id)
        unavailable = service.add_source(
            folder / "Disconnected Drive",
            display_name="Disconnected Drive",
            include_subfolders=False,
        )
        service.test_source(unavailable.source_id)
        disabled = service.add_source(
            disabled_folder,
            display_name="Archive",
        )
        service.set_source_enabled(disabled.source_id, False)

        window.scan_page.refresh_sources(available.source_id)
        window.resize(1180, 790)
        window.show()
        window._show_page("scan")
        application.processEvents()
        window.grab().save(
            str(output / "rc6-6-watched-sources-restored.png")
        )

        window.resize(1000, 720)
        application.processEvents()
        window.grab().save(
            str(output / "rc6-6-watched-sources-compact.png")
        )

        window.resize(1180, 790)
        application.processEvents()
        window.scan_page._start_scan()
        _wait(
            application,
            lambda: window.scan_page.analysis_thread is None,
        )
        window.grab().save(
            str(output / "rc6-6-safe-preview-restored.png")
        )

        window.resize(1000, 720)
        application.processEvents()
        window.grab().save(
            str(output / "rc6-6-safe-preview-compact.png")
        )

        analysis = window.scan_page.current_analysis
        if analysis is None:
            raise RuntimeError("Safe Preview did not produce an analysis.")
        window.resize(1180, 790)
        window.scan_page._start_apply(analysis)
        _wait(
            application,
            lambda: window.scan_page.apply_thread is None,
        )
        window.scan_page.scan_tabs.setCurrentWidget(
            window.scan_page.history_tab
        )
        application.processEvents()
        window.grab().save(
            str(output / "rc6-6-apply-history-restored.png")
        )

        window.resize(1000, 720)
        window.scan_page.scan_tabs.setCurrentWidget(
            window.scan_page.history_tab
        )
        application.processEvents()
        window.grab().save(
            str(output / "rc6-6-apply-history-compact.png")
        )

        scan_operation = next(
            record
            for record in ProtectionService(
                DatabaseManager(database_path)
            ).list_operation_history()
            if record.plan.operation_type == "scan_apply"
        )
        window.resize(1180, 790)
        window._show_page("protection")
        window.protection_page.page_tabs.setCurrentWidget(
            window.protection_page.history_panel
        )
        window.protection_page.history_panel.show_operation(
            scan_operation.operation_id
        )
        application.processEvents()
        window.grab().save(
            str(output / "rc6-7-scan-protection-history-restored.png")
        )

        window.resize(1000, 720)
        application.processEvents()
        window.grab().save(
            str(output / "rc6-7-scan-protection-history-compact.png")
        )
        window.close()
        application.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

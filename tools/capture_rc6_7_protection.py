"""Capture deterministic RC6.7 Protection Centre screenshots."""

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
from main_window import MainWindow  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from services.dashboard_service import DashboardService  # noqa: E402
from services.library_service import LibraryService  # noqa: E402
from services.protection_models import PlanConfirmation  # noqa: E402
from services.protection_service import ProtectionService  # noqa: E402
from services.scan_service import ScanService  # noqa: E402


def _wait(application: QApplication, predicate, timeout: float = 5.0) -> None:
    deadline = perf_counter() + timeout
    while not predicate() and perf_counter() < deadline:
        application.processEvents()
        sleep(0.01)
    application.processEvents()
    if not predicate():
        raise RuntimeError("RC6.7 backup smoke operation timed out.")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: capture_rc6_7_protection.py OUTPUT_FOLDER"
        )
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    application = QApplication.instance() or QApplication([])

    with TemporaryDirectory(
        prefix="Twano-RC67-protection-",
        ignore_cleanup_errors=True,
    ) as temp:
        folder = Path(temp)
        database_path = folder / "library.db"
        database = DatabaseManager(database_path)
        database.create_collection("Favourites")
        settings = QSettings(
            str(folder / "settings.ini"),
            QSettings.Format.IniFormat,
        )
        protection_factory = lambda: ProtectionService(
            DatabaseManager(database_path)
        )
        window = MainWindow(
            library_service=LibraryService(database),
            dashboard_service=DashboardService(database),
            preferences=PreferencesStore(settings),
            scan_service_factory=lambda: ScanService(
                DatabaseManager(database_path)
            ),
            protection_service_factory=protection_factory,
        )
        page = window.protection_page
        page.backup_folder_edit.setText(str(folder / "Backups"))
        page.retention_days.setValue(0)

        window.resize(1180, 790)
        window.show()
        window._show_page("home")
        application.processEvents()
        window.grab().save(
            str(output / "home-restored.png")
        )

        window.resize(900, 600)
        application.processEvents()
        window.grab().save(
            str(output / "home-compact.png")
        )

        window.resize(1180, 790)
        window._show_page("protection")
        application.processEvents()
        page.page_tabs.setCurrentWidget(page.backup_tab)
        application.processEvents()
        window.grab().save(
            str(output / "rc6-7-protection-empty-restored.png")
        )

        page._create_backup()
        _wait(application, lambda: not page.is_busy())
        window.grab().save(
            str(output / "rc6-7-protection-verified-restored.png")
        )

        window.resize(900, 600)
        application.processEvents()
        window.grab().save(
            str(output / "rc6-7-protection-verified-compact.png")
        )

        window.resize(1180, 790)
        page.history_panel.preview_button.click()
        page.page_tabs.setCurrentWidget(page.history_panel)
        page.history_panel.view_tabs.setCurrentWidget(
            page.history_panel.plan_tab
        )
        application.processEvents()
        window.grab().save(
            str(output / "rc6-7-change-plan-preview-restored.png")
        )

        page.history_panel.cancel_plan_button.click()
        page.history_panel.view_tabs.setCurrentWidget(
            page.history_panel.history_tab
        )
        application.processEvents()
        window.grab().save(
            str(output / "rc6-7-operation-history-restored.png")
        )

        window.resize(900, 600)
        application.processEvents()
        window.grab().save(
            str(output / "rc6-7-operation-history-compact.png")
        )

        window.resize(1180, 790)
        page.history_panel.view_tabs.setCurrentWidget(
            page.history_panel.plan_tab
        )
        page.history_panel.reversible_button.click()
        application.processEvents()
        window.grab().save(
            str(output / "rc6-7-reversible-plan-restored.png")
        )

        record = page.history_panel.current_record
        approved = page.history_panel.service.approve_change_plan(
            record.operation_id,
            PlanConfirmation(
                plan_token=record.plan.plan_token,
                approved=True,
                confirmer="visual-check",
            ),
            current_basis_token=(
                page.history_panel.service.current_basis_token(record)
            ),
        )
        page.history_panel.current_record = approved
        page.history_panel._render_record(approved)
        page.history_panel.refresh_history(approved.operation_id)
        page.history_panel._start_execution(approved.operation_id)
        _wait(application, lambda: not page.is_busy())
        window.grab().save(
            str(output / "rc6-7-protected-apply-restored.png")
        )

        page.history_panel.undo_button.click()
        application.processEvents()
        window.grab().save(
            str(output / "rc6-7-undo-preview-restored.png")
        )
        undo = page.history_panel.current_record
        approved_undo = page.history_panel.service.approve_change_plan(
            undo.operation_id,
            PlanConfirmation(
                plan_token=undo.plan.plan_token,
                approved=True,
                confirmer="visual-check",
            ),
            current_basis_token=(
                page.history_panel.service.current_basis_token(undo)
            ),
        )
        page.history_panel.current_record = approved_undo
        page.history_panel._render_record(approved_undo)
        page.history_panel.refresh_history(approved_undo.operation_id)
        page.history_panel._start_execution(approved_undo.operation_id)
        _wait(application, lambda: not page.is_busy())
        window.resize(900, 600)
        application.processEvents()
        window.grab().save(
            str(output / "rc6-7-persistent-undo-compact.png")
        )
        window.close()
        application.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

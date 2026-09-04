"""Main application window for Twano's eBook Manager."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from config import APP_VERSION, RELEASE_NAME
from preferences import PreferencesStore, ProtectionMode
from services.dashboard_service import DashboardService
from services.diagnostic_report_service import DiagnosticReportService
from services.duplicate_service import DuplicateService
from services.integration_service import IntegrationService
from services.library_health_service import LibraryHealthService
from services.library_service import LibraryService
from services.metadata_studio_service import MetadataStudioService
from services.plugin_service import PluginService
from services.protection_service import ProtectionService
from services.scan_service import ScanService
from ui.dashboard import DashboardPage
from ui.branding import BRAND_TAGLINE
from ui.duplicate_page import DuplicatePage
from ui.guidance_pages import AboutPage, UserGuidePage, WhatsNewPage
from ui.library_health_page import LibraryHealthPage
from ui.library_page import LibraryPage
from ui.metadata_studio import MetadataStudioPage
from ui.plugin_page import PluginPage
from ui.protection_page import ProtectionPage
from ui.review_queue import ReviewQueuePage
from ui.scan_page import ScanPage
from ui.search_results import SearchResultsPage
from ui.settings import SettingsPage
from ui.sidebar import NAVIGATION_PAGE_IDS, ResponsiveSidebar
from ui.theme import APP_STYLESHEET


logger = logging.getLogger(__name__)

PAGE_IDS = (
    "home",
    "library",
    "search",
    "scan",
    "metadata",
    "review_queue",
    "duplicates",
    "protection",
    "library_health",
    "plugins",
    "settings",
    "user_guide",
    "whats_new",
    "about",
)


class MainWindow(QMainWindow):
    """Main window with stable page-ID based navigation."""

    def __init__(
        self,
        *,
        library_service: LibraryService | None = None,
        dashboard_service: DashboardService | None = None,
        preferences: PreferencesStore | None = None,
        scan_service_factory: Callable[[], ScanService] | None = None,
        protection_service_factory: (
            Callable[[], ProtectionService] | None
        ) = None,
    ) -> None:
        super().__init__()

        self.setWindowTitle(
            f"Twano's eBook Manager — {BRAND_TAGLINE}"
        )
        self.preferences = preferences or PreferencesStore()
        self.library_service = library_service or LibraryService()
        self.dashboard_service = dashboard_service or DashboardService()
        self.scan_service_factory = scan_service_factory or ScanService
        self.protection_service_factory = (
            protection_service_factory or ProtectionService
        )
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self._current_page_id = ""
        self._close_when_idle = False
        self._restore_navigation_locked = False

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = ResponsiveSidebar()
        self.sidebar.set_protection_mode(
            self.preferences.load_home_preferences().protection_mode
        )
        self.sidebar.page_requested.connect(self._change_page)
        self.sidebar.diagnostic_report_requested.connect(
            self._generate_diagnostic_report
        )

        self.pages = QStackedWidget()
        self.pages_by_id: dict[str, QWidget] = {}

        self.dashboard_page = DashboardPage(
            self.dashboard_service,
            self.preferences,
            library_service=self.library_service,
        )
        self.dashboard_page.open_library_requested.connect(
            self._open_library_search
        )
        self.dashboard_page.search_requested.connect(
            self._open_search_results
        )
        self.dashboard_page.scan_requested.connect(
            lambda: self._show_page("scan")
        )
        self.dashboard_page.metadata_requested.connect(
            lambda: self._show_page("metadata")
        )
        self.dashboard_page.review_queue_requested.connect(
            self._open_metadata_review_queue
        )
        self.dashboard_page.health_requested.connect(
            lambda: self._show_page("library_health")
        )
        self.dashboard_page.settings_requested.connect(
            lambda: self._show_page("settings")
        )
        self._register_page("home", self.dashboard_page)

        self.library_page = LibraryPage(
            self.library_service,
            self.preferences,
        )
        self.library_page.edit_metadata_requested.connect(
            self._open_metadata_book
        )
        self.library_page.review_issues_requested.connect(
            self._open_library_review_issues
        )
        self._register_page("library", self.library_page)

        self.search_results_page = SearchResultsPage(
            self.library_service,
            self.preferences,
        )
        self.search_results_page.view_in_library_requested.connect(
            self._open_library_search
        )
        self._register_page("search", self.search_results_page)

        self.scan_page = ScanPage(
            self.scan_service_factory,
            self.preferences,
        )
        self.scan_page.scan_stopped.connect(self._on_scan_stopped)
        self.scan_page.catalogue_changed.connect(
            self.library_page.refresh_library_data
        )
        self.scan_page.catalogue_changed.connect(
            self.dashboard_page.refresh_dashboard
        )
        self.scan_page.catalogue_changed.connect(
            self._refresh_application_status
        )
        self.scan_page.catalogue_changed.connect(
            self._relink_missing_books_from_destination
        )
        self._register_page("scan", self.scan_page)

        metadata_protection_service = self.protection_service_factory()
        self.plugin_service = PluginService()
        self.metadata_page = MetadataStudioPage(
            MetadataStudioService(
                database=metadata_protection_service.database,
                library_service=self.library_service,
                protection_service=metadata_protection_service,
                plugin_service=self.plugin_service,
            ),
            self.preferences,
            self.protection_service_factory,
        )
        self.metadata_page.catalogue_changed.connect(
            self.library_page.refresh_library_data
        )
        self.metadata_page.book_updated.connect(
            self.library_page.reveal_book_after_update
        )
        self.metadata_page.catalogue_changed.connect(
            self.dashboard_page.refresh_dashboard
        )
        self.metadata_page.catalogue_changed.connect(
            self._refresh_application_status
        )
        self.metadata_page.review_queue_requested.connect(
            self._open_metadata_review_queue
        )
        self.metadata_page.work_stopped.connect(
            self._on_background_work_stopped
        )
        self._register_page("metadata", self.metadata_page)

        self.review_queue_page = ReviewQueuePage(
            self.library_service,
            self.preferences,
        )
        self.review_queue_page.review_requested.connect(
            self._open_metadata_book
        )
        self.review_queue_page.view_in_library_requested.connect(
            self._open_library_search
        )
        self._register_page("review_queue", self.review_queue_page)

        self.duplicate_page = DuplicatePage(
            DuplicateService(metadata_protection_service.database)
        )
        self.duplicate_page.catalogue_changed.connect(
            self.library_page.refresh_library_data
        )
        self.duplicate_page.catalogue_changed.connect(
            self.dashboard_page.refresh_dashboard
        )
        self.duplicate_page.catalogue_changed.connect(
            self._refresh_application_status
        )
        self.duplicate_page.view_in_library_requested.connect(
            self._open_library_search
        )
        self.duplicate_page.metadata_requested.connect(
            self._open_metadata_book
        )
        self.duplicate_page.work_stopped.connect(
            self._on_background_work_stopped
        )
        self._register_page("duplicates", self.duplicate_page)

        self.protection_page = ProtectionPage(
            self.preferences,
            self.protection_service_factory,
            self._database_work_idle,
        )
        self.protection_page.backup_stopped.connect(
            self._on_background_work_stopped
        )
        self.protection_page.catalogue_changed.connect(
            self.library_page.refresh_library_data
        )
        self.protection_page.catalogue_changed.connect(
            self.dashboard_page.refresh_dashboard
        )
        self.protection_page.catalogue_changed.connect(
            self._refresh_application_status
        )
        self.protection_page.catalogue_restored.connect(
            self._catalogue_restored
        )
        self.protection_page.database_replacement_active.connect(
            self._set_restore_navigation_locked
        )
        self._register_page("protection", self.protection_page)

        self.library_health_page = LibraryHealthPage(
            LibraryHealthService(metadata_protection_service.database),
            self.library_service,
        )
        self.library_health_page.destination_requested.connect(
            self._show_page
        )
        self.library_health_page.catalogue_changed.connect(
            self.library_page.refresh_library_data
        )
        self.library_health_page.catalogue_changed.connect(
            self.dashboard_page.refresh_dashboard
        )
        self._register_page("library_health", self.library_health_page)

        self.plugin_page = PluginPage(
            self.plugin_service,
            IntegrationService(),
        )
        self.plugin_page.scan_source_requested.connect(
            self._add_routed_scan_source
        )
        self._register_page("plugins", self.plugin_page)

        self.settings_page = SettingsPage(self.preferences)
        self.settings_page.preferences_changed.connect(
            self.dashboard_page.refresh_dashboard
        )
        self.settings_page.protection_mode_changed.connect(
            self._set_protection_mode
        )
        self.settings_page.destination_folder_changed.connect(
            self._relink_missing_books_from_destination
        )
        self._register_page("settings", self.settings_page)

        self._register_page("user_guide", UserGuidePage())
        self._register_page("whats_new", WhatsNewPage())
        self._register_page("about", AboutPage())

        if tuple(self.pages_by_id) != PAGE_IDS:
            raise RuntimeError("MainWindow page registration is incomplete")
        if not set(NAVIGATION_PAGE_IDS).issubset(self.pages_by_id):
            raise RuntimeError("Sidebar contains an unregistered page ID")

        root_layout.addWidget(self.sidebar)
        root_layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self._create_application_status_bar()
        self._apply_styles()
        self._update_responsive_sidebar()
        self._refresh_application_status()
        self._show_page("home")
        if (
            self.preferences.load_general_preferences()
            .check_updates_on_startup
        ):
            QTimer.singleShot(750, self._show_update_status)

    def _create_application_status_bar(self) -> None:
        """Create the quiet whole-window status strip from the reference UI."""
        status_bar = QStatusBar()
        status_bar.setObjectName("applicationStatusBar")
        status_bar.setSizeGripEnabled(False)
        self.setStatusBar(status_bar)

        self.status_library_label = QLabel("No library yet")
        self.status_library_label.setObjectName("statusLibrary")
        self.status_book_count_label = QLabel("0 books")
        self.status_book_count_label.setObjectName("statusBookCount")
        self.status_version_label = QLabel(APP_VERSION)
        self.status_version_label.setObjectName("statusVersion")
        self.status_version_label.setToolTip(RELEASE_NAME)

        self.status_update_button = QPushButton("↻  Check for Updates")
        self.status_update_button.setObjectName("footerUpdateAction")
        self.status_update_button.setToolTip(
            "Check whether a newer supported Twano release is available."
        )
        self.status_update_button.clicked.connect(
            self._show_update_status
        )

        for _index, widget in enumerate(
            (
                self.status_library_label,
                self.status_book_count_label,
                self.status_version_label,
            )
        ):
            if _index:
                separator = QFrame()
                separator.setObjectName("statusSeparator")
                separator.setFrameShape(QFrame.Shape.VLine)
                status_bar.addPermanentWidget(separator)
            status_bar.addPermanentWidget(widget)

        status_bar.addPermanentWidget(self.status_update_button)
        ready_dot = QLabel("●")
        ready_dot.setObjectName("statusReady")
        ready_dot.setToolTip("Twano is ready.")
        status_bar.addPermanentWidget(ready_dot)

    def _refresh_application_status(self) -> None:
        """Refresh library name and book count without exposing technical data."""
        if not hasattr(self, "status_library_label"):
            return
        try:
            snapshot = self.dashboard_service.get_dashboard_data()
        except Exception:
            logger.exception("Unable to refresh the application status strip")
            self.status_library_label.setText("Library unavailable")
            self.status_book_count_label.setText("— books")
            return

        locations = snapshot.library_locations
        if len(locations) == 1:
            name = Path(locations[0]).name or locations[0]
        elif len(locations) > 1:
            name = f"{len(locations):,} library locations"
        else:
            name = "No library yet"
        noun = "book" if snapshot.total_books == 1 else "books"
        self.status_library_label.setText(name)
        self.status_library_label.setToolTip(
            locations[0] if len(locations) == 1 else ""
        )
        self.status_book_count_label.setText(
            f"{snapshot.total_books:,} {noun}"
        )

    def _register_page(self, page_id: str, page: QWidget) -> None:
        if page_id not in PAGE_IDS:
            raise ValueError(f"Unknown page ID: {page_id}")
        if page_id in self.pages_by_id:
            raise ValueError(f"Duplicate page ID: {page_id}")
        self.pages_by_id[page_id] = page
        self.pages.addWidget(page)

    def _show_page(self, page_id: str) -> None:
        """Route visible destinations through the sidebar when possible."""
        if page_id not in self.pages_by_id:
            raise ValueError(f"Unknown page ID: {page_id}")
        previous_id = self._current_page_id
        if self.sidebar.select_page(page_id):
            if self._current_page_id != page_id:
                self._change_page(page_id)
            elif previous_id == page_id:
                self._change_page(page_id)
        else:
            self.sidebar.clear_selection()
            self._change_page(page_id)

    def _change_page(self, page_id: str) -> None:
        if self._restore_navigation_locked and page_id != "protection":
            return
        page = self.pages_by_id.get(page_id)
        if page is None:
            logger.warning("Ignoring unknown page ID %s", page_id)
            return

        if self._current_page_id == "home" and page_id != "home":
            self.dashboard_page.deactivate()

        self.pages.setCurrentWidget(page)
        self._current_page_id = page_id

        if page_id == "home":
            self.dashboard_page.activate()
        elif page_id == "library":
            logger.info("Navigating to Library page")
            self.library_page.activate()
        elif page_id == "search":
            self.search_results_page.activate()
        elif page_id == "review_queue":
            self.review_queue_page.activate(metadata_only=True)
        elif page_id == "metadata":
            self.metadata_page.activate()
        elif page_id == "duplicates":
            self.duplicate_page.activate()
        elif page_id == "protection":
            self.protection_page.activate()
        elif page_id == "library_health":
            self.library_health_page.activate()
        elif page_id == "plugins":
            self.plugin_page.activate()

    def _database_work_idle(self) -> bool:
        """Allow live replacement only after other SQLite workers finish."""
        return (
            not self.scan_page.is_scanning()
            and not self.library_page.has_active_database_work()
            and (
                not hasattr(self, "metadata_page")
                or not self.metadata_page.is_busy()
            )
            and (
                not hasattr(self, "duplicate_page")
                or not self.duplicate_page.is_busy()
            )
            and (
                not hasattr(self, "protection_page")
                or self.protection_page.backup_thread is None
            )
        )

    def _set_restore_navigation_locked(self, locked: bool) -> None:
        """Keep the user on Protection while the live catalogue is replaced."""
        self._restore_navigation_locked = bool(locked)
        self.sidebar.setEnabled(not locked)

    def _catalogue_restored(self) -> None:
        """Refresh every page whose detached data came from the catalogue."""
        self.library_page.refresh_library_data()
        self.dashboard_page.refresh_dashboard()
        self.scan_page.refresh_sources()
        self.review_queue_page.refresh()
        self.search_results_page.activate()
        self.metadata_page.refresh()
        self.library_health_page.refresh()
        self._refresh_application_status()

    def _set_protection_mode(self, mode: ProtectionMode) -> None:
        self.sidebar.set_protection_mode(mode)
        self.scan_page.set_protection_mode(mode)

    def _generate_diagnostic_report(self) -> None:
        """Build a redacted diagnostic report and let the user save it."""
        protection_service = self.protection_service_factory()
        scan_service = self.scan_service_factory()
        report_service = DiagnosticReportService(
            database=protection_service.database,
            plugin_service=self.plugin_service,
            scan_service=scan_service,
            dashboard_service=self.dashboard_service,
            preferences=self.preferences,
        )
        try:
            report_text = report_service.generate_report()
        except Exception as error:
            QMessageBox.warning(
                self,
                "Diagnostic Report",
                f"Twano could not build the diagnostic report.\n\n{error}",
            )
            return

        default_name = (
            "Twano-Diagnostic-Report-"
            f"{datetime.now().strftime('%Y-%m-%d-%H%M')}.txt"
        )
        desktop = Path.home() / "Desktop"
        default_path = str(
            (desktop if desktop.is_dir() else Path.home()) / default_name
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Diagnostic Report",
            default_path,
            "Text Files (*.txt)",
        )
        if not file_path:
            return
        try:
            Path(file_path).write_text(report_text, encoding="utf-8")
        except OSError as error:
            QMessageBox.warning(
                self,
                "Diagnostic Report",
                f"Twano could not save the report.\n\n{error}",
            )
            return
        QMessageBox.information(
            self,
            "Diagnostic Report Saved",
            f"Saved to:\n{file_path}\n\n"
            "You can attach this file when reporting a problem. It has "
            "been checked to avoid including your Windows account name or "
            "real folder paths, and does not include any book titles, "
            "authors, or API keys.",
        )

    def _relink_missing_books_from_destination(
        self,
        new_destination: str | None = None,
    ) -> None:
        """Search the destination folder for already-relocated books.

        Runs both when the destination folder setting is saved and after
        every scan/apply. A book only becomes "missing" once a scan of its
        original watched source notices the file is gone — if that happens
        after the destination was last saved (e.g. the user moved files
        first and scanned later), the setting-save trigger alone would
        never see it, leaving it missing forever. Re-checking after every
        scan closes that gap.
        """
        destination = new_destination or (
            self.preferences.load_organization_preferences()
            .destination_folder
        )
        if not destination:
            return
        summary = self.library_service.relink_missing_books_from(
            destination
        )
        if not summary.relinked_book_ids:
            return
        self.library_page.refresh_library_data()
        self.dashboard_page.refresh_dashboard()
        count = len(summary.relinked_book_ids)
        message = (
            f"Found {count} book{'s' if count != 1 else ''} already in "
            "that folder and cleared their missing status."
        )
        if summary.still_missing_count:
            message += (
                f" {summary.still_missing_count} other book"
                f"{'s' if summary.still_missing_count != 1 else ''} "
                "remain missing."
            )
        QMessageBox.information(self, "Missing Books Found", message)

    def _show_update_status(self) -> None:
        """Report the honest update boundary for this test build."""
        QMessageBox.information(
            self,
            "Check for Updates",
            f"{APP_VERSION} — {RELEASE_NAME} is installed.\n\n"
            "This test package is current. Online installation is disabled "
            "until release metadata can be signed; the footer check remains "
            "the safe update-status entry point.",
        )

    def _open_library_search(self, search_text: str) -> None:
        """Open Library and carry a routed result into its filter."""
        self._show_page("library")
        self.library_page.apply_search(search_text)

    def _open_search_results(self, query: str) -> None:
        """Open the dedicated Search Results page for any submitted query."""
        self.search_results_page.set_query(query)
        self._show_page("search")

    def _open_metadata_review_queue(self) -> None:
        """Open the queue already constrained to metadata attention."""
        self._show_page("review_queue")

    def _open_library_review_issues(self, _title: str) -> None:
        """Route Library issue review to the existing protected queue."""
        self._show_page("review_queue")

    def _open_metadata_book(self, title: str) -> None:
        """Carry a review row into the existing Metadata destination."""
        self._show_page("metadata")
        self.metadata_page.set_context(title)

    def _add_routed_scan_source(self, folder_path: str) -> None:
        """Carry an approved Calibre or network location into Scan."""
        self._show_page("scan")
        self.scan_page.add_source_path(folder_path)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_responsive_sidebar()

    def _update_responsive_sidebar(self) -> None:
        if hasattr(self, "sidebar"):
            footer_height = (
                self.statusBar().height()
                if self.statusBar() is not None
                else 0
            )
            self.sidebar.apply_responsive_size(
                self.width(),
                max(0, self.height() - footer_height),
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Cancel active work and close after its thread exits."""
        background_work_active = False
        if self.scan_page.is_scanning():
            background_work_active = True
            self.scan_page.cancel_active_scan()
        if self.protection_page.is_busy():
            background_work_active = True
            self.protection_page.cancel_active_operation()
        if self.metadata_page.is_busy():
            background_work_active = True
            self.metadata_page.cancel_active_operation()
        if self.duplicate_page.is_busy():
            background_work_active = True
        if background_work_active:
            self._close_when_idle = True
            event.ignore()
            return
        self._close_when_idle = False
        super().closeEvent(event)

    def _on_scan_stopped(self) -> None:
        """Retry a deferred close without waiting on the GUI thread."""
        self._on_background_work_stopped()

    def _on_background_work_stopped(self) -> None:
        """Retry close after either background subsystem becomes idle."""
        if self._close_when_idle:
            QTimer.singleShot(0, self.close)

    def _apply_styles(self) -> None:
        self.setStyleSheet(APP_STYLESHEET)

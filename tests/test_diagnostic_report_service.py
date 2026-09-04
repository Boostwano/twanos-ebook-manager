"""The Diagnostic Report never leaks real paths, usernames, or API keys."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from database.database import DatabaseManager
from preferences import OrganizationPreferences, PreferencesStore
from services.dashboard_service import DashboardService
from services.diagnostic_report_service import DiagnosticReportService
from services.plugin_service import PluginService
from services.scan_service import ScanService


class _MemoryCredentials:
    """A credential store that never touches Windows DPAPI, for tests."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def save(self, plugin_id: str, value: str) -> None:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Enter an API key before choosing Save.")
        self.values[plugin_id] = cleaned

    def load(self, plugin_id: str) -> str:
        return self.values.get(plugin_id, "")

    def has(self, plugin_id: str) -> bool:
        return bool(self.load(plugin_id))

    def entry_exists(self, plugin_id: str) -> bool:
        return plugin_id in self.values

    def delete(self, plugin_id: str) -> None:
        self.values.pop(plugin_id, None)


def _store(tmp_path: Path) -> PreferencesStore:
    settings = QSettings(
        str(tmp_path / "preferences.ini"),
        QSettings.Format.IniFormat,
    )
    return PreferencesStore(settings)


def _plugin_service(tmp_path: Path) -> PluginService:
    return PluginService(
        tmp_path / "plugins",
        tmp_path / "plugin-state.json",
        credential_store=_MemoryCredentials(),
    )


def test_report_replaces_real_paths_with_generic_labels(
    tmp_path: Path,
) -> None:
    watched = tmp_path / "MySecretBooks"
    watched.mkdir()
    destination = tmp_path / "MyOrganisedBooks"
    backup = tmp_path / "MyBackups"

    database = DatabaseManager(tmp_path / "library.db")
    scan_service = ScanService(database)
    scan_service.add_source(watched, display_name="Books")

    preferences = _store(tmp_path)
    preferences.save_organization_preferences(
        OrganizationPreferences(destination_folder=str(destination))
    )
    protection = preferences.load_protection_preferences()
    from preferences import ProtectionPreferences

    preferences.save_protection_preferences(
        ProtectionPreferences(
            backup_folder=str(backup),
            retention_days=protection.retention_days,
        )
    )

    service = DiagnosticReportService(
        database=database,
        plugin_service=_plugin_service(tmp_path),
        scan_service=scan_service,
        dashboard_service=DashboardService(database),
        preferences=preferences,
        log_path=tmp_path / "no-such-log.log",
    )

    report = service.generate_report()

    assert "MySecretBooks" not in report
    assert "MyOrganisedBooks" not in report
    assert "MyBackups" not in report
    assert str(tmp_path) not in report
    assert "[WATCHED_SOURCE_1]" in report
    assert "[DESTINATION_FOLDER]" in report
    assert "[BACKUP_FOLDER]" in report


def test_report_never_includes_api_key_values(tmp_path: Path) -> None:
    database = DatabaseManager(tmp_path / "library.db")
    plugins = _plugin_service(tmp_path)
    plugins.install_builtin("google_books_covers")
    secret_key = "AIzaSySuperSecretKeyValueShouldNeverAppear12345"
    plugins.set_api_key("google_books_covers", secret_key)
    plugins.set_enabled("google_books_covers", True)

    service = DiagnosticReportService(
        database=database,
        plugin_service=plugins,
        scan_service=ScanService(database),
        dashboard_service=DashboardService(database),
        preferences=_store(tmp_path),
        log_path=tmp_path / "no-such-log.log",
    )

    report = service.generate_report()

    assert secret_key not in report
    assert "key configured" in report


def test_report_includes_expected_sections(tmp_path: Path) -> None:
    database = DatabaseManager(tmp_path / "library.db")
    service = DiagnosticReportService(
        database=database,
        plugin_service=_plugin_service(tmp_path),
        scan_service=ScanService(database),
        dashboard_service=DashboardService(database),
        preferences=_store(tmp_path),
        log_path=tmp_path / "no-such-log.log",
    )

    report = service.generate_report()

    assert "Twano Diagnostic Report" in report
    assert "Application" in report
    assert "Library Summary" in report
    assert "Watched Sources" in report
    assert "Organisation & Protection Settings" in report
    assert "Plugins" in report
    assert "Recent Log Entries" in report
    assert "(no log file found)" in report


def test_report_scrubs_username_from_a_user_folder_path_in_log_lines(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "twano.log"
    username = Path.home().name
    original_path = f"C:\\Users\\{username}\\Documents\\Books\\x.epub"
    log_path.write_text(
        "2026-01-01 00:00:00 ERROR services.scan_service: "
        f"Could not read {original_path}\n",
        encoding="utf-8",
    )
    database = DatabaseManager(tmp_path / "library.db")
    service = DiagnosticReportService(
        database=database,
        plugin_service=_plugin_service(tmp_path),
        scan_service=ScanService(database),
        dashboard_service=DashboardService(database),
        preferences=_store(tmp_path),
        log_path=log_path,
    )

    report = service.generate_report()

    # The full home directory is already a registered label, so it takes
    # precedence over the standalone username pattern here...
    assert original_path not in report
    assert "[USER_HOME]\\Documents\\Books\\x.epub" in report
    # ...without mangling unrelated text that happens to contain the same
    # word (the account on this machine may coincide with the product's
    # own name).
    assert "Twano Diagnostic Report" in report


def test_username_pattern_scrubs_a_user_path_outside_the_registered_home(
    tmp_path: Path,
) -> None:
    """The standalone username fallback still fires outside Path.home()."""
    from services.diagnostic_report_service import _PathRedactor

    username = Path.home().name
    redactor = _PathRedactor()

    scrubbed = redactor.scrub(
        f"D:\\Users\\{username}\\Backups\\catalogue.sqlite3"
    )

    assert scrubbed == "D:\\Users\\[USER]\\Backups\\catalogue.sqlite3"
    # Unrelated text containing the same word is left alone.
    assert redactor.scrub("Twano Diagnostic Report") == (
        "Twano Diagnostic Report"
    )

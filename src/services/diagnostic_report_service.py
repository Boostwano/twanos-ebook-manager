"""Build a privacy-conscious diagnostic report the user can send along."""

from __future__ import annotations

import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import qVersion

from config import APP_VERSION, RELEASE_NAME
from database.database import APP_DATA_FOLDER, DatabaseManager
from preferences import PreferencesStore
from services.dashboard_service import DashboardService
from services.plugin_service import PluginService
from services.scan_service import ScanService


LOG_TAIL_LINES = 200


class DiagnosticReportService:
    """Gather version, library, plugin, and log information for support.

    Every real folder path is replaced with a short, stable, generic label
    (for example ``[WATCHED_SOURCE_1]``) before anything is written out,
    so the report stays useful for troubleshooting without exposing the
    user's Windows account name or personal folder names. Book titles,
    authors, and other catalogue contents are deliberately left out
    entirely; only counts and statuses are included.
    """

    def __init__(
        self,
        *,
        database: DatabaseManager,
        plugin_service: PluginService,
        scan_service: ScanService,
        dashboard_service: DashboardService,
        preferences: PreferencesStore,
        log_path: str | Path | None = None,
    ) -> None:
        self.database = database
        self.plugin_service = plugin_service
        self.scan_service = scan_service
        self.dashboard_service = dashboard_service
        self.preferences = preferences
        self.log_path = Path(log_path) if log_path else APP_DATA_FOLDER / "logs" / "twano.log"

    def generate_report(self) -> str:
        """Return the complete report as plain text."""
        redactor = self._build_redactor()
        sections = [
            self._application_section(),
            self._library_section(redactor),
            self._organisation_section(redactor),
            self._plugin_section(redactor),
            self._log_section(redactor),
        ]
        return "\n\n".join(sections) + "\n"

    # -- section builders -------------------------------------------------

    def _application_section(self) -> str:
        lines = [
            "Twano Diagnostic Report",
            "=" * 24,
            f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            "",
            "Application",
            "-----------",
            f"Version: {APP_VERSION} ({RELEASE_NAME})",
            f"Python: {platform.python_version()}",
            f"PySide6 / Qt: {pyside_version} / {qVersion()}",
            f"Platform: {platform.platform()}",
        ]
        return "\n".join(lines)

    def _library_section(self, redactor: "_PathRedactor") -> str:
        data = self.dashboard_service.get_dashboard_data()
        lines = [
            "Library Summary",
            "----------------",
            f"Total books: {data.total_books}",
            f"Missing files: {data.missing_books}",
            f"Needs metadata: {data.needs_metadata}",
            f"Embedded metadata only: {data.embedded_metadata}",
            f"Metadata health: {data.metadata_health}%",
            f"Total size: {_format_bytes(data.total_size)}",
            f"Books added this week: {data.books_this_week}",
            "",
            "Watched Sources",
            "----------------",
        ]
        sources = self.scan_service.get_sources(include_archived=True)
        if not sources:
            lines.append("(none configured)")
        for source in sources:
            label = redactor.label_for(source.folder_path)
            state = "archived" if source.archived_at else "active"
            lines.append(
                f"{label} — {state}, connection={source.connection_status.value}, "
                f"include_subfolders={source.include_subfolders}"
            )
            lines.append(
                "  Last scan: status="
                f"{source.last_scan_status or 'never'}, "
                f"discovered={source.last_scan_discovered_count}, "
                f"new={source.last_scan_new_count}, "
                f"changed={source.last_scan_changed_count}, "
                f"missing={source.last_scan_missing_count}, "
                f"unreadable={source.last_scan_unreadable_count}, "
                f"skipped={source.last_scan_skipped_count}"
            )
            if source.last_scan_error:
                lines.append(
                    "  Last scan error: "
                    + redactor.scrub(source.last_scan_error)
                )
        return "\n".join(lines)

    def _organisation_section(self, redactor: "_PathRedactor") -> str:
        organisation = self.preferences.load_organization_preferences()
        protection = self.preferences.load_protection_preferences()
        home = self.preferences.load_home_preferences()
        lines = [
            "Organisation & Protection Settings",
            "-----------------------------------",
            "Destination folder configured: "
            + (
                redactor.label_for(organisation.destination_folder)
                if organisation.destination_folder
                else "no (each watched library organises itself)"
            ),
            "Backup folder configured: "
            + (
                redactor.label_for(protection.backup_folder)
                if protection.backup_folder
                else "no (using the default location)"
            ),
            f"Backup retention: "
            + (
                "keep all"
                if protection.retention_days == 0
                else f"{protection.retention_days} days"
            ),
            f"Protection mode: {home.protection_mode}",
        ]
        return "\n".join(lines)

    def _plugin_section(self, redactor: "_PathRedactor") -> str:
        lines = ["Plugins", "-------"]
        for plugin in self.plugin_service.list_plugins():
            if not plugin.installed:
                continue
            state = "enabled" if plugin.enabled else "disabled"
            key_state = ""
            if plugin.requires_api_key or plugin.optional_api_key:
                key_state = (
                    ", key configured"
                    if plugin.api_key_configured
                    else ", key not configured"
                )
                if plugin.api_key_unreadable:
                    key_state += " (unreadable by this Windows account)"
            lines.append(
                f"{plugin.name} — {state}{key_state}, "
                f"health={plugin.provider_health}"
            )
            if plugin.provider_health_message:
                lines.append(
                    "  " + redactor.scrub(plugin.provider_health_message)
                )
        if len(lines) == 2:
            lines.append("(none installed)")
        return "\n".join(lines)

    def _log_section(self, redactor: "_PathRedactor") -> str:
        lines = [
            f"Recent Log Entries (last {LOG_TAIL_LINES} lines)",
            "-" * 34,
        ]
        try:
            raw_lines = self.log_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            lines.append("(no log file found)")
            return "\n".join(lines)
        tail = raw_lines[-LOG_TAIL_LINES:]
        if not tail:
            lines.append("(log file is empty)")
        for entry in tail:
            lines.append(redactor.scrub(entry))
        return "\n".join(lines)

    # -- redaction ----------------------------------------------------

    def _build_redactor(self) -> "_PathRedactor":
        redactor = _PathRedactor()
        redactor.register(APP_DATA_FOLDER, "APP_DATA_FOLDER")
        redactor.register(self.database.database_path.parent, "DATABASE_FOLDER")
        for index, source in enumerate(
            self.scan_service.get_sources(include_archived=True),
            start=1,
        ):
            redactor.register(source.folder_path, f"WATCHED_SOURCE_{index}")
        organisation = self.preferences.load_organization_preferences()
        if organisation.destination_folder:
            redactor.register(
                organisation.destination_folder, "DESTINATION_FOLDER"
            )
        protection = self.preferences.load_protection_preferences()
        if protection.backup_folder:
            redactor.register(protection.backup_folder, "BACKUP_FOLDER")
        redactor.register(Path.home(), "USER_HOME")
        return redactor


class _PathRedactor:
    """Replace known real paths (longest first) with recognisable labels."""

    def __init__(self) -> None:
        self._labels: dict[str, str] = {}
        self._username_pattern: re.Pattern[str] | None = None
        try:
            username = Path.home().name
        except OSError:
            username = ""
        if username and len(username) >= 2:
            # Scoped to a "Users\<name>" or "/home/<name>" path segment,
            # not a bare word match: a Windows account name can coincide
            # with an ordinary word (or even this product's own name), and
            # a blanket match would mangle unrelated text that happens to
            # contain it.
            self._username_pattern = re.compile(
                r"((?:Users|home)[\\/])"
                + re.escape(username)
                + r"(?=[\\/]|$)",
                flags=re.IGNORECASE,
            )

    def register(self, path: str | Path, label: str) -> None:
        text = str(path).strip()
        if not text:
            return
        self._labels[text] = f"[{label}]"

    def label_for(self, path: str | Path) -> str:
        text = str(path).strip()
        return self._labels.get(text, self.scrub(text))

    def scrub(self, text: str) -> str:
        if not text:
            return text
        result = text
        for real_path in sorted(self._labels, key=len, reverse=True):
            if real_path in result:
                result = result.replace(real_path, self._labels[real_path])
        if self._username_pattern is not None:
            result = self._username_pattern.sub(r"\1[USER]", result)
        return result


def _format_bytes(total_bytes: int) -> str:
    value = float(total_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"

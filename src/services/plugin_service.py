"""Controlled plugin catalogue, compatibility checks, and quarantine."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import zipfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any

from config import APP_VERSION
from database.database import APP_DATA_FOLDER
from services.plugin_credential_service import PluginCredentialStore


PLUGIN_API_VERSION = 1
MAX_PLUGIN_PACKAGE_BYTES = 25 * 1024 * 1024
REQUIRED_PLUGIN_IDS = frozenset({"local_metadata"})
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PluginRecord:
    plugin_id: str
    name: str
    publisher: str
    version: str
    description: str
    source_name: str
    source_url: str
    capabilities: tuple[str, ...]
    installed: bool
    enabled: bool
    compatible: bool
    built_in: bool
    status: str
    requires_api_key: bool = False
    api_key_configured: bool = False
    api_key_help_url: str = ""
    api_key_note: str = ""
    optional_api_key: bool = False
    api_key_unreadable: bool = False
    provider_health: str = "not_checked"
    provider_health_message: str = ""
    provider_health_checked_at: str = ""


BUILTIN_CATALOG = (
    PluginRecord(
        "local_metadata",
        "Embedded Book Metadata",
        "Twano",
        "1.0",
        "Reads metadata already stored inside supported ebook files.",
        "Included with Twano",
        "",
        ("metadata_provider",),
        True,
        True,
        True,
        True,
        "Active",
    ),
    PluginRecord(
        "open_library_metadata",
        "Open Library Metadata & Covers",
        "Internet Archive / Open Library",
        "1.0",
        "Search Open Library for book details and edition covers.",
        "Open Library",
        "https://openlibrary.org/developers/api",
        ("metadata_provider", "cover_provider"),
        False,
        False,
        True,
        True,
        "Available",
    ),
    PluginRecord(
        "google_books_covers",
        "Google Books Metadata & Covers",
        "Google",
        "1.0",
        "Search Google Books for book details and edition covers without "
        "requiring Calibre.",
        "Google Books API",
        "https://developers.google.com/books/docs/v1/using",
        ("metadata_provider", "cover_provider"),
        False,
        False,
        True,
        True,
        "Available",
        api_key_help_url=(
            "https://console.cloud.google.com/apis/library/books.googleapis.com"
        ),
        api_key_note=(
            "Google Books can sometimes answer without a key. Add a restricted "
            "Google Books API key if requests are unavailable or rate limited."
        ),
        optional_api_key=True,
    ),
    PluginRecord(
        "serpapi_book_resolver",
        "SerpApi Search Book Resolver",
        "SerpApi",
        "1.0",
        "Use real Google search results (via the SerpApi service) to help "
        "identify an exact book title and author before searching other "
        "metadata providers. Does not supply metadata or covers itself.",
        "SerpApi",
        "https://serpapi.com/search-api",
        ("identification_resolver",),
        False,
        False,
        True,
        True,
        "Available",
        True,
        False,
        "https://serpapi.com/manage-api-key",
        "Requires a SerpApi account and API key. Uses your SerpApi search "
        "quota to help identify uncertain titles only.",
    ),
    PluginRecord(
        "hardcover_metadata",
        "Hardcover Metadata & Covers",
        "Hardcover",
        "1.0",
        "Search Hardcover for book metadata and edition covers using your "
        "own API token.",
        "Hardcover API",
        "https://docs.hardcover.app/",
        ("metadata_provider", "cover_provider"),
        False,
        False,
        True,
        True,
        "Available",
        True,
        False,
        "https://hardcover.app/account/api",
        "A free Hardcover account is required. Use a read-only or scoped "
        "token if Hardcover offers that option.",
    ),
    PluginRecord(
        "comic_vine_metadata",
        "Comic Vine Metadata & Covers",
        "Comic Vine",
        "1.0",
        "Search comic and graphic-novel metadata and covers using your own "
        "Comic Vine API key.",
        "Comic Vine API",
        "https://comicvine.gamespot.com/api/",
        ("metadata_provider", "cover_provider"),
        False,
        False,
        True,
        True,
        "Available",
        True,
        False,
        "https://comicvine.gamespot.com/api/",
        "Comic Vine requires an account and limits its API to personal, "
        "non-commercial use. Its rate limits also apply.",
    ),
    PluginRecord(
        "apple_books_metadata",
        "Apple Books Metadata & Covers",
        "Apple",
        "1.0",
        "Search the public Apple Books catalogue for ebook descriptions and "
        "cover artwork. Results can vary by country.",
        "Apple Search API",
        (
            "https://developer.apple.com/library/archive/documentation/"
            "AudioVideo/Conceptual/iTuneSearchAPI/"
        ),
        ("metadata_provider", "cover_provider"),
        False,
        False,
        True,
        True,
        "Available",
    ),
    PluginRecord(
        "amazon_metadata",
        "Amazon Metadata & Covers",
        "Amazon public catalogue",
        "1.1",
        "Search public Amazon Australia, US, UK and Canada book listings for "
        "matching editions and cover art. No Amazon or Calibre installation "
        "is required.",
        "Amazon English Marketplaces",
        "https://www.amazon.com.au/books-used-books-textbooks/b",
        ("metadata_provider", "cover_provider"),
        False,
        False,
        True,
        True,
        "Available",
    ),
    PluginRecord(
        "booktopia_metadata",
        "Booktopia Metadata & Covers",
        "Booktopia",
        "1.0",
        "Search the public Australian Booktopia catalogue for book details and cover artwork.",
        "Booktopia Australia",
        "https://www.booktopia.com.au/",
        ("metadata_provider", "cover_provider"),
        True,
        True,
        True,
        True,
        "Active",
    ),
    PluginRecord(
        "isbndb_metadata",
        "ISBNdb Metadata & Covers",
        "ISBNdb",
        "1.0",
        "Search ISBNdb for edition identifiers, descriptions, publication "
        "details and cover artwork using your own API key.",
        "ISBNdb API",
        "https://isbndb.com/isbn-database",
        ("metadata_provider", "cover_provider"),
        False,
        False,
        True,
        True,
        "Available",
        True,
        False,
        "https://isbndb.com/",
        "ISBNdb requires a personal API subscription or trial. Twano stores "
        "the key only for the current Windows account.",
    ),
    PluginRecord(
        "goodreads_metadata",
        "Goodreads Metadata & Covers",
        "Goodreads public catalogue",
        "1.0",
        "Reads Goodreads' public book pages for series names, ratings and "
        "cover art. Goodreads retired its public API years ago, so this "
        "reads the same pages a browser would -- accurate for series "
        "data, but automated access is against Goodreads' Terms of "
        "Service and Goodreads can block it without notice. Off by "
        "default; only enable this if you accept that risk.",
        "Goodreads",
        "https://www.goodreads.com/",
        ("metadata_provider", "cover_provider"),
        False,
        False,
        True,
        True,
        "Available",
    ),
    PluginRecord(
        "gutenberg_metadata",
        "Project Gutenberg Metadata & Covers",
        "Project Gutenberg data via Gutendex",
        "1.0",
        "Search public-domain ebook metadata, summaries and available cover "
        "images. This catalogue is intended for classic literature.",
        "Gutendex",
        "https://github.com/garethbjohnson/gutendex",
        ("metadata_provider", "cover_provider"),
        False,
        False,
        True,
        True,
        "Available",
    ),
    PluginRecord(
        "harvard_librarycloud_metadata",
        "Harvard LibraryCloud Metadata",
        "Harvard Library",
        "1.0",
        "Search Harvard Library bibliographic records by ISBN, title or "
        "author. Most records do not include downloadable cover artwork.",
        "Harvard LibraryCloud",
        (
            "https://harvardwiki.atlassian.net/wiki/spaces/LibraryStaffDoc/"
            "pages/43287734/LibraryCloud+APIs"
        ),
        ("metadata_provider",),
        False,
        False,
        True,
        True,
        "Available",
    ),
    PluginRecord(
        "crossref_metadata",
        "Crossref Academic Book Metadata",
        "Crossref",
        "1.0",
        "Search DOI-registered books, textbooks and chapters. Crossref "
        "usually provides bibliographic metadata rather than cover artwork.",
        "Crossref REST API",
        "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
        ("metadata_provider",),
        False,
        False,
        True,
        True,
        "Available",
    ),
    PluginRecord(
        "big_book_metadata",
        "Big Book API Metadata & Covers",
        "Big Book API",
        "1.0",
        "Search book metadata, descriptions and covers using a personal Big "
        "Book API key. The free plan has a small daily quota.",
        "Big Book API",
        "https://bigbookapi.com/docs/",
        ("metadata_provider", "cover_provider"),
        False,
        False,
        True,
        True,
        "Available",
        True,
        False,
        "https://bigbookapi.com/pricing",
        "The free non-commercial plan currently allows 50 requests per day "
        "and requires attribution. Paid plans have different terms.",
    ),
    PluginRecord(
        "openweb_ninja_metadata",
        "OpenWeb Ninja Books Metadata & Covers",
        "OpenWeb Ninja",
        "1.0",
        "Search live Google Books results through OpenWeb Ninja using a "
        "personal API key. This is a quota-limited fallback provider.",
        "OpenWeb Ninja Real-Time Books Data API",
        "https://www.openwebninja.com/api/real-time-books-data",
        ("metadata_provider", "cover_provider"),
        False,
        False,
        True,
        True,
        "Available",
        True,
        False,
        "https://app.openwebninja.com/",
        "The free plan currently has a hard monthly request limit. It "
        "duplicates some Google Books data, so use it as a fallback.",
    ),
    PluginRecord(
        "calibre_bridge",
        "Calibre Bridge",
        "Twano",
        "1.0",
        "Detects Calibre and opens libraries through documented commands.",
        "Bundled Twano integration",
        "https://manual.calibre-ebook.com/",
        ("reader_integration", "library_analysis"),
        True,
        True,
        True,
        True,
        "Active",
    ),
    PluginRecord(
        "network_libraries",
        "Windows Network Libraries",
        "Twano",
        "1.0",
        "UNC and mapped-drive diagnostics with offline-source protection.",
        "Bundled Twano integration",
        "",
        ("library_analysis",),
        True,
        True,
        True,
        True,
        "Active",
    ),
)


class PluginService:
    """Manage only allowlisted, versioned extension packages."""

    def __init__(
        self,
        plugin_folder: str | Path | None = None,
        state_path: str | Path | None = None,
        credential_store: PluginCredentialStore | None = None,
    ) -> None:
        self.plugin_folder = Path(
            plugin_folder or APP_DATA_FOLDER / "plugins"
        )
        self.state_path = Path(
            state_path or APP_DATA_FOLDER / "plugin-state.json"
        )
        self.credential_store = credential_store or PluginCredentialStore(
            self.state_path.with_name("plugin-credentials.json")
        )
        self.quarantine_folder = APP_DATA_FOLDER / "plugin-quarantine"
        self.health_path = self.state_path.with_name("provider-health.json")
        self._state = self._load_state()
        self._provider_health = self._load_provider_health()
        self._provider_health_lock = RLock()

    def list_plugins(self) -> tuple[PluginRecord, ...]:
        records = [
            self._with_state(record)
            for record in BUILTIN_CATALOG
        ]
        folders = (
            sorted(self.plugin_folder.iterdir())
            if self.plugin_folder.is_dir()
            else ()
        )
        for folder in folders:
            if not folder.is_dir():
                continue
            manifest_path = folder / "plugin.json"
            try:
                manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
                records.append(self._manifest_record(manifest))
            except Exception:
                records.append(
                    PluginRecord(
                        folder.name,
                        folder.name,
                        "Unknown",
                        "",
                        "This plugin could not be read and is disabled.",
                        "Local package",
                        "",
                        (),
                        True,
                        False,
                        False,
                        False,
                        "Needs attention",
                    )
                )
        return tuple(records)

    def install_builtin(self, plugin_id: str) -> PluginRecord:
        record = self._builtin(plugin_id)
        self._state[record.plugin_id] = {
            "installed": True,
            "enabled": False,
        }
        self._save_state()
        return self._with_state(record)

    def uninstall(self, plugin_id: str) -> PluginRecord:
        """Disable and uninstall an approved built-in without deleting it."""
        record = self._find(plugin_id)
        if record.plugin_id in REQUIRED_PLUGIN_IDS:
            raise ValueError(
                "Embedded Book Metadata is required by Twano and cannot be "
                "uninstalled."
            )
        if not record.built_in:
            raise ValueError(
                "Downloaded plugin packages must be deleted or reinstalled "
                "from their verified package."
            )
        if not record.installed:
            return record
        self._state[record.plugin_id] = {
            "installed": False,
            "enabled": False,
        }
        self._save_state()
        return self._with_state(record)

    def delete_package(self, plugin_id: str) -> str:
        """Permanently remove one installed external plugin package."""
        record = self._find(plugin_id)
        if record.built_in:
            raise ValueError(
                "Approved built-in plugins stay in the catalogue. "
                "Use Uninstall Selected instead."
            )
        destination = (self.plugin_folder / record.plugin_id).resolve()
        plugin_root = self.plugin_folder.resolve()
        if not destination.is_relative_to(plugin_root):
            raise ValueError("The plugin folder is outside Twano's plugin area.")
        if not destination.is_dir():
            raise FileNotFoundError("The installed plugin folder is missing.")
        shutil.rmtree(destination)
        self._state.pop(record.plugin_id, None)
        self.credential_store.delete(record.plugin_id)
        self._save_state()
        return record.name

    def set_enabled(self, plugin_id: str, enabled: bool) -> PluginRecord:
        record = self._find(plugin_id)
        if not record.installed:
            raise ValueError("Install this approved plugin before enabling it.")
        if not record.compatible:
            raise ValueError("This plugin is not compatible with this Twano version.")
        if (
            enabled
            and record.requires_api_key
            and not self.credential_store.has(record.plugin_id)
        ):
            raise ValueError(
                "Configure an API key for this plugin before enabling it."
            )
        self._state[record.plugin_id] = {
            "installed": True,
            "enabled": bool(enabled),
        }
        self._save_state()
        return replace(
            record,
            enabled=bool(enabled),
            status="Active" if enabled else "Disabled",
        )

    def set_api_key(self, plugin_id: str, api_key: str) -> PluginRecord:
        """Store one provider key without exposing it in plugin state."""
        record = self._find(plugin_id)
        if not _uses_api_key(record):
            raise ValueError("This plugin does not use an API key.")
        if not record.installed:
            raise ValueError("Install this approved plugin before adding a key.")
        self.credential_store.save(plugin_id, api_key)
        return self._with_state(record)

    def clear_api_key(self, plugin_id: str) -> PluginRecord:
        """Remove a saved key and disable providers that require one."""
        record = self._find(plugin_id)
        if not _uses_api_key(record):
            raise ValueError("This plugin does not use an API key.")
        self.credential_store.delete(plugin_id)
        if record.installed and record.requires_api_key:
            self._state[plugin_id] = {
                "installed": True,
                "enabled": False,
            }
            self._save_state()
        return self._with_state(record)

    def get_api_key(self, plugin_id: str) -> str:
        """Return a key only to the provider service that needs it."""
        record = self._find(plugin_id)
        if not _uses_api_key(record):
            return ""
        return self.credential_store.load(plugin_id)

    def install_package(
        self,
        package_path: str | Path,
        *,
        approved_hashes: dict[str, str],
    ) -> PluginRecord:
        """Install one catalogue-approved data-only plugin package."""
        package = Path(package_path)
        if not package.is_file() or package.suffix.casefold() != ".twano-plugin":
            raise ValueError("Choose a .twano-plugin package.")
        if package.stat().st_size > MAX_PLUGIN_PACKAGE_BYTES:
            raise ValueError("That plugin package is larger than 25 MB.")
        digest = _sha256(package)
        approved_id = next(
            (
                plugin_id
                for plugin_id, expected in approved_hashes.items()
                if str(expected).casefold() == digest.casefold()
            ),
            "",
        )
        if not approved_id:
            raise ValueError(
                "This package is not in Twano's approved-source catalogue."
            )
        with zipfile.ZipFile(package) as archive:
            self._validate_archive_paths(archive)
            if "plugin.json" not in archive.namelist():
                raise ValueError("The approved package has no plugin.json manifest.")
            manifest = json.loads(archive.read("plugin.json"))
            record = self._manifest_record(manifest)
            if record.plugin_id != approved_id:
                raise ValueError("The package identity does not match the catalogue.")
            if not record.compatible:
                raise ValueError("This package is not compatible with this Twano build.")
            self.plugin_folder.mkdir(parents=True, exist_ok=True)
            destination = self.plugin_folder / record.plugin_id
            if destination.exists():
                raise FileExistsError("That plugin is already installed.")
            temporary = self.plugin_folder / f".{record.plugin_id}.installing"
            if temporary.exists():
                shutil.rmtree(temporary)
            temporary.mkdir()
            try:
                archive.extractall(temporary)
                temporary.replace(destination)
            except Exception:
                if temporary.exists():
                    shutil.rmtree(temporary)
                raise
        self._state[record.plugin_id] = {
            "installed": True,
            "enabled": False,
        }
        self._save_state()
        return replace(record, installed=True, enabled=False, status="Disabled")

    def quarantine(self, plugin_id: str) -> Path:
        record = self._find(plugin_id)
        if record.built_in:
            raise ValueError("Built-in integrations can be disabled, not quarantined.")
        source = self.plugin_folder / record.plugin_id
        if not source.is_dir():
            raise FileNotFoundError("The installed plugin folder is missing.")
        self.quarantine_folder.mkdir(parents=True, exist_ok=True)
        target = self.quarantine_folder / (
            record.plugin_id + "-" + hashlib.sha256(
                str(source).encode("utf-8")
            ).hexdigest()[:8]
        )
        if target.exists():
            raise FileExistsError("This plugin is already quarantined.")
        shutil.move(str(source), str(target))
        self._state[record.plugin_id] = {
            "installed": False,
            "enabled": False,
        }
        self._save_state()
        return target

    def is_enabled(self, plugin_id: str) -> bool:
        try:
            return self._find(plugin_id).enabled
        except KeyError:
            return False

    def report_provider_health(
        self,
        plugin_id: str,
        status: str,
        message: str = "",
    ) -> None:
        """Persist a provider check without storing searches or credentials."""
        if status not in {
            "healthy",
            "blocked",
            "layout_changed",
            "unavailable",
            "not_checked",
        }:
            raise ValueError(f"Unknown provider health status: {status}")
        checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        safe_message = " ".join(str(message).split())[:600]
        with self._provider_health_lock:
            self._provider_health[plugin_id] = {
                "status": status,
                "message": safe_message,
                "checked_at": checked_at,
                "provider_version": self._find(plugin_id).version,
            }
            self._save_provider_health()
        log_method = (
            logger.warning
            if status in {"blocked", "layout_changed"}
            else logger.info
        )
        log_method(
            "Provider health: plugin=%s status=%s checked_at=%s detail=%s",
            plugin_id,
            status,
            checked_at,
            safe_message or "none",
        )

    def clear_provider_health(self, plugin_id: str) -> None:
        """Clear a stale diagnostic after an approved endpoint update."""
        with self._provider_health_lock:
            if self._provider_health.pop(plugin_id, None) is not None:
                self._save_provider_health()

    def _with_state(self, record: PluginRecord) -> PluginRecord:
        state = self._state.get(record.plugin_id)
        if not isinstance(state, dict):
            state = {}
        installed = bool(state.get("installed", record.installed))
        api_key_configured = (
            self.credential_store.has(record.plugin_id)
            if _uses_api_key(record)
            else False
        )
        entry_exists = getattr(
            self.credential_store,
            "entry_exists",
            lambda _plugin_id: api_key_configured,
        )
        api_key_unreadable = bool(
            _uses_api_key(record)
            and not api_key_configured
            and entry_exists(record.plugin_id)
        )
        enabled = (
            bool(state.get("enabled", record.enabled))
            and installed
            and (not record.requires_api_key or api_key_configured)
        )
        health = self._provider_health.get(record.plugin_id, {})
        checked_version = str(health.get("provider_version", ""))
        if checked_version and checked_version != record.version:
            health = {}
        health_status = str(health.get("status", "not_checked"))
        health_message = str(health.get("message", ""))
        health_checked_at = str(health.get("checked_at", ""))
        active_status = "Active"
        if health_status == "blocked":
            active_status = "Active — access blocked"
        elif health_status == "layout_changed":
            active_status = "Active — provider update needed"
        elif health_status == "unavailable":
            active_status = "Active — temporarily unavailable"
        return replace(
            record,
            installed=installed,
            enabled=enabled,
            api_key_configured=api_key_configured,
            api_key_unreadable=api_key_unreadable,
            provider_health=health_status,
            provider_health_message=health_message,
            provider_health_checked_at=health_checked_at,
            status=(
                "Active — key needs re-entry"
                if enabled and api_key_unreadable
                else active_status if enabled
                else "Key needs re-entry"
                if installed and api_key_unreadable
                else "Setup required"
                if installed
                and record.requires_api_key
                and not api_key_configured
                else "Disabled" if installed
                else "Available"
            ),
        )

    def _builtin(self, plugin_id: str) -> PluginRecord:
        for record in BUILTIN_CATALOG:
            if record.plugin_id == plugin_id:
                return record
        raise KeyError(f"Unknown approved plugin: {plugin_id}")

    def _find(self, plugin_id: str) -> PluginRecord:
        for record in self.list_plugins():
            if record.plugin_id == plugin_id:
                return record
        raise KeyError(f"Unknown plugin: {plugin_id}")

    def _manifest_record(self, manifest: Any) -> PluginRecord:
        if not isinstance(manifest, dict):
            raise ValueError("Plugin manifest must be an object.")
        required = {
            "id",
            "name",
            "publisher",
            "version",
            "api_version",
            "description",
            "source_url",
            "capabilities",
        }
        if not required.issubset(manifest):
            raise ValueError("Plugin manifest is incomplete.")
        plugin_id = str(manifest["id"]).strip()
        if not plugin_id or not all(
            character.isalnum() or character in "._-"
            for character in plugin_id
        ):
            raise ValueError("Plugin ID is invalid.")
        api_version = int(manifest["api_version"])
        capabilities = tuple(
            str(value)
            for value in manifest["capabilities"]
            if str(value) in {
                "metadata_provider",
                "cover_provider",
                "export_provider",
                "library_analysis",
            }
        )
        compatible = api_version == PLUGIN_API_VERSION
        state = self._state.get(plugin_id, {})
        installed = bool(state.get("installed", True))
        enabled = bool(state.get("enabled", False)) and compatible
        return PluginRecord(
            plugin_id=plugin_id,
            name=str(manifest["name"]),
            publisher=str(manifest["publisher"]),
            version=str(manifest["version"]),
            description=str(manifest["description"]),
            source_name=str(manifest["publisher"]),
            source_url=str(manifest["source_url"]),
            capabilities=capabilities,
            installed=installed,
            enabled=enabled,
            compatible=compatible,
            built_in=False,
            status=(
                "Active" if enabled
                else "Disabled" if compatible
                else f"Needs plugin API {api_version}"
            ),
        )

    def _load_state(self) -> dict[str, dict[str, bool]]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".json.partial")
        temporary.write_text(
            json.dumps(self._state, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    def _load_provider_health(self) -> dict[str, dict[str, str]]:
        try:
            data = json.loads(self.health_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_provider_health(self) -> None:
        self.health_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.health_path.with_suffix(".json.partial")
        temporary.write_text(
            json.dumps(self._provider_health, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.health_path)

    @staticmethod
    def _validate_archive_paths(archive: zipfile.ZipFile) -> None:
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Plugin package contains an unsafe path.")
            if member.file_size > MAX_PLUGIN_PACKAGE_BYTES:
                raise ValueError("Plugin package contains an oversized file.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _uses_api_key(record: PluginRecord) -> bool:
    return record.requires_api_key or record.optional_api_key

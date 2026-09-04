"""Safe, data-only provider endpoint updates for startup maintenance."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from database.database import APP_DATA_FOLDER
import services.cover_search_service as cover_module
import services.metadata_studio_service as metadata_module
import services.remote_metadata_provider_service as remote_module


logger = logging.getLogger(__name__)

DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/Boostwano/twano-updates/"
    "main/provider-search-locations.json"
)
MAX_MANIFEST_BYTES = 128 * 1024
MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EndpointTarget:
    """One runtime URL constant and the hosts it may safely use."""

    module: Any
    attribute: str
    allowed_hosts: tuple[str, ...]


ENDPOINT_TARGETS: dict[tuple[str, str], EndpointTarget] = {
    ("open_library_metadata", "search_url"): EndpointTarget(
        metadata_module, "OPEN_LIBRARY_SEARCH_URL", ("openlibrary.org",)
    ),
    ("open_library_metadata", "cover_url"): EndpointTarget(
        metadata_module, "OPEN_LIBRARY_COVER_URL", ("openlibrary.org",)
    ),
    ("wikipedia_work_resolver", "api_url"): EndpointTarget(
        metadata_module, "WIKIPEDIA_API_URL", ("wikipedia.org",)
    ),
    ("google_books_covers", "search_url"): EndpointTarget(
        cover_module, "GOOGLE_BOOKS_SEARCH_URL", ("googleapis.com",)
    ),
    ("apple_books_metadata", "search_url"): EndpointTarget(
        cover_module, "APPLE_BOOKS_SEARCH_URL", ("apple.com",)
    ),
    ("isbndb_metadata", "api_url"): EndpointTarget(
        cover_module, "ISBNDB_API_URL", ("isbndb.com",)
    ),
    ("hardcover_metadata", "api_url"): EndpointTarget(
        remote_module, "HARDCOVER_API_URL", ("hardcover.app",)
    ),
    ("comic_vine_metadata", "search_url"): EndpointTarget(
        remote_module, "COMIC_VINE_SEARCH_URL", ("gamespot.com",)
    ),
    ("comic_vine_metadata", "issues_url"): EndpointTarget(
        remote_module, "COMIC_VINE_ISSUES_URL", ("gamespot.com",)
    ),
    ("gutenberg_metadata", "search_url"): EndpointTarget(
        remote_module, "GUTENDEX_SEARCH_URL", ("gutendex.com",)
    ),
    ("harvard_librarycloud_metadata", "search_url"): EndpointTarget(
        remote_module, "HARVARD_LIBRARYCLOUD_URL", ("harvard.edu",)
    ),
    ("crossref_metadata", "search_url"): EndpointTarget(
        remote_module, "CROSSREF_WORKS_URL", ("crossref.org",)
    ),
    ("big_book_metadata", "api_url"): EndpointTarget(
        remote_module, "BIG_BOOK_API_URL", ("bigbookapi.com",)
    ),
    ("openweb_ninja_metadata", "search_url"): EndpointTarget(
        remote_module, "OPENWEB_NINJA_BOOKS_URL", ("openwebninja.com",)
    ),
    ("amazon_metadata", "search_url"): EndpointTarget(
        remote_module,
        "AMAZON_BOOK_SEARCH_URL",
        ("amazon.com", "amazon.com.au", "amazon.co.uk", "amazon.ca"),
    ),
    ("goodreads_metadata", "search_url"): EndpointTarget(
        remote_module, "GOODREADS_SEARCH_URL", ("goodreads.com",)
    ),
}


class ProviderUpdateError(ValueError):
    """A downloaded provider manifest failed conservative validation."""


class ProviderUpdateService:
    """Load cached endpoints immediately and refresh them off the GUI thread."""

    def __init__(
        self,
        *,
        manifest_url: str = DEFAULT_MANIFEST_URL,
        cache_path: str | Path | None = None,
        timeout: float = 6.0,
    ) -> None:
        self.manifest_url = manifest_url
        self.cache_path = Path(
            cache_path
            or APP_DATA_FOLDER / "provider-search-locations.json"
        )
        self.timeout = timeout

    def apply_cached(self, *, plugin_service: Any | None = None) -> int:
        """Apply a previously validated manifest without using the network."""
        if not self.cache_path.is_file():
            return 0
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            endpoints = _validated_endpoints(payload)
        except (OSError, json.JSONDecodeError, ProviderUpdateError) as error:
            logger.warning("Ignoring invalid provider update cache: %s", error)
            return 0
        return _apply_endpoints(endpoints, plugin_service=plugin_service)

    def refresh_and_apply(self, *, plugin_service: Any | None = None) -> int:
        """Download, validate, cache, and apply the latest endpoint manifest."""
        request = Request(
            self.manifest_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Twanos-eBook-Manager/4 provider updater",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    raise ProviderUpdateError(
                        f"Manifest server returned HTTP {response.status}."
                    )
                raw = response.read(MAX_MANIFEST_BYTES + 1)
            if len(raw) > MAX_MANIFEST_BYTES:
                raise ProviderUpdateError("Provider manifest is too large.")
            payload = json.loads(raw.decode("utf-8"))
            endpoints = _validated_endpoints(payload)
            self._save(payload)
            count = _apply_endpoints(
                endpoints,
                plugin_service=plugin_service,
            )
            logger.info("Applied %s provider endpoint update(s).", count)
            return count
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ProviderUpdateError,
        ) as error:
            logger.info("Provider endpoint update check skipped: %s", error)
            return 0

    def _save(self, payload: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.cache_path)


def _validated_endpoints(payload: Any) -> dict[tuple[str, str], str]:
    if not isinstance(payload, dict):
        raise ProviderUpdateError("Manifest root must be an object.")
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ProviderUpdateError("Unsupported provider manifest schema.")
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        raise ProviderUpdateError("Manifest providers must be an object.")

    validated: dict[tuple[str, str], str] = {}
    for plugin_id, definition in providers.items():
        if not isinstance(definition, dict):
            raise ProviderUpdateError("Provider definition must be an object.")
        endpoints = definition.get("endpoints")
        if not isinstance(endpoints, dict):
            raise ProviderUpdateError("Provider endpoints must be an object.")
        for endpoint_name, value in endpoints.items():
            key = (str(plugin_id), str(endpoint_name))
            target = ENDPOINT_TARGETS.get(key)
            if target is None:
                raise ProviderUpdateError(
                    f"Unapproved provider endpoint: {key[0]}.{key[1]}"
                )
            if not isinstance(value, str) or not _allowed_url(
                value,
                target.allowed_hosts,
            ):
                raise ProviderUpdateError(
                    f"Unsafe provider URL: {key[0]}.{key[1]}"
                )
            validated[key] = value
    return validated


def _allowed_url(value: str, allowed_hosts: tuple[str, ...]) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").casefold()
    return bool(
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and host
        and any(host == suffix or host.endswith("." + suffix) for suffix in allowed_hosts)
    )


def _apply_endpoints(
    endpoints: dict[tuple[str, str], str],
    *,
    plugin_service: Any | None,
) -> int:
    changed_plugins: set[str] = set()
    changed = 0
    for key, value in endpoints.items():
        target = ENDPOINT_TARGETS[key]
        if getattr(target.module, target.attribute) == value:
            continue
        setattr(target.module, target.attribute, value)
        changed += 1
        changed_plugins.add(key[0])
    if plugin_service is not None:
        clear_health = getattr(plugin_service, "clear_provider_health", None)
        if callable(clear_health):
            for plugin_id in changed_plugins:
                clear_health(plugin_id)
    return changed

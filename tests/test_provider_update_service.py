"""Provider endpoint updates remain data-only, bounded, and optional."""

from __future__ import annotations

import json

import services.remote_metadata_provider_service as remote_module
from services.provider_update_service import ProviderUpdateService


class _Response:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit: int = -1) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _PluginService:
    def __init__(self) -> None:
        self.cleared: list[str] = []

    def clear_provider_health(self, plugin_id: str) -> None:
        self.cleared.append(plugin_id)


def test_refresh_applies_and_caches_approved_endpoint(
    monkeypatch,
    tmp_path,
) -> None:
    original = remote_module.AMAZON_BOOK_SEARCH_URL
    payload = {
        "schema_version": 1,
        "providers": {
            "amazon_metadata": {
                "endpoints": {
                    "search_url": "https://www.amazon.com/search",
                }
            }
        },
    }
    monkeypatch.setattr(
        "services.provider_update_service.urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )
    plugins = _PluginService()
    service = ProviderUpdateService(cache_path=tmp_path / "providers.json")
    try:
        assert service.refresh_and_apply(plugin_service=plugins) == 1
        assert remote_module.AMAZON_BOOK_SEARCH_URL == (
            "https://www.amazon.com/search"
        )
        assert plugins.cleared == ["amazon_metadata"]
        assert json.loads(service.cache_path.read_text(encoding="utf-8")) == payload
    finally:
        remote_module.AMAZON_BOOK_SEARCH_URL = original


def test_refresh_rejects_unapproved_host_without_changing_runtime(
    monkeypatch,
    tmp_path,
) -> None:
    original = remote_module.AMAZON_BOOK_SEARCH_URL
    payload = {
        "schema_version": 1,
        "providers": {
            "amazon_metadata": {
                "endpoints": {"search_url": "https://example.net/search"}
            }
        },
    }
    monkeypatch.setattr(
        "services.provider_update_service.urlopen",
        lambda *_args, **_kwargs: _Response(payload),
    )
    service = ProviderUpdateService(cache_path=tmp_path / "providers.json")
    assert service.refresh_and_apply() == 0
    assert remote_module.AMAZON_BOOK_SEARCH_URL == original
    assert not service.cache_path.exists()


def test_cached_manifest_is_applied_without_network(tmp_path) -> None:
    original = remote_module.AMAZON_BOOK_SEARCH_URL
    cache_path = tmp_path / "providers.json"
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "providers": {
                    "amazon_metadata": {
                        "endpoints": {
                            "search_url": "https://www.amazon.com.au/s"
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    try:
        assert ProviderUpdateService(cache_path=cache_path).apply_cached() == 1
        assert remote_module.AMAZON_BOOK_SEARCH_URL == (
            "https://www.amazon.com.au/s"
        )
    finally:
        remote_module.AMAZON_BOOK_SEARCH_URL = original

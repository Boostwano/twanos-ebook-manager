"""Tests for Open Library enrichment without live network access."""

import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from metadata.models import MetadataResult
from metadata.provider_manager import (
    ProviderManager,
    create_default_provider_manager,
    merge_metadata,
)
from metadata.providers.open_library_provider import OpenLibraryProvider


def response(documents):
    return json.dumps({"docs": documents}).encode()


def document(**overrides):
    values = {
        "title": "The Example Book",
        "author_name": ["Ada Author"],
        "isbn": ["9781234567897"],
        "publisher": ["Example Press"],
        "language": ["eng"],
        "first_publish_date": "2020",
    }
    values.update(overrides)
    return values


def local(**overrides):
    values = {
        "title": "The Example Book",
        "author": "Ada Author",
        "isbn": None,
        "extraction_status": "embedded",
        "confidence": 0.6,
        "provider_name": "local",
    }
    values.update(overrides)
    return MetadataResult(**values)


def test_exact_isbn_lookup_maps_result_and_has_full_confidence() -> None:
    calls = []

    def get(url, headers, timeout):
        calls.append((url, headers, timeout))
        return response([document()])

    result = OpenLibraryProvider(http_get=get).enrich(
        "book.epub",
        local(isbn="978-1-23456-789-7"),
    )

    assert result is not None
    assert "isbn=9781234567897" in calls[0][0]
    assert "title=" not in calls[0][0]
    assert calls[0][1]["User-Agent"].startswith("Twanos-eBook-Manager/")
    assert result.title == "The Example Book"
    assert result.author == "Ada Author"
    assert result.publisher == "Example Press"
    assert result.language == "eng"
    assert result.published_date == "2020"
    assert result.confidence == 1.0
    assert result.provider_name == "open_library"


def test_isbn_no_result_falls_back_to_title_and_author() -> None:
    urls = []

    def get(url, _headers, _timeout):
        urls.append(url)
        return response([] if "isbn=" in url else [document()])

    result = OpenLibraryProvider(http_get=get).enrich(
        "book.epub",
        local(isbn="9781234567897"),
    )

    assert result is not None
    assert len(urls) == 2
    assert "title=The+Example+Book" in urls[1]
    assert "author=Ada+Author" in urls[1]
    assert result.confidence == 0.85


def test_unrelated_search_result_is_rejected() -> None:
    provider = OpenLibraryProvider(
        http_get=lambda *_: response(
            [document(title="Different Book")]
        )
    )
    assert provider.enrich("book.epub", local()) is None


@pytest.mark.parametrize(
    "failure",
    [
        b"{not json",
        HTTPError("url", 500, "error", {}, None),
        TimeoutError("slow"),
        URLError("offline"),
    ],
)
def test_malformed_and_network_failures_are_clean_no_result(failure) -> None:
    def get(*_args):
        if isinstance(failure, bytes):
            return failure
        raise failure

    assert OpenLibraryProvider(http_get=get).enrich(
        "book.epub",
        local(),
    ) is None


def test_title_only_requires_exact_distinctive_title() -> None:
    provider = OpenLibraryProvider(
        http_get=lambda *_: response([document()])
    )
    result = provider.enrich(
        "The Example Book.epub",
        local(author=None),
    )
    assert result is not None
    assert result.confidence == 0.70

    short = OpenLibraryProvider(
        http_get=lambda *_: response([document(title="Dune")])
    )
    assert short.enrich(
        "Dune.epub",
        local(title="Dune", author=None),
    ) is None


def test_duplicate_query_uses_per_provider_cache() -> None:
    calls = []

    def get(*args):
        calls.append(args)
        return response([document()])

    provider = OpenLibraryProvider(http_get=get)
    first = provider.enrich("one.epub", local())
    second = provider.enrich("two.epub", local())

    assert first == second
    assert len(calls) == 1


def test_merge_enriches_blanks_without_erasing_stronger_local_values() -> None:
    current = local(
        title="Trusted Local Title",
        publisher=None,
        confidence=0.9,
    )
    incoming = MetadataResult(
        title="External Title",
        publisher="External Press",
        extraction_status="external",
        confidence=0.85,
        provider_name="open_library",
    )
    merged = merge_metadata(current, incoming)

    assert merged.title == "Trusted Local Title"
    assert merged.publisher == "External Press"
    assert merged.provider_name == "open_library"
    assert merged.confidence == 0.9

    empty = merge_metadata(
        current,
        MetadataResult(
            confidence=1.0,
            provider_name="open_library",
        ),
    )
    assert empty.title == "Trusted Local Title"


def test_reliable_isbn_result_replaces_weaker_local_values() -> None:
    merged = merge_metadata(
        local(title="Weak Title", isbn="9781234567897"),
        MetadataResult(
            title="Verified Title",
            isbn="9781234567897",
            extraction_status="external",
            confidence=1.0,
            provider_name="open_library",
        ),
    )
    assert merged.title == "Verified Title"
    assert merged.confidence == 1.0


def test_provider_can_be_disabled_and_default_is_local_only() -> None:
    calls = []
    disabled = OpenLibraryProvider(
        enabled=False,
        http_get=lambda *args: calls.append(args),
    )
    assert not disabled.supports(Path("book.epub"))
    assert disabled.enrich("book.epub", local()) is None
    assert calls == []
    assert [
        provider.name
        for provider in create_default_provider_manager(
            open_library_enabled=False
        ).providers
    ] == ["local"]


def test_manager_preserves_local_result_when_external_has_no_match() -> None:
    class Local:
        name = "local"

        def supports(self, _path):
            return True

        def enrich(self, _path, _current):
            return local()

    manager = ProviderManager(
        [
            Local(),
            OpenLibraryProvider(http_get=lambda *_: response([])),
        ]
    )
    assert manager.extract("book.epub") == local()

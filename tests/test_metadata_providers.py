"""Tests for the metadata provider framework."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from core.metadata import BookMetadata
from metadata.models import MetadataResult
from metadata.provider import MetadataProvider
from metadata.provider_manager import (
    ProviderManager,
    create_default_provider_manager,
)
from metadata.providers.local_provider import LocalMetadataProvider


class StubProvider(MetadataProvider):
    """Deterministic provider used to test manager behavior."""

    def __init__(
        self,
        name: str,
        result: MetadataResult | None,
        *,
        supported: bool = True,
    ) -> None:
        self._name = name
        self._result = result
        self._supported = supported
        self.support_calls: list[Path] = []
        self.calls: list[Path] = []

    @property
    def name(self) -> str:
        return self._name

    def supports(
        self,
        file_path: str | Path,
    ) -> bool:
        self.support_calls.append(Path(file_path))
        return self._supported

    def extract(
        self,
        file_path: str | Path,
    ) -> MetadataResult:
        self.calls.append(Path(file_path))

        if self._result is None:
            raise AssertionError("Supported stub must provide a result")

        return self._result


def test_metadata_result_is_immutable_and_validates_confidence() -> None:
    result = MetadataResult(
        title="Example",
        confidence=0.75,
        provider_name="test",
    )

    assert result.title == "Example"
    assert result.confidence == 0.75

    with pytest.raises(FrozenInstanceError):
        result.title = "Changed"

    with pytest.raises(ValueError):
        MetadataResult(confidence=1.1)


def test_provider_manager_executes_all_and_returns_highest_confidence(
    tmp_path: Path,
) -> None:
    book_path = tmp_path / "Example.epub"
    low = StubProvider(
        "low",
        MetadataResult(confidence=0.2, provider_name="low"),
    )
    unsupported = StubProvider("unsupported", None, supported=False)
    high = StubProvider(
        "high",
        MetadataResult(confidence=0.9, provider_name="high"),
    )
    manager = ProviderManager([low, unsupported])
    manager.register(high)

    result = manager.extract(book_path)

    assert result is not None
    assert result.provider_name == "high"
    assert low.calls == [book_path]
    assert unsupported.support_calls == [book_path]
    assert unsupported.calls == []
    assert high.calls == [book_path]


def test_provider_manager_rejects_duplicate_provider_names() -> None:
    manager = ProviderManager([StubProvider("same", None)])

    with pytest.raises(ValueError):
        manager.register(StubProvider("same", None))


def test_local_provider_preserves_local_extraction_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    book_path = tmp_path / "Example.epub"
    extracted = BookMetadata(
        title="Example",
        author="Author",
        isbn="9780000000000",
        publisher="Publisher",
        language="en",
        published_date="2026",
        extraction_status="embedded",
    )
    calls = []

    def fake_extract(path):
        calls.append(path)
        return extracted

    monkeypatch.setattr(
        "metadata.providers.local_provider.extract_metadata",
        fake_extract,
    )

    provider = LocalMetadataProvider()
    result = provider.extract(book_path)

    assert calls == [book_path]
    assert provider.supports(book_path)
    assert result.title == extracted.title
    assert result.author == extracted.author
    assert result.isbn == extracted.isbn
    assert result.publisher == extracted.publisher
    assert result.language == extracted.language
    assert result.published_date == extracted.published_date
    assert result.extraction_status == extracted.extraction_status
    assert result.confidence == 1.0
    assert result.provider_name == "local"


def test_default_manager_registers_only_local_provider() -> None:
    manager = create_default_provider_manager()

    assert [provider.name for provider in manager.providers] == ["local"]


def test_local_provider_preserves_missing_file_status(
    tmp_path: Path,
) -> None:
    result = LocalMetadataProvider().extract(
        tmp_path / "missing.epub"
    )

    assert result.extraction_status == "missing"
    assert result.confidence == 0.0
    assert result.provider_name == "local"

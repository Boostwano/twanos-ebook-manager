"""Registration and execution of metadata providers."""

from collections.abc import Iterable
from pathlib import Path

from metadata.models import MetadataResult
from metadata.provider import MetadataProvider


class ProviderManager:
    """Execute providers in order and merge useful metadata fields."""

    def __init__(
        self,
        providers: Iterable[MetadataProvider] = (),
    ) -> None:
        self._providers: list[MetadataProvider] = []

        for provider in providers:
            self.register(provider)

    @property
    def providers(self) -> tuple[MetadataProvider, ...]:
        """Return registered providers in execution order."""
        return tuple(self._providers)

    def register(self, provider: MetadataProvider) -> None:
        """Register a provider once by its stable name."""
        if any(
            existing.name == provider.name
            for existing in self._providers
        ):
            raise ValueError(
                f"Metadata provider already registered: {provider.name}"
            )

        self._providers.append(provider)

    def extract(
        self,
        file_path: str | Path,
    ) -> MetadataResult | None:
        """Run supporting providers and enrich the accumulated result."""
        result: MetadataResult | None = None

        for provider in self._providers:
            if not provider.supports(file_path):
                continue

            enrich = getattr(provider, "enrich", None)
            provider_result = (
                enrich(file_path, result)
                if enrich is not None
                else provider.extract(file_path)
            )
            if provider_result is not None:
                result = merge_metadata(result, provider_result)

        return result


def merge_metadata(
    current: MetadataResult | None,
    incoming: MetadataResult,
) -> MetadataResult:
    """Merge non-empty fields, allowing only stronger results to replace."""
    if current is None:
        return incoming

    incoming_is_stronger = incoming.confidence > current.confidence

    def choose(old: str | None, new: str | None) -> str | None:
        if not new:
            return old
        if not old or incoming_is_stronger:
            return new
        return old

    changed = any(
        choose(getattr(current, field), getattr(incoming, field))
        != getattr(current, field)
        for field in (
            "title",
            "author",
            "isbn",
            "publisher",
            "language",
            "published_date",
        )
    )
    adopted_incoming = changed or incoming_is_stronger
    return MetadataResult(
        title=choose(current.title, incoming.title),
        author=choose(current.author, incoming.author),
        isbn=choose(current.isbn, incoming.isbn),
        publisher=choose(current.publisher, incoming.publisher),
        language=choose(current.language, incoming.language),
        published_date=choose(
            current.published_date,
            incoming.published_date,
        ),
        extraction_status=(
            incoming.extraction_status
            if adopted_incoming
            else current.extraction_status
        ),
        confidence=max(current.confidence, incoming.confidence),
        provider_name=(
            incoming.provider_name
            if adopted_incoming
            else current.provider_name
        ),
    )


def create_default_provider_manager(
    *,
    open_library_enabled: bool | None = None,
) -> ProviderManager:
    """Create built-in providers in local-first execution order."""
    from config import OPEN_LIBRARY_ENABLED
    from metadata.providers.local_provider import LocalMetadataProvider
    from metadata.providers.open_library_provider import OpenLibraryProvider

    enabled = (
        OPEN_LIBRARY_ENABLED
        if open_library_enabled is None
        else open_library_enabled
    )
    providers: list[MetadataProvider] = [LocalMetadataProvider()]
    if enabled:
        providers.append(OpenLibraryProvider())
    return ProviderManager(providers)

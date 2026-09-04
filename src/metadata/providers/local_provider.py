"""Local embedded-metadata provider."""

from pathlib import Path

from core.metadata import extract_metadata
from metadata.models import MetadataResult
from metadata.provider import MetadataProvider


class LocalMetadataProvider(MetadataProvider):
    """Adapt the existing local EPUB extractor to the provider API."""

    @property
    def name(self) -> str:
        return "local"

    def supports(self, file_path: str | Path) -> bool:
        """Return true because the local extractor owns all local statuses."""
        return True

    def extract(
        self,
        file_path: str | Path,
    ) -> MetadataResult:
        """Return the existing local extraction result unchanged."""
        metadata = extract_metadata(file_path)

        return MetadataResult(
            title=metadata.title,
            author=metadata.author,
            isbn=metadata.isbn,
            publisher=metadata.publisher,
            language=metadata.language,
            published_date=metadata.published_date,
            extraction_status=metadata.extraction_status,
            confidence=(
                1.0
                if metadata.extraction_status == "embedded"
                else 0.0
            ),
            provider_name=self.name,
        )

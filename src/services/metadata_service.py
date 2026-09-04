"""Stable service interface for local metadata extraction."""

from pathlib import Path

from metadata.models import MetadataResult
from metadata.provider_manager import (
    ProviderManager,
    create_default_provider_manager,
)


class MetadataService:
    """Resolve metadata through an explicitly configured provider manager."""

    def __init__(
        self,
        provider_manager: ProviderManager | None = None,
    ) -> None:
        self._provider_manager = (
            provider_manager
            or create_default_provider_manager()
        )

    def extract(self, file_path: str | Path) -> MetadataResult:
        """Return the best available provider result."""
        result = self._provider_manager.extract(file_path)

        if result is None:
            return MetadataResult(extraction_status="unavailable")

        return result

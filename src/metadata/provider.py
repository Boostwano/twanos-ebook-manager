"""Metadata provider interface."""

from abc import ABC, abstractmethod
from pathlib import Path

from metadata.models import MetadataResult


class MetadataProvider(ABC):
    """Interface implemented by independent metadata sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable provider name."""

    @abstractmethod
    def supports(
        self,
        file_path: str | Path,
    ) -> bool:
        """Return whether this provider can inspect the supplied path."""

    @abstractmethod
    def extract(
        self,
        file_path: str | Path,
    ) -> MetadataResult:
        """Extract provider-neutral metadata from the supplied path."""

    def enrich(
        self,
        file_path: str | Path,
        current: MetadataResult | None,
    ) -> MetadataResult | None:
        """Return metadata using an earlier provider result as context."""
        return self.extract(file_path)

"""Models shared by metadata providers and their clients."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MetadataResult:
    """Provider-neutral metadata for one local eBook."""

    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    language: str | None = None
    published_date: str | None = None
    extraction_status: str = "unavailable"
    confidence: float = 0.0
    provider_name: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")

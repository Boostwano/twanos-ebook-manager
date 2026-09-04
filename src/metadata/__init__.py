"""Metadata provider framework."""

from metadata.models import MetadataResult
from metadata.provider import MetadataProvider
from metadata.provider_manager import (
    ProviderManager,
    create_default_provider_manager,
)
from metadata.providers.local_provider import LocalMetadataProvider
from metadata.providers.open_library_provider import OpenLibraryProvider

__all__ = [
    "LocalMetadataProvider",
    "OpenLibraryProvider",
    "MetadataProvider",
    "MetadataResult",
    "ProviderManager",
    "create_default_provider_manager",
]

"""Built-in metadata providers."""

from metadata.providers.local_provider import LocalMetadataProvider
from metadata.providers.open_library_provider import OpenLibraryProvider

__all__ = ["LocalMetadataProvider", "OpenLibraryProvider"]

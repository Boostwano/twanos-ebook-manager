"""Application configuration defaults."""

import os


APP_VERSION = "R4 RC1"
RELEASE_NAME = "Production Release Candidate"


def _environment_flag(name: str, *, default: bool) -> bool:
    """Read a conservative boolean environment setting."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# External metadata lookup is opt-in because scans otherwise disclose book
# identifiers and titles to a third-party service.
OPEN_LIBRARY_ENABLED = _environment_flag(
    "TWANOS_OPEN_LIBRARY_ENABLED",
    default=False,
)

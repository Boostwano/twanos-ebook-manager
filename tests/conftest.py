"""Shared pytest configuration."""

import os
import sys
import tempfile
import time
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_ROOT))


def pytest_configure(config) -> None:
    """Use a repeatable Windows-safe temp root without pytest symlinks."""
    if config.option.basetemp is None:
        config.option.basetemp = (
            Path(tempfile.gettempdir())
            / f"TwanoPytest-{os.getpid()}-{time.time_ns()}"
        )

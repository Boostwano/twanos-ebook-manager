"""Shared Twano branding assets and wording."""

from __future__ import annotations

from pathlib import Path
import sys


BRAND_TAGLINE = "Your Library, Beautifully Organised"
BRAND_TAGLINE_UPPER = BRAND_TAGLINE.upper()


def branding_asset_path(filename: str) -> Path:
    """Return a source-tree or bundled path for an approved brand asset."""
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root) / "design" / "branding" / filename
    return Path(__file__).resolve().parents[2] / "design" / "branding" / filename

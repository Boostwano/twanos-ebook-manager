"""Validated Home banner selection independent of Qt widgets."""

from __future__ import annotations

import random
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from preferences import (
    BANNER_NAMES,
    DEFAULT_BANNER_NAME,
    BannerRotation,
    HomePreferences,
    normalise_banner_name,
    normalise_banner_rotation,
)


BANNER_ASSET_FILENAMES = {
    "The Grand Library": "grand-library.png",
    "Reading Nook": "reading-nook.png",
    "Modern Library": "modern-library.png",
    "Candlelit Study": "candlelit-study.png",
    "Rainy Afternoon": "rainy-afternoon.png",
    "Woodland Library": "woodland-library.png",
    "Infinite Library": "infinite-library.png",
    "By the light of a warm Fire": "warm-fire.png",
}
BannerChooser = Callable[[tuple[str, ...]], str]


@dataclass(frozen=True)
class BannerSelection:
    """One validated banner name and its optional image asset."""

    name: str
    asset_path: Path | None


class BannerService:
    """Resolve fixed or once-per-launch banner preferences safely."""

    def __init__(
        self,
        asset_directory: Path | None = None,
        *,
        choose_banner: BannerChooser = random.choice,
    ) -> None:
        self._asset_directory = (
            asset_directory
            if asset_directory is not None
            else _default_asset_directory()
        )
        available_names = self._available_names()
        self._startup_name = (
            choose_banner(available_names)
            if available_names
            else DEFAULT_BANNER_NAME
        )
        if self._startup_name not in BANNER_NAMES:
            self._startup_name = DEFAULT_BANNER_NAME

    def resolve(
        self,
        preferences: HomePreferences,
    ) -> BannerSelection:
        """Return a usable selected asset or the safest fallback."""
        rotation = normalise_banner_rotation(
            preferences.banner_rotation
        )
        preferred_name = (
            self._startup_name
            if rotation is BannerRotation.STARTUP
            else normalise_banner_name(preferences.banner_name)
        )
        return self._resolve_available(preferred_name)

    def _resolve_available(self, preferred_name: str) -> BannerSelection:
        preferred_path = self._path_for(preferred_name)
        if preferred_path.is_file():
            return BannerSelection(preferred_name, preferred_path)

        default_path = self._path_for(DEFAULT_BANNER_NAME)
        if default_path.is_file():
            return BannerSelection(DEFAULT_BANNER_NAME, default_path)

        available_names = self._available_names()
        if available_names:
            name = available_names[0]
            return BannerSelection(name, self._path_for(name))

        return BannerSelection(DEFAULT_BANNER_NAME, None)

    def _available_names(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in BANNER_NAMES
            if self._path_for(name).is_file()
        )

    def _path_for(self, name: str) -> Path:
        filename = BANNER_ASSET_FILENAMES.get(
            name,
            BANNER_ASSET_FILENAMES[DEFAULT_BANNER_NAME],
        )
        return self._asset_directory / filename


def _default_asset_directory() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root) / "design" / "banner-sources"
    return (
        Path(__file__).resolve().parents[2]
        / "design"
        / "banner-sources"
    )

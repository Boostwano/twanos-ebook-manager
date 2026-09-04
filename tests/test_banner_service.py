"""Tests for RC6.4 banner preferences and selection."""

from pathlib import Path
import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage

from preferences import (
    BANNER_NAMES,
    DEFAULT_BANNER_NAME,
    BannerRotation,
    HomePreferences,
    PreferencesStore,
)
from services import banner_service
from services.banner_service import BannerService


def _settings(tmp_path: Path) -> QSettings:
    return QSettings(
        str(tmp_path / "preferences.ini"),
        QSettings.Format.IniFormat,
    )


def test_legacy_banner_preferences_are_validated_and_migrated(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    settings.setValue("home/banner_name", "grand-library")
    settings.setValue("home/banner_rotation", "seasonal")

    preferences = PreferencesStore(settings).load_home_preferences()

    assert preferences.banner_name == DEFAULT_BANNER_NAME
    assert preferences.banner_rotation is BannerRotation.STARTUP
    assert settings.value("home/banner_name") == DEFAULT_BANNER_NAME
    assert settings.value("home/banner_rotation") == "startup"


def test_invalid_banner_preferences_fall_back_and_are_persisted(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    settings.setValue("home/banner_name", "Not A Real Banner")
    settings.setValue("home/banner_rotation", "unknown")

    preferences = PreferencesStore(settings).load_home_preferences()

    assert preferences.banner_name == DEFAULT_BANNER_NAME
    assert preferences.banner_rotation is BannerRotation.FIXED
    assert settings.value("home/banner_name") == DEFAULT_BANNER_NAME
    assert settings.value("home/banner_rotation") == "fixed"


def test_fixed_banner_uses_selected_available_asset(
    tmp_path: Path,
) -> None:
    asset_directory = tmp_path / "banners"
    asset_directory.mkdir()
    selected_path = asset_directory / "reading-nook.png"
    selected_path.write_bytes(b"image")

    selection = BannerService(asset_directory).resolve(
        HomePreferences(
            banner_name="Reading Nook",
            banner_rotation=BannerRotation.FIXED,
        )
    )

    assert selection.name == "Reading Nook"
    assert selection.asset_path == selected_path


def test_all_eight_bundled_banner_assets_resolve() -> None:
    asset_directory = (
        Path(__file__).resolve().parents[1]
        / "design"
        / "banner-sources"
    )
    service = BannerService(asset_directory)

    for banner_name in BANNER_NAMES:
        selection = service.resolve(
            HomePreferences(
                banner_name=banner_name,
                banner_rotation=BannerRotation.FIXED,
            )
        )
        assert selection.name == banner_name
        assert selection.asset_path is not None
        assert selection.asset_path.is_file()


def test_all_bundled_banners_have_transparent_title_overlays() -> None:
    project_directory = Path(__file__).resolve().parents[1]
    banner_directory = project_directory / "design" / "banner-sources"
    overlay_directory = (
        project_directory / "design" / "banner-title-overlays"
    )
    background_directory = (
        project_directory / "design" / "banner-backgrounds"
    )

    for banner_path in banner_directory.glob("*.png"):
        overlay_path = (
            overlay_directory / f"{banner_path.stem}-title.png"
        )
        image = QImage(str(overlay_path))

        assert overlay_path.is_file()
        assert not image.isNull()
        assert image.hasAlphaChannel()
        assert image.pixelColor(0, 0).alpha() == 0
        background_path = (
            background_directory
            / f"{banner_path.stem}-background.png"
        )
        background = QImage(str(background_path))
        assert background_path.is_file()
        assert not background.isNull()


def test_startup_rotation_selects_once_for_the_service_lifetime(
    tmp_path: Path,
) -> None:
    asset_directory = tmp_path / "banners"
    asset_directory.mkdir()
    (asset_directory / "grand-library.png").write_bytes(b"one")
    chosen_path = asset_directory / "modern-library.png"
    chosen_path.write_bytes(b"two")
    calls = []

    def choose(names: tuple[str, ...]) -> str:
        calls.append(names)
        return "Modern Library"

    service = BannerService(
        asset_directory,
        choose_banner=choose,
    )
    preferences = HomePreferences(
        banner_name="The Grand Library",
        banner_rotation=BannerRotation.STARTUP,
    )

    first = service.resolve(preferences)
    second = service.resolve(preferences)

    assert first == second
    assert first.name == "Modern Library"
    assert first.asset_path == chosen_path
    assert len(calls) == 1


def test_missing_selected_asset_uses_default_then_any_available(
    tmp_path: Path,
) -> None:
    asset_directory = tmp_path / "banners"
    asset_directory.mkdir()
    default_path = asset_directory / "grand-library.png"
    default_path.write_bytes(b"default")
    preferences = HomePreferences(
        banner_name="Reading Nook",
        banner_rotation=BannerRotation.FIXED,
    )

    default_selection = BannerService(asset_directory).resolve(
        preferences
    )
    assert default_selection.name == DEFAULT_BANNER_NAME
    assert default_selection.asset_path == default_path

    default_path.unlink()
    available_path = asset_directory / "woodland-library.png"
    available_path.write_bytes(b"available")
    available_selection = BannerService(asset_directory).resolve(
        preferences
    )
    assert available_selection.name == "Woodland Library"
    assert available_selection.asset_path == available_path


def test_no_banner_assets_returns_painted_fallback(
    tmp_path: Path,
) -> None:
    selection = BannerService(tmp_path).resolve(HomePreferences())

    assert selection.name == DEFAULT_BANNER_NAME
    assert selection.asset_path is None


def test_packaged_banner_service_uses_pyinstaller_bundle_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    banner_directory = tmp_path / "design" / "banner-sources"
    banner_directory.mkdir(parents=True)
    bundled_banner = banner_directory / "grand-library.png"
    bundled_banner.write_bytes(b"image")

    assert banner_service._default_asset_directory() == (
        banner_directory
    )
    selection = BannerService().resolve(HomePreferences())
    assert selection.asset_path == bundled_banner

"""Tests for the approved RC1 branding and startup splash."""

from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

from ui import branding
from ui.branding import BRAND_TAGLINE, branding_asset_path
from ui.sidebar import BrandLogo
from ui.splash_screen import SPLASH_DISPLAY_MS, TwanoSplashScreen


def test_approved_branding_assets_and_wording_are_available() -> None:
    assert BRAND_TAGLINE == "Your Library, Beautifully Organised"
    assert branding_asset_path("twano-splash-rc1.png").is_file()
    assert branding_asset_path("twano-splash-panel-rc1.png").is_file()
    assert branding_asset_path("twano-book-logo.png").is_file()
    assert branding_asset_path("twano-book-logo.ico").is_file()


def test_splash_and_sidebar_logo_load_approved_artwork() -> None:
    application = QApplication.instance() or QApplication([])
    splash = TwanoSplashScreen()
    logo = BrandLogo()

    assert not splash.pixmap().isNull()
    assert splash.objectName() == "twanoSplashScreen"
    assert splash.pixmap().width() <= 636
    assert splash.pixmap().height() < splash.pixmap().width()
    splash_image = splash.pixmap().toImage()
    assert splash_image.size().width() == 630
    assert splash_image.size().height() == 358
    assert splash_image.pixelColor(0, 0).alpha() > 0
    assert (
        splash_image.pixelColor(0, 0).red(),
        splash_image.pixelColor(0, 0).green(),
        splash_image.pixelColor(0, 0).blue(),
    ) == (57, 172, 231)
    assert splash_image.pixelColor(
        splash_image.width() // 2,
        splash_image.height() // 2,
    ).alpha() > 0
    right_frame = splash_image.pixelColor(
        splash_image.width() - 1,
        splash_image.height() // 2,
    )
    bottom_frame = splash_image.pixelColor(
        splash_image.width() // 2,
        splash_image.height() - 1,
    )
    assert right_frame.alpha() > 0
    assert right_frame.blue() > right_frame.red()
    assert bottom_frame.alpha() > 0
    assert bottom_frame.blue() > bottom_frame.red()
    expected_border = (57, 172, 231)
    border_points = (
        (splash_image.width() // 2, 1),
        (1, splash_image.height() // 2),
        (splash_image.width() - 2, splash_image.height() // 2),
        (splash_image.width() // 2, splash_image.height() - 2),
    )
    assert all(
        (
            splash_image.pixelColor(x, y).red(),
            splash_image.pixelColor(x, y).green(),
            splash_image.pixelColor(x, y).blue(),
        )
        == expected_border
        for x, y in border_points
    )
    assert splash.mask().isEmpty()
    assert not logo._pixmap.isNull()

    splash.close()
    logo.close()
    application.processEvents()


def test_splash_uses_a_visible_fade_out_animation() -> None:
    application = QApplication.instance() or QApplication([])
    splash = TwanoSplashScreen()
    completed: list[bool] = []

    splash.fade_out(lambda: completed.append(True))

    assert splash._fade_animation is not None
    assert splash._fade_animation.duration() == 650
    assert splash._fade_animation.startValue() == 1.0
    assert splash._fade_animation.endValue() == 0.0
    assert completed == []

    splash._fade_animation.stop()
    splash.close()
    application.processEvents()


def test_splash_remains_visible_for_five_seconds() -> None:
    assert SPLASH_DISPLAY_MS == 5_000


def test_main_application_opens_maximized_after_the_splash() -> None:
    project_root = Path(__file__).resolve().parents[1]
    application_source = (project_root / "src" / "app.py").read_text(
        encoding="utf-8"
    )

    assert "window.showMaximized()" in application_source


def test_packaged_branding_uses_pyinstaller_bundle_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert branding.branding_asset_path("logo.png") == (
        tmp_path / "design" / "branding" / "logo.png"
    )


def test_windows_package_uses_full_product_name_and_book_icon() -> None:
    project_root = Path(__file__).resolve().parents[1]
    installer_script = (
        project_root / "packaging" / "Twano.iss"
    ).read_text(encoding="utf-8")
    build_script = (
        project_root / "tools" / "build_windows_app.ps1"
    ).read_text(encoding="utf-8")

    assert 'ProductName "Twano\'s eBook Manager"' in installer_script
    assert "OutputBaseFilename=Twano's eBook Manager Setup" in (
        installer_script
    )
    assert "UninstallDisplayIcon={app}\\{#ExecutableName}" in (
        installer_script
    )
    assert "--name $ExecutableBaseName" in build_script
    assert "--icon $IconPath" in build_script

"""Application entry point for Twano's eBook Manager."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from threading import Thread

from PySide6.QtCore import QElapsedTimer, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from config import APP_VERSION
from database.database import APP_DATA_FOLDER
from main_window import MainWindow
from preferences import OrganizationPreferences, PreferencesStore
from services.provider_update_service import ProviderUpdateService
from ui.splash_screen import SPLASH_DISPLAY_MS, TwanoSplashScreen


LOG_FOLDER = APP_DATA_FOLDER / "logs"
LOG_FILE = LOG_FOLDER / "twano.log"


def _configure_logging() -> None:
    """Log to the console as before, and now also to a rotating file.

    The file gives the Diagnostic Report something real to draw from when
    a user hits an error; two 2 MB backups keep it bounded indefinitely.
    """
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        LOG_FOLDER.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                LOG_FILE,
                maxBytes=2 * 1024 * 1024,
                backupCount=2,
                encoding="utf-8",
            )
        )
    except OSError:
        pass
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=handlers)


def _maybe_show_destination_folder_prompt(window: MainWindow) -> None:
    """Introduce the destination-folder setting once, on its first run."""
    preferences = window.preferences
    organisation = preferences.load_organization_preferences()
    if organisation.destination_prompt_shown:
        return
    QMessageBox.information(
        window,
        "Choose Where Books Are Organised",
        "Twano can move every correctly identified book — and anything "
        "you delete — into one destination folder of your choosing, "
        "instead of organising each watched library on its own.\n\n"
        "You can set this any time from Settings → File Organisation. "
        "Leave it unset to keep organising each book inside its own "
        "watched library, as before.",
    )
    preferences.save_organization_preferences(
        OrganizationPreferences(
            destination_folder=organisation.destination_folder,
            destination_prompt_shown=True,
        )
    )
    preferences.sync()


def main() -> int:
    """Start the desktop application."""
    _configure_logging()
    application = QApplication(sys.argv)
    application.setApplicationName("Twano's eBook Manager")
    application.setApplicationVersion(APP_VERSION)
    application.setOrganizationName("Boostwano")

    provider_updates = ProviderUpdateService()
    provider_updates.apply_cached()

    startup_timer = QElapsedTimer()
    startup_timer.start()
    splash = TwanoSplashScreen()
    splash.show()
    application.processEvents()

    accessibility = PreferencesStore().load_accessibility_preferences()
    font = application.font()
    base_size = font.pointSizeF()
    if base_size > 0:
        font.setPointSizeF(
            base_size * accessibility.text_scale_percent / 100.0
        )
        application.setFont(font)

    window = MainWindow()
    Thread(
        target=provider_updates.refresh_and_apply,
        kwargs={"plugin_service": window.plugin_service},
        daemon=True,
        name="twano-provider-updates",
    ).start()

    def show_main_window() -> None:
        window.showMaximized()
        splash.fade_out(lambda: splash.finish(window))
        _maybe_show_destination_folder_prompt(window)

    remaining_ms = max(
        0,
        SPLASH_DISPLAY_MS - startup_timer.elapsed(),
    )
    QTimer.singleShot(remaining_ms, show_main_window)

    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

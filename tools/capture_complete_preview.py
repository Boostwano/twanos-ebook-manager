"""Capture deterministic complete-package UI smoke screenshots."""

from __future__ import annotations

import argparse
import atexit
import os
from pathlib import Path
import shutil
import sys
import tempfile
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CAPTURE_DATA_ROOT = Path(
    tempfile.mkdtemp(prefix="Twano-Beta2-capture-data-")
)
os.environ.setdefault("TWANO_DATA_FOLDER", str(CAPTURE_DATA_ROOT))
atexit.register(
    lambda: shutil.rmtree(CAPTURE_DATA_ROOT, ignore_errors=True)
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from core.scanner import BookFile
from database.database import DatabaseManager
from main_window import MainWindow
from preferences import PreferencesStore
from services.dashboard_service import DashboardService
from services.library_service import LibraryService
from services.metadata_studio_service import (
    MetadataCandidate,
    ProviderSearchReport,
)
from services.protection_service import ProtectionService
from services.scan_service import ScanService


def _wait(application: QApplication, predicate, seconds: float = 8.0) -> None:
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        application.processEvents()
        if predicate():
            return
    raise RuntimeError("UI smoke operation timed out.")


def _metadata_candidate() -> MetadataCandidate:
    return MetadataCandidate(
        title="The Example Book",
        author="A. Reader",
        isbn="9780261103344",
        publisher="Twano Press",
        language="en",
        published_date="2026",
        cover_id=None,
        work_key="example",
        confidence=90,
        confidence_reason="Exact title and author match",
        provider_name="Google Books",
        remote_cover_url="https://books.google.com/example.jpg",
    )


def capture(output_folder: Path) -> tuple[Path, ...]:
    output_folder.mkdir(parents=True, exist_ok=True)
    application = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="Twano-Beta2-capture-") as folder:
        root = Path(folder)
        library = root / "Demo Library"
        library.mkdir()
        first = library / "The Example Book.epub"
        second = library / "The Example Book Copy.epub"
        first.write_bytes(b"deterministic duplicate content")
        second.write_bytes(b"deterministic duplicate content")
        preview_cover = root / "example-cover.png"
        preview_pixmap = QPixmap(120, 180)
        preview_pixmap.fill(QColor("#315f88"))
        if not preview_pixmap.save(str(preview_cover)):
            raise RuntimeError("Could not create deterministic cover preview")
        database_path = root / "library.db"
        database = DatabaseManager(database_path)
        database.save_scan_results(
            library,
            [
                BookFile(
                    first.stem,
                    "EPUB",
                    first.stat().st_size,
                    first,
                ),
                BookFile(
                    second.stem,
                    "EPUB",
                    second.stat().st_size,
                    second,
                ),
            ],
        )
        database.update_book_metadata(
            first,
            title="The Example Book",
            author="A. Reader",
            isbn="9780261103344",
            publisher="Twano Press",
            language="en",
            published_date="2026",
            metadata_status="embedded",
        )
        database.update_book_metadata(
            second,
            title="The Example Book",
            author="A. Reader",
            isbn="9780261103344",
            publisher=None,
            language="en",
            published_date=None,
            metadata_status="pending",
        )
        preferences = PreferencesStore(
            QSettings(
                str(root / "preferences.ini"),
                QSettings.Format.IniFormat,
            )
        )
        window = MainWindow(
            library_service=LibraryService(database),
            dashboard_service=DashboardService(database),
            preferences=preferences,
            scan_service_factory=lambda: ScanService(
                DatabaseManager(database_path)
            ),
            protection_service_factory=lambda: ProtectionService(
                DatabaseManager(database_path)
            ),
        )
        captures: list[Path] = []
        window.resize(1180, 760)
        window.show()
        application.processEvents()
        for page_id, filename in (
            ("home", "01-home.png"),
            ("library", "02-library.png"),
            ("metadata", "03-metadata.png"),
            ("library_health", "04-health.png"),
            ("plugins", "05-plugins.png"),
            ("duplicates", "06-duplicates.png"),
        ):
            if page_id == "metadata":
                window.resize(1600, 900)
            else:
                window.resize(1180, 760)
            window._show_page(page_id)
            if page_id == "metadata":
                window.metadata_page.service.last_search_report = (
                    ProviderSearchReport(
                        searched_providers=(
                            "Open Library",
                            "Google Books",
                            "Hardcover",
                            "Comic Vine",
                        ),
                        cover_providers=("Google Books",),
                    )
                )
                window.metadata_page._lookup_completed(
                    (_metadata_candidate(),)
                )
                window.metadata_page._cover_preview_downloaded(
                    str(preview_cover)
                )
            if page_id == "duplicates":
                _wait(
                    application,
                    lambda: not window.duplicate_page.is_busy(),
                )
            application.processEvents()
            destination = output_folder / filename
            if not window.grab().save(str(destination)):
                raise RuntimeError(f"Could not save {destination}")
            captures.append(destination)
        window.resize(900, 600)
        window._show_page("metadata")
        window.metadata_page.service.last_search_report = ProviderSearchReport(
            searched_providers=(
                "Open Library",
                "Google Books",
                "Hardcover",
                "Comic Vine",
            ),
            cover_providers=("Google Books",),
        )
        window.metadata_page._lookup_completed(
            (_metadata_candidate(),)
        )
        window.metadata_page._cover_preview_downloaded(str(preview_cover))
        application.processEvents()
        compact = output_folder / "07-metadata-compact.png"
        if not window.grab().save(str(compact)):
            raise RuntimeError(f"Could not save {compact}")
        captures.append(compact)
        window.close()
        application.processEvents()
    return tuple(captures)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    captures = capture(arguments.output.resolve())
    for path in captures:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

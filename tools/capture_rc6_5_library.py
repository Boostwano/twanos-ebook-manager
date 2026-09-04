"""Capture deterministic RC6.5 Library smoke-test screenshots."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, sleep
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QItemSelectionModel, QSettings  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from database.database import DatabaseManager  # noqa: E402
from main_window import MainWindow  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from services.dashboard_service import DashboardService  # noqa: E402
from services.library_service import LibraryService  # noqa: E402


def _wait(application: QApplication, predicate, timeout: float = 5.0) -> None:
    deadline = perf_counter() + timeout
    while not predicate() and perf_counter() < deadline:
        application.processEvents()
        sleep(0.01)
    application.processEvents()
    if not predicate():
        raise RuntimeError("Library smoke-test query timed out.")


def _populate(database: DatabaseManager, folder: Path) -> None:
    timestamp = "2026-07-28T00:00:00+00:00"
    covers = []
    for index, color in enumerate(
        ("#2b6787", "#78518d", "#8b6132", "#3d7851", "#8b3f54"),
        1,
    ):
        path = folder / f"cover-{index}.png"
        image = QImage(360, 520, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        image.save(str(path), "PNG")
        covers.append(path)

    with database.connection() as connection:
        library = connection.execute(
            """
            INSERT INTO libraries (
                folder_path,
                created_at,
                last_scanned_at
            )
            VALUES (?, ?, ?)
            """,
            (str(folder), timestamp, timestamp),
        )
        library_id = int(library.lastrowid)
        for index in range(36):
            cover = str(covers[index % len(covers)]) if index % 4 else ""
            connection.execute(
                """
                INSERT INTO books (
                    library_id,
                    file_path,
                    file_name,
                    title,
                    author,
                    isbn,
                    publisher,
                    language,
                    published_date,
                    series,
                    series_number,
                    description,
                    cover_path,
                    file_format,
                    file_size,
                    file_modified_at,
                    discovered_at,
                    last_seen_at,
                    metadata_status,
                    review_required,
                    is_missing
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, 0
                )
                """,
                (
                    library_id,
                    str(folder / f"Book {index + 1}.epub"),
                    f"Book {index + 1}.epub",
                    (
                        "The Cartographer's Quiet Library"
                        if index == 0
                        else f"Living Library Book {index + 1}"
                    ),
                    f"Author {index % 8 + 1}",
                    f"97800000{index:05d}",
                    f"Publisher {index % 5 + 1}",
                    "en",
                    str(1990 + index % 30),
                    f"Chronicles {index % 6 + 1}",
                    float(index % 9 + 1),
                    (
                        "A representative description used to verify the "
                        "responsive details panel, missing states and "
                        "selectable catalogue facts."
                    ),
                    cover,
                    ("EPUB", "PDF", "MOBI")[index % 3],
                    800_000 + index * 12_000,
                    timestamp,
                    timestamp,
                    timestamp,
                    "embedded" if index % 3 else "pending",
                    1 if index % 5 == 0 else 0,
                ),
            )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: capture_rc6_5_library.py OUTPUT_FOLDER")
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    application = QApplication.instance() or QApplication([])

    with TemporaryDirectory(
        prefix="Twano-RC65-smoke-",
        ignore_cleanup_errors=True,
    ) as temp:
        folder = Path(temp)
        database = DatabaseManager(folder / "smoke.db")
        _populate(database, folder)
        settings = QSettings(
            str(folder / "settings.ini"),
            QSettings.Format.IniFormat,
        )
        preferences = PreferencesStore(settings)
        library_service = LibraryService(database)
        window = MainWindow(
            library_service=library_service,
            dashboard_service=DashboardService(database),
            preferences=preferences,
        )
        window.resize(1680, 980)
        window.show()
        window._show_page("library")
        _wait(
            application,
            lambda: (
                not window.library_page.model.loading
                and window.library_page.model.rowCount() == 36
            ),
        )
        index = window.library_page.model.index(0, 0)
        window.library_page.selection_model.setCurrentIndex(
            index,
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows,
        )
        _wait(
            application,
            lambda: (
                window.library_page.thumbnail_cache.item_count > 0
            ),
        )
        application.processEvents()
        window.grab().save(str(output / "rc6-5-library-wide.png"))

        window.resize(1180, 790)
        application.processEvents()
        window.grab().save(
            str(output / "rc6-5-library-restored.png")
        )

        window.resize(1000, 720)
        application.processEvents()
        window.grab().save(str(output / "rc6-5-library-compact-grid.png"))

        window.library_page._activate_details(index)
        application.processEvents()
        window.grab().save(
            str(output / "rc6-5-library-compact-details.png")
        )
        window.close()
        application.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

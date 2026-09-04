"""Background worker for library scanning and metadata extraction."""

import logging
from collections.abc import Callable
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from core.scanner import BookFile
from services.scan_service import ScanService


logger = logging.getLogger(__name__)

class ScanWorker(QObject):
    """Scan an eBook folder without blocking the application interface."""

    discovery_started = Signal()
    processing_started = Signal(int)
    progress_changed = Signal(int, int)
    current_file_changed = Signal(str)
    book_processed = Signal(object)
    status_changed = Signal(str)

    completed = Signal(int, int)
    cancelled = Signal(int, int)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        library_folder: str | Path,
        service_factory: Callable[[], ScanService],
    ) -> None:
        super().__init__()

        self.library_folder = Path(library_folder)
        self._service_factory = service_factory
        self._cancel_event = Event()

    def request_cancel(self) -> None:
        """Request that the scan stop at the next safe opportunity."""
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        """Discover files, save them and extract available metadata."""
        discovered_books: list[BookFile] = []
        processed_count = 0
        metadata_count = 0

        try:
            service = self._service_factory()
            service.validate_library_folder(self.library_folder)

            self.discovery_started.emit()
            self.status_changed.emit("Discovering supported eBook files…")

            discovered_books = service.discover_books(
                self.library_folder,
                is_cancelled=self._cancel_event.is_set,
                on_discovery_count=self._on_discovery_count,
            )

            if self._cancel_event.is_set():
                self.cancelled.emit(0, len(discovered_books))
                return

            total_books = len(discovered_books)
            self.processing_started.emit(total_books)

            if total_books == 0:
                self.status_changed.emit("No supported eBook files were found.")
                self.completed.emit(0, 0)
                return

            self.status_changed.emit(
                f"Saving {total_books:,} discovered books…"
            )

            service.save_discovered_books(
                self.library_folder,
                discovered_books,
            )

            for index, book in enumerate(discovered_books, start=1):
                if self._cancel_event.is_set():
                    self.cancelled.emit(processed_count, total_books)
                    return

                self.current_file_changed.emit(book.path.name)

                metadata = service.process_metadata(book)

                if metadata.extraction_status == "embedded":
                    metadata_count += 1

                processed_count = index
                self.book_processed.emit(book)
                self.progress_changed.emit(index, total_books)

            self.status_changed.emit("Library scan completed.")
            logger.info(
                "Scan database work committed; signalling completion "
                "books=%s metadata=%s",
                total_books,
                metadata_count,
            )
            self.completed.emit(total_books, metadata_count)

        except (
            FileNotFoundError,
            NotADirectoryError,
            PermissionError,
            OSError,
        ) as error:
            self.failed.emit(str(error))

        except Exception as error:
            self.failed.emit(
                f"An unexpected scanning error occurred:\n\n{error}"
            )

        finally:
            logger.info(
                "Scan worker finished folder=%s processed=%s discovered=%s",
                self.library_folder,
                processed_count,
                len(discovered_books),
            )
            self.finished.emit()

    def _on_discovery_count(self, count: int) -> None:
        """Forward discovery progress from the service to the UI."""
        self.status_changed.emit(
            f"Discovered {count:,} books…"
        )

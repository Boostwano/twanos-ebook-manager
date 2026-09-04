"""Background read-only connection check for one watched source."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal, Slot

from services.scan_service import ScanService


class SourceConnectionWorker(QObject):
    """Create and use its scan service entirely in the worker thread."""

    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        source_id: int,
        service_factory: Callable[[], ScanService],
    ) -> None:
        super().__init__()
        self._source_id = int(source_id)
        self._service_factory = service_factory

    @Slot()
    def run(self) -> None:
        try:
            result = self._service_factory().test_source(self._source_id)
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(
                "The source connection test could not finish:\n\n"
                f"{error}"
            )
        finally:
            self.finished.emit()

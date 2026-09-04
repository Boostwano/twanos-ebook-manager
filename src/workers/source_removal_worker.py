"""Background worker for atomic watched-source catalogue removal."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal, Slot

from services.scan_service import ScanService


class SourceRemovalWorker(QObject):
    """Remove one watch without touching its folder or ebook files."""

    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        source_id: int,
        service_factory: Callable[[], ScanService],
    ) -> None:
        super().__init__()
        self.source_id = int(source_id)
        self.service_factory = service_factory

    @Slot()
    def run(self) -> None:
        try:
            result = self.service_factory().remove_source(self.source_id)
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()

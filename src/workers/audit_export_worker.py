"""Background export of one persistent protection-operation report."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from services.protection_service import (
    ProtectionService,
    ReportExportCancelled,
)


class AuditExportWorker(QObject):
    """Create its service and export one report in the worker thread."""

    completed = Signal(str)
    cancelled = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        operation_id: int,
        destination: str | Path,
        service_factory: Callable[[], ProtectionService],
    ) -> None:
        super().__init__()
        self._operation_id = int(operation_id)
        self._destination = Path(destination)
        self._service_factory = service_factory
        self._cancel_event = Event()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            path = self._service_factory().export_operation_report(
                self._operation_id,
                self._destination,
                overwrite=True,
                is_cancelled=self._cancel_event.is_set,
            )
            self.completed.emit(str(path))
        except ReportExportCancelled:
            self.cancelled.emit("Operation-report export cancelled safely.")
        except Exception as error:
            self.failed.emit(
                "The operation report could not be exported:\n\n"
                f"{error}"
            )
        finally:
            self.finished.emit()

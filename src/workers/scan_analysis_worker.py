"""Background RC6.6 source analysis with no catalogue mutation."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from services.scan_service import ScanService


class ScanAnalysisWorker(QObject):
    """Analyse one configured source and return an immutable preview."""

    analysis_started = Signal()
    current_location_changed = Signal(str)
    discovery_count_changed = Signal(int)
    status_changed = Signal(str)
    completed = Signal(object)
    cancelled = Signal(object)
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
        self._cancel_event = Event()

    def request_cancel(self) -> None:
        """Request cancellation at the next discovery boundary."""
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            self.analysis_started.emit()
            self.status_changed.emit(
                "Analysing source without changing the Library…"
            )
            result = self._service_factory().analyse_source(
                self._source_id,
                is_cancelled=self._cancel_event.is_set,
                on_current_location=self.current_location_changed.emit,
                on_discovery_count=self.discovery_count_changed.emit,
            )
            if result.cancelled:
                self.cancelled.emit(result)
            else:
                self.completed.emit(result)
        except Exception as error:
            self.failed.emit(
                "The source analysis could not finish:\n\n"
                f"{error}"
            )
        finally:
            self.finished.emit()

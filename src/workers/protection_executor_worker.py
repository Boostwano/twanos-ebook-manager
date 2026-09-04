"""Background execution of approved RC6.7 protected operations."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from preferences import ProtectionMode
from services.protection_service import (
    BackupCancelled,
    BackupPolicy,
    ProtectionService,
)


class ProtectionExecutorWorker(QObject):
    """Own one executor service entirely inside its worker thread."""

    progress_changed = Signal(int, str)
    completed = Signal(object)
    cancelled = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        operation_id: int,
        policy: BackupPolicy,
        protection_mode: ProtectionMode,
        service_factory: Callable[[], ProtectionService],
    ) -> None:
        super().__init__()
        self._operation_id = int(operation_id)
        self._policy = policy
        self._protection_mode = ProtectionMode(protection_mode)
        self._service_factory = service_factory
        self._cancel_event = Event()

    def request_cancel(self) -> None:
        """Request cancellation before the atomic database transaction."""
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            result = self._service_factory().apply_approved_operation(
                self._operation_id,
                self._policy,
                self._protection_mode,
                is_cancelled=self._cancel_event.is_set,
                on_progress=self.progress_changed.emit,
            )
            self.completed.emit(result)
        except BackupCancelled:
            self.cancelled.emit(
                "Protected operation cancelled before catalogue mutation."
            )
        except Exception as error:
            self.failed.emit(
                "The protected operation could not finish:\n\n"
                f"{error}"
            )
        finally:
            self.finished.emit()

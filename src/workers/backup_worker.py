"""Background creation and verification of RC6.7 database backups."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from services.protection_service import (
    BackupCancelled,
    BackupPolicy,
    ProtectionService,
)


class BackupWorker(QObject):
    """Own one backup service entirely inside its worker thread."""

    progress_changed = Signal(int, str)
    completed = Signal(object)
    cancelled = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        operation: str,
        service_factory: Callable[[], ProtectionService],
        *,
        policy: BackupPolicy | None = None,
        backup_path: str | Path | None = None,
    ) -> None:
        super().__init__()
        if operation not in {"create", "verify", "preview_cleanup"}:
            raise ValueError(f"Unknown backup operation: {operation}")
        if operation in {"create", "preview_cleanup"} and policy is None:
            raise ValueError(
                "Backup creation and cleanup review require a policy."
            )
        if operation == "verify" and backup_path is None:
            raise ValueError("Backup verification requires a path.")
        self._operation = operation
        self._service_factory = service_factory
        self._policy = policy
        self._backup_path = (
            Path(backup_path) if backup_path is not None else None
        )
        self._cancel_event = Event()

    def request_cancel(self) -> None:
        """Request cancellation at the next safe operation boundary."""
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            service = self._service_factory()
            if self._operation == "create":
                result = service.create_verified_backup(
                    self._policy,
                    is_cancelled=self._cancel_event.is_set,
                    on_progress=self.progress_changed.emit,
                )
            elif self._operation == "verify":
                result = service.verify_backup(
                    self._backup_path,
                    is_cancelled=self._cancel_event.is_set,
                    on_progress=self.progress_changed.emit,
                )
            else:
                result = service.preview_retention_cleanup(
                    self._policy,
                    is_cancelled=self._cancel_event.is_set,
                    on_progress=self.progress_changed.emit,
                )
            self.completed.emit(result)
        except BackupCancelled:
            self.cancelled.emit("Backup operation cancelled safely.")
        except Exception as error:
            self.failed.emit(
                "The backup operation could not finish:\n\n"
                f"{error}"
            )
        finally:
            self.finished.emit()

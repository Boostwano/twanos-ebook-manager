"""Background worker for guarded transactional preview application."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from services.scan_service import (
    ScanAnalysisResult,
    ScanApplyStatus,
    ScanService,
)
from preferences import ProtectionMode


class ScanApplyWorker(QObject):
    """Recheck and apply one approved preview outside the GUI thread."""

    current_item_changed = Signal(str)
    progress_changed = Signal(int, int)
    backup_progress_changed = Signal(int, str)
    status_changed = Signal(str)
    completed = Signal(object)
    cancelled = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        analysis: ScanAnalysisResult,
        service_factory: Callable[[], ScanService],
        *,
        backup_folder: str | Path | None = None,
        retention_days: int = 0,
        protection_mode: ProtectionMode | str = ProtectionMode.STANDARD,
    ) -> None:
        super().__init__()
        self._analysis = analysis
        self._service_factory = service_factory
        self._backup_folder = backup_folder
        self._retention_days = int(retention_days)
        self._protection_mode = protection_mode
        self._cancel_event = Event()

    def request_cancel(self) -> None:
        """Cancel before the database transaction begins."""
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            self.status_changed.emit(
                "Rechecking preview and refreshing changed metadata…"
            )
            result = self._service_factory().apply_analysis(
                self._analysis,
                is_cancelled=self._cancel_event.is_set,
                on_current_item=self.current_item_changed.emit,
                on_progress=self.progress_changed.emit,
                on_status=self.status_changed.emit,
                on_backup_progress=self.backup_progress_changed.emit,
                backup_folder=self._backup_folder,
                retention_days=self._retention_days,
                protection_mode=self._protection_mode,
            )
            if result.status == ScanApplyStatus.CANCELLED:
                self.cancelled.emit(result)
            else:
                self.completed.emit(result)
        except Exception as error:
            self.failed.emit(
                "The preview could not be applied. Catalogue changes were "
                "rolled back.\n\n"
                f"{error}"
            )
        finally:
            self.finished.emit()

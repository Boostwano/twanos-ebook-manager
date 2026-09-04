"""Background duplicate comparison worker."""

from PySide6.QtCore import QObject, Signal, Slot

from services.duplicate_service import DuplicateService


class DuplicateScanWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service: DuplicateService) -> None:
        super().__init__()
        self.service = service

    @Slot()
    def run(self) -> None:
        try:
            self.completed.emit(self.service.find_groups())
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()

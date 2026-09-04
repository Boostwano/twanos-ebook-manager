"""Background metadata lookup, direct cover search, and cover download."""

from __future__ import annotations

from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from services.library_service import LibraryRecord
from services.metadata_studio_service import (
    MetadataCandidate,
    MetadataStudioService,
)


class MetadataLookupWorker(QObject):
    """Run one network request without blocking the GUI thread."""

    candidates_ready = Signal(object)
    cover_ready = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        service: MetadataStudioService,
        *,
        title: str = "",
        author: str = "",
        isbn: str = "",
        file_name: str = "",
        cover_candidate: MetadataCandidate | None = None,
        cover_source_id: str = "",
        book_id: int = 0,
        preview_cover: bool = False,
        cache_days: int = 30,
        include_open_library: bool = True,
        provider_plugin_id: str = "",
    ) -> None:
        super().__init__()
        self.service = service
        self.title = title
        self.author = author
        self.isbn = isbn
        self.file_name = file_name
        self.cover_candidate = cover_candidate
        self.cover_source_id = cover_source_id
        self.book_id = int(book_id)
        self.preview_cover = bool(preview_cover)
        self.cache_days = int(cache_days)
        self.include_open_library = bool(include_open_library)
        self.provider_plugin_id = str(provider_plugin_id)

    @Slot()
    def run(self) -> None:
        try:
            if self.cover_candidate is not None:
                if self.preview_cover:
                    path = self.service.download_cover_preview(
                        self.cover_candidate,
                        book_id=self.book_id,
                    )
                else:
                    path = self.service.download_cover(
                        self.cover_candidate,
                        book_id=self.book_id,
                    )
                self.cover_ready.emit(str(path))
            elif self.cover_source_id:
                candidates = self.service.search_cover_candidates(
                    source_id=self.cover_source_id,
                    title=self.title,
                    author=self.author,
                    isbn=self.isbn,
                    file_name=self.file_name,
                    cache_days=self.cache_days,
                    include_open_library=self.include_open_library,
                )
                self.candidates_ready.emit(candidates)
            else:
                candidates = self.service.search_enabled_candidates(
                    title=self.title,
                    author=self.author,
                    isbn=self.isbn,
                    file_name=self.file_name,
                    cache_days=self.cache_days,
                    include_open_library=self.include_open_library,
                    provider_plugin_id=self.provider_plugin_id,
                )
                self.candidates_ready.emit(candidates)
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


class ProviderConnectionCheckWorker(QObject):
    """Run one manual provider connection check without blocking the GUI."""

    checked = Signal(str, str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        service: MetadataStudioService,
        plugin_id: str,
    ) -> None:
        super().__init__()
        self.service = service
        self.plugin_id = plugin_id

    @Slot()
    def run(self) -> None:
        try:
            status, message = self.service.check_provider_connection(
                self.plugin_id
            )
            self.checked.emit(status, message)
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


class MetadataBatchLookupWorker(QObject):
    """Prepare review candidates for several books without changing them."""

    result_ready = Signal(int, object, object)
    book_failed = Signal(int, str)
    progress_changed = Signal(int, int, str)
    completed = Signal(int, int)
    cancelled = Signal(int, int)
    finished = Signal()

    def __init__(
        self,
        service: MetadataStudioService,
        records: tuple[LibraryRecord, ...],
        *,
        cache_days: int = 30,
        include_open_library: bool = True,
        provider_plugin_id: str = "",
    ) -> None:
        super().__init__()
        self.service = service
        self.records = tuple(records)
        self.cache_days = int(cache_days)
        self.include_open_library = bool(include_open_library)
        self.provider_plugin_id = str(provider_plugin_id)
        self._cancel_requested = Event()

    def request_cancel(self) -> None:
        """Request a safe stop between provider searches."""
        self._cancel_requested.set()

    @Slot()
    def run(self) -> None:
        processed = 0
        matched = 0
        total = len(self.records)
        try:
            for record in self.records:
                if self._cancel_requested.is_set():
                    self.cancelled.emit(processed, matched)
                    return
                self.progress_changed.emit(
                    processed,
                    total,
                    f"Searching {record.title}",
                )
                try:
                    candidates = self.service.search_enabled_candidates(
                        title=record.title,
                        author=(
                            "" if record.author == "Unknown" else record.author
                        ),
                        isbn=record.isbn,
                        file_name=record.file_path,
                        cache_days=self.cache_days,
                        include_open_library=self.include_open_library,
                        provider_plugin_id=self.provider_plugin_id,
                    )
                    report = self.service.last_search_report
                    self.result_ready.emit(
                        record.book_id,
                        tuple(candidates),
                        report,
                    )
                    if candidates:
                        matched += 1
                except Exception as error:
                    self.book_failed.emit(record.book_id, str(error))
                processed += 1
                self.progress_changed.emit(
                    processed,
                    total,
                    f"Prepared {processed} of {total} books",
                )
                if self._cancel_requested.wait(0.2):
                    self.cancelled.emit(processed, matched)
                    return
            self.completed.emit(processed, matched)
        finally:
            self.finished.emit()

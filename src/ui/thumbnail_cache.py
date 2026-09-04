"""Background cover decoding with a bounded GUI-thread pixmap cache."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QSize,
    QThread,
    QThreadPool,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage, QImageReader, QPixmap

from services.library_service import LibraryRecord


ThumbnailKey = tuple[str, str, int, int]


@dataclass(frozen=True)
class _ThumbnailResult:
    key: ThumbnailKey
    book_id: int
    generation: int
    image: QImage | None
    error: str = ""


class _ThumbnailSignals(QObject):
    finished = Signal(object)


class _ThumbnailTask(QRunnable):
    """Decode and scale one cover entirely outside the GUI thread."""

    def __init__(
        self,
        key: ThumbnailKey,
        book_id: int,
        generation: int,
        size: QSize,
    ) -> None:
        super().__init__()
        self._key = key
        self._book_id = book_id
        self._generation = generation
        self._size = size
        self.signals = _ThumbnailSignals()

    @Slot()
    def run(self) -> None:
        path = Path(self._key[0])
        if not path.is_file():
            self._finish(None, "Cover file is unavailable.")
            return

        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            self._finish(
                None,
                reader.errorString() or "Cover image could not be decoded.",
            )
            return

        image = image.scaled(
            self._size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._finish(image)

    def _finish(
        self,
        image: QImage | None,
        error: str = "",
    ) -> None:
        self.signals.finished.emit(
            _ThumbnailResult(
                key=self._key,
                book_id=self._book_id,
                generation=self._generation,
                image=image,
                error=error,
            )
        )


class ThumbnailCache(QObject):
    """Own a bounded LRU cache of QPixmaps on the GUI thread."""

    thumbnail_ready = Signal(int)
    thumbnail_failed = Signal(int, str)

    def __init__(
        self,
        *,
        max_items: int = 192,
        thread_pool: QThreadPool | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if max_items <= 0:
            raise ValueError("Thumbnail cache size must be positive.")
        self._max_items = max_items
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._pixmaps: OrderedDict[ThumbnailKey, QPixmap] = OrderedDict()
        self._failures: dict[ThumbnailKey, str] = {}
        self._pending: set[tuple[ThumbnailKey, int]] = set()
        self._tasks: dict[
            tuple[ThumbnailKey, int],
            _ThumbnailTask,
        ] = {}
        self._generation = 0
        self._stale_results = 0

    @property
    def max_items(self) -> int:
        return self._max_items

    @property
    def item_count(self) -> int:
        return len(self._pixmaps)

    @property
    def stale_result_count(self) -> int:
        return self._stale_results

    def set_generation(self, generation: int) -> None:
        """Reject outstanding results from earlier visible queries."""
        self._generation = generation
        self._pending = {
            pending
            for pending in self._pending
            if pending[1] == generation
        }

    def get_thumbnail(
        self,
        book: LibraryRecord,
        size: QSize,
    ) -> QPixmap | None:
        """Return a cached pixmap or schedule background decoding."""
        self._assert_gui_thread()
        if not book.cover_path:
            return None
        key = self._key(book, size)
        pixmap = self._pixmaps.get(key)
        if pixmap is not None:
            self._pixmaps.move_to_end(key)
            return pixmap
        if key in self._failures:
            return None

        pending_key = (key, self._generation)
        if pending_key not in self._pending:
            self._pending.add(pending_key)
            task = _ThumbnailTask(
                key,
                book.book_id,
                self._generation,
                size,
            )
            self._tasks[pending_key] = task
            task.signals.finished.connect(self._thumbnail_finished)
            self._thread_pool.start(task)
        return None

    def state(self, book: LibraryRecord, size: QSize) -> str:
        """Return ready, loading, missing, or failed for one thumbnail."""
        if not book.cover_path:
            return "missing"
        key = self._key(book, size)
        if key in self._pixmaps:
            return "ready"
        if key in self._failures:
            return "failed"
        return "loading"

    def clear(self) -> None:
        self._assert_gui_thread()
        self._pixmaps.clear()
        self._failures.clear()

    @Slot(object)
    def _thumbnail_finished(self, result: _ThumbnailResult) -> None:
        self._tasks.pop((result.key, result.generation), None)
        self._pending.discard((result.key, result.generation))
        if result.generation != self._generation:
            self._stale_results += 1
            return

        if result.image is None or result.image.isNull():
            message = result.error or "Cover image could not be loaded."
            self._failures[result.key] = message
            self.thumbnail_failed.emit(result.book_id, message)
            return

        self._assert_gui_thread()
        pixmap = QPixmap.fromImage(result.image)
        self._pixmaps[result.key] = pixmap
        self._pixmaps.move_to_end(result.key)
        while len(self._pixmaps) > self._max_items:
            self._pixmaps.popitem(last=False)
        self.thumbnail_ready.emit(result.book_id)

    @staticmethod
    def _key(book: LibraryRecord, size: QSize) -> ThumbnailKey:
        return (
            book.cover_path,
            book.file_modified_at,
            max(1, size.width()),
            max(1, size.height()),
        )

    def _assert_gui_thread(self) -> None:
        application_thread = self.thread()
        if QThread.currentThread() is not application_thread:
            raise RuntimeError("QPixmap cache access must stay on the GUI thread.")

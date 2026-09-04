"""Background thumbnail loading and bounded cache tests."""

from pathlib import Path
from time import perf_counter, sleep

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from services.library_service import LibraryRecord
from ui.thumbnail_cache import ThumbnailCache


def _book(
    book_id: int,
    cover_path: Path | None,
) -> LibraryRecord:
    return LibraryRecord(
        title=f"Book {book_id}",
        author="Author",
        isbn="",
        publisher="",
        published_date="",
        language="",
        file_format="EPUB",
        file_size=100,
        metadata_status="embedded",
        file_path=f"C:/Books/{book_id}.epub",
        book_id=book_id,
        cover_path=str(cover_path) if cover_path else "",
        file_modified_at=f"2026-01-{book_id:02d}",
    )


def _cover(path: Path, color: str, size=(120, 180)) -> None:
    image = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path), "PNG")


def _wait_for(predicate, timeout: float = 3.0) -> None:
    application = QApplication.instance()
    deadline = perf_counter() + timeout
    while not predicate() and perf_counter() < deadline:
        application.processEvents()
        sleep(0.005)
    application.processEvents()
    assert predicate()


def test_thumbnail_cache_is_bounded_and_handles_missing_states(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    cache = ThumbnailCache(max_items=2)
    size = QSize(80, 120)
    books = []
    for index, color in enumerate(("#aa3344", "#33aa44", "#3344aa"), 1):
        path = tmp_path / f"cover-{index}.png"
        _cover(path, color)
        book = _book(index, path)
        books.append(book)
        cache.get_thumbnail(book, size)
        _wait_for(lambda expected=index: cache.item_count >= min(expected, 2))

    assert cache.item_count == 2
    assert cache.state(_book(9, None), size) == "missing"

    corrupt_path = tmp_path / "corrupt.png"
    corrupt_path.write_bytes(b"not an image")
    corrupt = _book(10, corrupt_path)
    cache.get_thumbnail(corrupt, size)
    _wait_for(lambda: cache.state(corrupt, size) == "failed")


def test_stale_thumbnail_result_is_ignored(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    path = tmp_path / "large-cover.png"
    _cover(path, "#226688", size=(1600, 2400))
    book = _book(1, path)
    cache = ThumbnailCache(max_items=2)
    cache.set_generation(1)

    cache.get_thumbnail(book, QSize(300, 450))
    cache.set_generation(2)

    _wait_for(lambda: cache.stale_result_count == 1)
    assert cache.item_count == 0

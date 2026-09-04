"""Invalid books can be moved safely out of watched-library processing."""

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox
import pytest

from core.scanner import BookFile
from database.database import DatabaseManager
from preferences import PreferencesStore
from services.library_service import (
    DELETED_FOLDER_NAME,
    MANUAL_REVIEW_FOLDER_NAME,
    LibraryRecord,
    LibraryService,
)
from services.scan_service import ScanItemStatus, ScanService
from ui.library_page import LibraryPage
from ui.metadata_studio import MetadataStudioPage
import ui.library_page as library_page_module


def _book(path: Path) -> BookFile:
    return BookFile(
        name=path.stem,
        extension=path.suffix.removeprefix(".").upper(),
        size_bytes=path.stat().st_size,
        path=path,
    )


def _record(book_id: int, title: str, root: Path) -> LibraryRecord:
    return LibraryRecord(
        title=title,
        author="Unknown",
        isbn="",
        publisher="",
        published_date="",
        language="",
        file_format="EPUB",
        file_size=10,
        metadata_status="pending",
        file_path=str(root / f"{title}.epub"),
        book_id=book_id,
        library_folder=str(root),
        metadata_issues=("Unknown author",),
        metadata_issue_count=1,
    )


def test_move_to_manual_review_preserves_collision_and_removes_catalogue_row(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Books"
    review = root / MANUAL_REVIEW_FOLDER_NAME
    review.mkdir(parents=True)
    source = root / "Not A Book.epub"
    source.write_bytes(b"selected")
    (review / source.name).write_bytes(b"existing")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(root, [_book(source)])
    book_id = int(database.get_books()[0]["id"])

    result = LibraryService(database).move_book_to_manual_review(book_id)

    destination = review / "Not A Book (2).epub"
    assert Path(result.destination_path) == destination
    assert destination.read_bytes() == b"selected"
    assert (review / source.name).read_bytes() == b"existing"
    assert not source.exists()
    assert database.get_book_by_id(book_id) is None


def test_catalogue_failure_returns_moved_file_to_original_location(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "Books"
    root.mkdir()
    source = root / "Return Me.epub"
    source.write_bytes(b"original")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(root, [_book(source)])
    book_id = int(database.get_books()[0]["id"])
    monkeypatch.setattr(
        database,
        "remove_book_from_catalogue",
        lambda _book_id: (_ for _ in ()).throw(
            RuntimeError("catalogue unavailable")
        ),
    )

    with pytest.raises(RuntimeError, match="catalogue unavailable"):
        LibraryService(database).move_book_to_manual_review(book_id)

    assert source.read_bytes() == b"original"
    assert not (
        root / MANUAL_REVIEW_FOLDER_NAME / source.name
    ).exists()
    assert database.get_book_by_id(book_id) is not None


def test_manual_review_folder_is_excluded_from_both_scan_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Books"
    review = root / MANUAL_REVIEW_FOLDER_NAME
    review.mkdir(parents=True)
    kept = root / "Kept.epub"
    ignored = review / "Ignored.epub"
    kept.write_bytes(b"kept")
    ignored.write_bytes(b"ignored")
    database = DatabaseManager(tmp_path / "library.db")
    service = ScanService(database)
    source = service.add_source(root)

    discovered = service.discover_books(
        root,
        is_cancelled=lambda: False,
    )
    analysis = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )

    assert [book.path for book in discovered] == [kept]
    assert {
        item.relative_path: item.status
        for item in analysis.items
    } == {"Kept.epub": ScanItemStatus.NEW}


def test_delete_book_preserves_collision_and_removes_catalogue_row(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Books"
    deleted = root / DELETED_FOLDER_NAME
    deleted.mkdir(parents=True)
    source = root / "No Longer Wanted.epub"
    source.write_bytes(b"selected")
    (deleted / source.name).write_bytes(b"existing")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(root, [_book(source)])
    book_id = int(database.get_books()[0]["id"])

    result = LibraryService(database).move_book_to_deleted(book_id)

    destination = deleted / "No Longer Wanted (2).epub"
    assert Path(result.destination_path) == destination
    assert destination.read_bytes() == b"selected"
    assert (deleted / source.name).read_bytes() == b"existing"
    assert not source.exists()
    assert database.get_book_by_id(book_id) is None


def test_delete_book_catalogue_failure_returns_moved_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "Books"
    root.mkdir()
    source = root / "Return Me.epub"
    source.write_bytes(b"original")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(root, [_book(source)])
    book_id = int(database.get_books()[0]["id"])
    monkeypatch.setattr(
        database,
        "remove_book_from_catalogue",
        lambda _book_id: (_ for _ in ()).throw(
            RuntimeError("catalogue unavailable")
        ),
    )

    with pytest.raises(RuntimeError, match="catalogue unavailable"):
        LibraryService(database).move_book_to_deleted(book_id)

    assert source.read_bytes() == b"original"
    assert not (root / DELETED_FOLDER_NAME / source.name).exists()
    assert database.get_book_by_id(book_id) is not None


def test_deleted_folder_is_excluded_from_both_scan_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Books"
    deleted = root / DELETED_FOLDER_NAME
    deleted.mkdir(parents=True)
    kept = root / "Kept.epub"
    ignored = deleted / "Ignored.epub"
    kept.write_bytes(b"kept")
    ignored.write_bytes(b"ignored")
    database = DatabaseManager(tmp_path / "library.db")
    service = ScanService(database)
    source = service.add_source(root)

    discovered = service.discover_books(
        root,
        is_cancelled=lambda: False,
    )
    analysis = service.analyse_source(
        source.source_id,
        is_cancelled=lambda: False,
    )

    assert [book.path for book in discovered] == [kept]
    assert {
        item.relative_path: item.status
        for item in analysis.items
    } == {"Kept.epub": ScanItemStatus.NEW}


class _MetadataMoveService:
    def __init__(self, records: tuple[LibraryRecord, ...]) -> None:
        self.records = records

    def list_books(self) -> tuple[LibraryRecord, ...]:
        return self.records

    def move_book_to_manual_review(self, book_id: int):
        self.records = tuple(
            record
            for record in self.records
            if record.book_id != book_id
        )
        return SimpleNamespace(review_folder="C:/Books/To be manually reviewed")

    def delete_book(self, book_id: int):
        self.records = tuple(
            record
            for record in self.records
            if record.book_id != book_id
        )
        return SimpleNamespace(deleted_folder="C:/Books/-=deleted=-")


def test_metadata_move_confirms_then_advances_to_next_attention_book(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "Books"
    service = _MetadataMoveService(
        (
            _record(1, "Invalid", root),
            _record(2, "Next", root),
        )
    )
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    page = MetadataStudioPage(service, preferences, lambda: None)
    changed: list[bool] = []
    page.catalogue_changed.connect(lambda: changed.append(True))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    page.manual_review_button.click()
    application.processEvents()

    assert changed == [True]
    assert page.current_book.book_id == 2
    assert "next book needing attention" in page.status_label.text().casefold()
    page.close()


def test_delete_book_confirms_then_advances_to_next_attention_book(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "Books"
    service = _MetadataMoveService(
        (
            _record(1, "Unwanted", root),
            _record(2, "Next", root),
        )
    )
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    page = MetadataStudioPage(service, preferences, lambda: None)
    changed: list[bool] = []
    page.catalogue_changed.connect(lambda: changed.append(True))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    page.delete_book_button.click()
    application.processEvents()

    assert changed == [True]
    assert page.current_book.book_id == 2
    assert "next book needing attention" in page.status_label.text().casefold()
    page.close()


def test_library_bottom_button_opens_existing_manual_review_folder(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "Books"
    review = root / MANUAL_REVIEW_FOLDER_NAME
    review.mkdir(parents=True)
    database = DatabaseManager(tmp_path / "library.db")
    ScanService(database).add_source(root)
    settings = QSettings(
        str(tmp_path / "settings.ini"),
        QSettings.Format.IniFormat,
    )
    page = LibraryPage(
        LibraryService(database),
        PreferencesStore(settings),
        background_queries=False,
    )
    opened: list[Path] = []
    monkeypatch.setattr(
        library_page_module,
        "open_folder_path",
        lambda _parent, folder: opened.append(Path(folder)) or True,
    )

    page.manual_review_folder_button.click()
    application.processEvents()

    assert opened == [review.resolve()]
    page.close()

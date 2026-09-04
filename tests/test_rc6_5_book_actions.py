"""Windows launch behavior for RC6.5 Library details actions."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QWidget

from preferences import PreferencesStore
from services.library_service import LibraryRecord
from ui.book_actions import open_book, open_containing_folder


pytestmark = pytest.mark.skipif(
    os.name != "nt",
    reason="Windows shell integration",
)


def _book(path: Path) -> LibraryRecord:
    return LibraryRecord(
        title=path.stem,
        author="Author",
        isbn="",
        publisher="",
        published_date="",
        language="",
        file_format=path.suffix.lstrip(".").upper(),
        file_size=path.stat().st_size,
        metadata_status="embedded",
        file_path=str(path),
        library_folder=str(path.parent),
    )


def _preferences(tmp_path: Path) -> PreferencesStore:
    settings = QSettings(
        str(tmp_path / "settings.ini"),
        QSettings.Format.IniFormat,
    )
    settings.clear()
    return PreferencesStore(settings)


def test_open_folder_passes_explorer_switch_and_path_separately(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    path = tmp_path / "Book With Spaces.epub"
    path.write_bytes(b"book")

    with patch("ui.book_actions.subprocess.Popen") as popen:
        opened = open_containing_folder(QWidget(), _book(path))

    assert opened
    popen.assert_called_once_with(
        ["explorer.exe", "/select,", str(path)]
    )


def test_missing_epub_association_uses_calibre_ebook_viewer(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    path = tmp_path / "Example.epub"
    path.write_bytes(b"book")
    viewer = Path(r"C:\Program Files\Calibre2\ebook-viewer.exe")

    with (
        patch(
            "ui.book_actions._windows_association_executable",
            return_value=Path(r"C:\Windows\System32\OpenWith.exe"),
        ),
        patch(
            "ui.book_actions._find_calibre_viewer",
            return_value=viewer,
        ),
        patch("ui.book_actions.subprocess.Popen") as popen,
    ):
        opened = open_book(
            QWidget(),
            _book(path),
            _preferences(tmp_path),
        )

    assert opened
    popen.assert_called_once_with([str(viewer), str(path)])


def test_real_windows_association_keeps_windows_default(
    tmp_path: Path,
) -> None:
    QApplication.instance() or QApplication([])
    path = tmp_path / "Example.epub"
    path.write_bytes(b"book")

    with (
        patch(
            "ui.book_actions._windows_association_executable",
            return_value=Path(r"C:\Apps\Thorium\Thorium.exe"),
        ),
        patch("ui.book_actions._find_calibre_viewer") as finder,
        patch("ui.book_actions.os.startfile") as startfile,
    ):
        opened = open_book(
            QWidget(),
            _book(path),
            _preferences(tmp_path),
        )

    assert opened
    finder.assert_not_called()
    startfile.assert_called_once_with(str(path))

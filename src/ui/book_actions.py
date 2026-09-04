"""Reader launching shared by Home and dedicated result pages."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from preferences import PreferencesStore, ReaderMode
from services.library_service import LibraryRecord


CALIBRE_VIEWER_EXTENSIONS = frozenset(
    {
        ".epub",
        ".mobi",
        ".azw",
        ".azw3",
        ".fb2",
    }
)


def open_book(
    parent: QWidget,
    book: LibraryRecord,
    preferences: PreferencesStore,
) -> bool:
    """Open a book according to the configured Reading settings."""
    path = Path(book.file_path)
    if not path.exists():
        QMessageBox.warning(
            parent,
            "Book not found",
            "Twano cannot find this file. Open Library Health to review "
            "its location.",
        )
        return False
    reading = preferences.load_reading_preferences()
    extension = path.suffix.lower()

    try:
        if reading.reader_mode == ReaderMode.FOLDER:
            return open_containing_folder(parent, book)

        if reading.reader_mode == ReaderMode.ASK:
            executable, _ = QFileDialog.getOpenFileName(
                parent,
                "Choose an ebook reader",
                filter="Applications (*.exe);;All files (*)",
            )
            if not executable:
                return False
            subprocess.Popen([executable, str(path)])
            return True

        custom_reader = ""
        if extension == ".epub":
            custom_reader = reading.epub_reader
        elif extension == ".pdf":
            custom_reader = reading.pdf_reader
        elif extension in {".mobi", ".azw", ".azw3"}:
            custom_reader = reading.mobi_reader
        elif extension in {".cbz", ".cbr"}:
            custom_reader = reading.comic_reader

        if (
            reading.reader_mode == ReaderMode.CUSTOM
            and custom_reader
        ):
            subprocess.Popen([custom_reader, str(path)])
        elif os.name == "nt":
            fallback_reader = _windows_fallback_reader(path)
            if fallback_reader is not None:
                subprocess.Popen([str(fallback_reader), str(path)])
            else:
                os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except OSError as error:
        QMessageBox.critical(
            parent,
            "Unable to open book",
            f"Twano could not launch a reader.\n\n{error}",
        )
        return False


def open_containing_folder(
    parent: QWidget,
    book: LibraryRecord,
) -> bool:
    """Open the available containing folder and select the book if possible."""
    path = Path(book.file_path)
    folder = (
        path.parent
        if path.parent.is_dir()
        else Path(book.library_folder)
    )
    if not folder.is_dir():
        QMessageBox.warning(
            parent,
            "Folder not found",
            "Twano cannot find this book's folder. Run a Library scan or "
            "review the stored location.",
        )
        return False

    try:
        if os.name == "nt":
            if path.is_file():
                subprocess.Popen(
                    ["explorer.exe", "/select,", str(path)]
                )
            else:
                os.startfile(str(folder))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        return True
    except OSError as error:
        QMessageBox.critical(
            parent,
            "Unable to open folder",
            f"Twano could not open this folder.\n\n{error}",
        )
        return False


def open_folder_path(parent: QWidget, folder: str | Path) -> bool:
    """Open one known folder without selecting a particular file."""
    path = Path(folder)
    if not path.is_dir():
        QMessageBox.warning(
            parent,
            "Folder not found",
            "Twano cannot find that folder. It is created after the first "
            "book is moved to manual review.",
        )
        return False
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except OSError as error:
        QMessageBox.critical(
            parent,
            "Unable to open folder",
            f"Twano could not open this folder.\n\n{error}",
        )
        return False


def _windows_fallback_reader(path: Path) -> Path | None:
    """Use Calibre's viewer only when Windows lacks a real ebook handler."""
    if path.suffix.casefold() not in CALIBRE_VIEWER_EXTENSIONS:
        return None
    associated = _windows_association_executable(path.suffix)
    if associated is not None and associated.name.casefold() not in {
        "openwith.exe",
        "calibre.exe",
        "calibre-parallel.exe",
    }:
        return None
    return _find_calibre_viewer()


def _windows_association_executable(extension: str) -> Path | None:
    """Return the executable registered for a Windows file extension."""
    if os.name != "nt":
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_ulong(len(buffer))
        result = ctypes.windll.shlwapi.AssocQueryStringW(
            0,
            2,
            extension,
            None,
            buffer,
            ctypes.byref(size),
        )
    except (AttributeError, OSError):
        return None
    if result != 0 or not buffer.value:
        return None
    return Path(buffer.value)


def _find_calibre_viewer() -> Path | None:
    """Find an installed Calibre ebook viewer without changing settings."""
    discovered = shutil.which("ebook-viewer.exe")
    candidates = [
        Path(discovered) if discovered else None,
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Calibre2"
        / "ebook-viewer.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Calibre2"
        / "ebook-viewer.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "calibre"
        / "ebook-viewer.exe",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    return None

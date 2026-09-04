"""Library scanning functions."""

from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".epub",
    ".mobi",
    ".azw",
    ".azw3",
    ".pdf",
    ".fb2",
    ".djvu",
    ".cbz",
    ".cbr",
    ".txt",
}


@dataclass(frozen=True)
class BookFile:
    """Information about a discovered eBook file."""

    name: str
    extension: str
    size_bytes: int
    path: Path

    @property
    def size_display(self) -> str:
        """Return the file size in a readable format."""
        size = float(self.size_bytes)

        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                return f"{size:.1f} {unit}"
            size /= 1024

        return f"{self.size_bytes} B"


def scan_library(folder: str | Path) -> list[BookFile]:
    """Recursively scan a folder for supported eBook files."""
    root = Path(folder)

    if not root.exists():
        raise FileNotFoundError(f"The selected folder does not exist: {root}")

    if not root.is_dir():
        raise NotADirectoryError(f"The selected path is not a folder: {root}")

    discovered_books: list[BookFile] = []

    for file_path in root.rglob("*"):
        try:
            if not file_path.is_file():
                continue

            extension = file_path.suffix.lower()

            if extension not in SUPPORTED_EXTENSIONS:
                continue

            discovered_books.append(
                BookFile(
                    name=file_path.stem,
                    extension=extension.removeprefix(".").upper(),
                    size_bytes=file_path.stat().st_size,
                    path=file_path,
                )
            )
        except (OSError, PermissionError):
            # Skip inaccessible files without stopping the entire scan.
            continue

    return sorted(
        discovered_books,
        key=lambda book: (book.name.lower(), str(book.path).lower()),
    )

"""Presentation-only formatting shared by Library widgets."""

from services.library_service import LibraryRecord


def format_file_size(size_bytes: int) -> str:
    """Convert a byte count into a readable file size."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def display_status(status: str) -> str:
    """Convert an internal metadata status into display text."""
    return status.replace("_", " ").title()


def display_series(book: LibraryRecord) -> str:
    """Return a consistent series and sequence label."""
    if not book.series:
        return ""
    group = book.series_group
    if group and book.series_group_number is not None:
        group = f"{group} #{book.series_group_number:g}"
    series = f"{group} › {book.series}" if group else book.series
    if book.series_number is None:
        return series
    return f"{series} #{book.series_number:g}"

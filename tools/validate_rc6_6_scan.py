"""Measure and verify representative RC6.6 scan/apply behavior."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from database.database import DatabaseManager  # noqa: E402
from metadata.provider_manager import ProviderManager  # noqa: E402
from services.scan_service import ScanItemStatus, ScanService  # noqa: E402


DEFAULT_BOOK_COUNT = 5_000
CHANGED_COUNT = 50
MISSING_COUNT = 25
NEW_COUNT = 75
UNSUPPORTED_COUNT = 100


def _milliseconds(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)


def _create_source_files(folder: Path, book_count: int) -> float:
    started = perf_counter()
    for index in range(book_count):
        (folder / f"Book {index:05d}.epub").write_bytes(
            f"book-{index:05d}".encode("ascii")
        )
    return _milliseconds(started)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure protected scan behavior at a chosen library size."
    )
    parser.add_argument(
        "--book-count",
        type=int,
        default=DEFAULT_BOOK_COUNT,
    )
    arguments = parser.parse_args()
    book_count = int(arguments.book_count)
    if book_count < CHANGED_COUNT + MISSING_COUNT:
        parser.error(
            f"--book-count must be at least {CHANGED_COUNT + MISSING_COUNT}"
        )
    with TemporaryDirectory(
        prefix="Twano-RC66-performance-",
        ignore_cleanup_errors=True,
    ) as temporary_folder:
        root = Path(temporary_folder)
        source_folder = root / "Large Source"
        source_folder.mkdir()
        file_creation_ms = _create_source_files(source_folder, book_count)

        database = DatabaseManager(root / "library.db")
        service = ScanService(database, ProviderManager())
        source = service.add_source(
            source_folder,
            display_name="Large Source",
        )

        started = perf_counter()
        first_preview = service.analyse_source(
            source.source_id,
            is_cancelled=lambda: False,
        )
        first_preview_ms = _milliseconds(started)
        assert first_preview.completed
        assert first_preview.count(ScanItemStatus.NEW) == book_count

        started = perf_counter()
        first_apply = service.apply_analysis(
            first_preview,
            is_cancelled=lambda: False,
        )
        first_apply_ms = _milliseconds(started)
        assert first_apply.applied_new_count == book_count
        assert database.count_books() == book_count

        started = perf_counter()
        unchanged_preview = service.analyse_source(
            source.source_id,
            is_cancelled=lambda: False,
        )
        unchanged_preview_ms = _milliseconds(started)
        assert unchanged_preview.applicable_count == 0
        assert (
            unchanged_preview.count(ScanItemStatus.UNCHANGED)
            == book_count
        )

        for index in range(CHANGED_COUNT):
            (source_folder / f"Book {index:05d}.epub").write_bytes(
                f"changed-book-{index:05d}".encode("ascii")
            )
        missing_contents: dict[Path, bytes] = {}
        for index in range(CHANGED_COUNT, CHANGED_COUNT + MISSING_COUNT):
            path = source_folder / f"Book {index:05d}.epub"
            missing_contents[path] = path.read_bytes()
            path.unlink()
        for index in range(NEW_COUNT):
            (source_folder / f"Added {index:05d}.pdf").write_bytes(
                f"added-{index:05d}".encode("ascii")
            )
        for index in range(UNSUPPORTED_COUNT):
            (source_folder / f"Unsupported {index:05d}.docx").write_bytes(
                b"unsupported"
            )

        started = perf_counter()
        changed_preview = service.analyse_source(
            source.source_id,
            is_cancelled=lambda: False,
        )
        changed_preview_ms = _milliseconds(started)
        assert changed_preview.count(ScanItemStatus.NEW) == NEW_COUNT
        assert changed_preview.count(ScanItemStatus.CHANGED) == CHANGED_COUNT
        assert changed_preview.count(ScanItemStatus.MISSING) == MISSING_COUNT
        assert changed_preview.skipped_count == UNSUPPORTED_COUNT

        vanished_path = source_folder / "Added 00000.pdf"
        vanished_path.unlink()
        reappeared_path = next(iter(missing_contents))
        reappeared_path.write_bytes(missing_contents[reappeared_path])

        started = perf_counter()
        changed_apply = service.apply_analysis(
            changed_preview,
            is_cancelled=lambda: False,
        )
        changed_apply_ms = _milliseconds(started)
        assert changed_apply.applied_new_count == NEW_COUNT - 1
        assert changed_apply.applied_changed_count == CHANGED_COUNT
        assert changed_apply.applied_missing_count == MISSING_COUNT - 1
        assert len(changed_apply.safely_skipped) == 2
        assert database.count_books() == book_count + NEW_COUNT - MISSING_COUNT
        assert database.count_books(include_missing=True) == (
            book_count + NEW_COUNT - 1
        )

        cancellation_requested = False

        def cancel_after_100(count: int) -> None:
            nonlocal cancellation_requested
            cancellation_requested = count >= 100

        started = perf_counter()
        cancelled_preview = service.analyse_source(
            source.source_id,
            is_cancelled=lambda: cancellation_requested,
            on_discovery_count=cancel_after_100,
        )
        cancelled_preview_ms = _milliseconds(started)
        assert cancelled_preview.cancelled
        assert cancelled_preview.count(ScanItemStatus.MISSING) == 0

        disconnected_folder = root / "Disconnected Large Source"
        source_folder.rename(disconnected_folder)
        started = perf_counter()
        unavailable_preview = service.analyse_source(
            source.source_id,
            is_cancelled=lambda: False,
        )
        unavailable_preview_ms = _milliseconds(started)
        assert not unavailable_preview.connected
        assert unavailable_preview.count(ScanItemStatus.MISSING) == 0
        disconnected_folder.rename(source_folder)

        history = database.list_scan_history(source.source_id)
        assert len(history) == 2
        assert all(row["status"] == "applied" for row in history)

        results = {
            "source_files": book_count,
            "unsupported_files": UNSUPPORTED_COUNT,
            "file_creation_ms": file_creation_ms,
            "first_preview_ms": first_preview_ms,
            "first_apply_ms": first_apply_ms,
            "unchanged_preview_ms": unchanged_preview_ms,
            "changed_preview_ms": changed_preview_ms,
            "changed_apply_ms": changed_apply_ms,
            "cancelled_preview_ms": cancelled_preview_ms,
            "unavailable_preview_ms": unavailable_preview_ms,
            "final_active_books": database.count_books(),
            "final_total_books": database.count_books(
                include_missing=True
            ),
            "history_rows": len(history),
            "safely_skipped_during_changed_apply": len(
                changed_apply.safely_skipped
            ),
        }
        print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

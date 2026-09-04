"""Dry-run or apply Twano's shared and nested series-folder layout.

The command is intentionally conservative: it only touches active catalogue
records that already have a series, plus a small set of explicitly verified
Three Investigators corrections. Every applied book uses Twano's normal
preview, approval, verified backup and rollback-capable metadata executor.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from database.database import DatabaseManager  # noqa: E402
from preferences import ProtectionMode  # noqa: E402
from services.protection_models import PlanConfirmation  # noqa: E402
from services.protection_service import (  # noqa: E402
    PlanValidationError,
    ProtectionService,
)
from services.series_metadata import (  # noqa: E402
    canonical_series_details,
    known_series_group,
)


THREE_INVESTIGATORS = {
    "the mystery of the stuttering parrot": ("Robert Arthur", 2),
    "the mystery of the vanishing treasure": ("Robert Arthur", 5),
    "the secret of the crooked cat": ("William Arden", 13),
}

def _normalise(value: object) -> str:
    text = " ".join(str(value or "").split()).casefold()
    return re.sub(r"^[\s\d._-]+", "", text)


def _reviewed_values(row: object) -> dict[str, object]:
    values: dict[str, object] = {}
    title = _normalise(row["title"])
    for known_title, (author, number) in THREE_INVESTIGATORS.items():
        if title == known_title or title.endswith(known_title):
            values.update(
                {
                    "author": author,
                    "series": "Alfred Hitchcock and The Three Investigators",
                    "series_number": number,
                }
            )
            break

    series = str(values.get("series") or row["series"] or "").strip()
    series, series_number = canonical_series_details(
        series,
        title=str(values.get("title") or row["title"] or ""),
        number=values.get("series_number", row["series_number"]),
    )
    if series != str(row["series"] or "").strip():
        values["series"] = series
    if series_number != str(row["series_number"] or "").strip():
        values["series_number"] = series_number
    group, group_number = known_series_group(series)
    if group and not str(row["series_group"] or "").strip():
        values["series_group"] = group
        values["series_group_number"] = group_number
    return values


def _candidate_rows(
    database: DatabaseManager,
    library_root: Path,
    canonical_series: str = "",
) -> list[object]:
    root = library_root.resolve()
    rows = []
    for row in database.get_books():
        path = Path(str(row["file_path"])).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            continue
        values = _reviewed_values(row)
        series = str(values.get("series") or row["series"] or "").strip()
        number = values.get("series_number", row["series_number"])
        if canonical_series and series.casefold() != canonical_series.casefold():
            continue
        # An unnumbered retail collection is not enough evidence to move a
        # book into the shared reading-order tree. It remains untouched until
        # a user confirms an order in Metadata & Cover Art.
        if series and number not in (None, ""):
            rows.append(row)
    return rows


def _build_previews(
    database: DatabaseManager,
    protection: ProtectionService,
    library_root: Path,
    canonical_series: str = "",
) -> list[tuple[int, dict[str, object], Path, Path]]:
    previews: list[tuple[int, dict[str, object], Path, Path]] = []
    destinations: dict[Path, int] = {}
    rows = _candidate_rows(database, library_root, canonical_series)
    missing_sources = [
        (int(row["id"]), Path(str(row["file_path"])).resolve())
        for row in rows
        if not Path(str(row["file_path"])).resolve().is_file()
    ]
    if missing_sources:
        details = "\n".join(
            f"  [{book_id}] {path}" for book_id, path in missing_sources
        )
        raise RuntimeError(
            "Migration preflight found missing catalogue source files; no "
            f"moves may start until they are reconciled:\n{details}"
        )
    for row in rows:
        book_id = int(row["id"])
        values = _reviewed_values(row)
        source = Path(str(row["file_path"])).resolve()
        try:
            plan = protection.build_metadata_update_plan(
                book_id,
                values,
                organise_file=True,
            )
        except PlanValidationError as error:
            if "already match the catalogue" in str(error):
                continue
            raise
        if not plan.file_changes:
            continue
        destination = Path(plan.file_changes[0].after_summary).resolve()
        other_id = destinations.get(destination)
        if other_id is not None:
            raise RuntimeError(
                f"Books {other_id} and {book_id} have the same destination: "
                f"{destination}"
            )
        destinations[destination] = book_id
        previews.append((book_id, values, source, destination))
    return previews


def _remove_empty_source_folders(
    sources: list[Path],
    library_root: Path,
) -> int:
    """Remove only empty, directly affected folders inside -=Series=-."""
    series_root = (library_root.resolve() / "-=Series=-").resolve()
    removed = 0
    for folder in sorted({path.parent.resolve() for path in sources}):
        if folder == series_root:
            continue
        try:
            folder.relative_to(series_root)
        except ValueError:
            continue
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--library-root",
        type=Path,
        default=Path(r"C:\EPUB\1-10"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply each validated preview using Twano's protected executor.",
    )
    parser.add_argument(
        "--series",
        default="",
        help="Limit the migration to one canonical series name.",
    )
    args = parser.parse_args()

    database = DatabaseManager()
    database.initialise_database()
    protection = ProtectionService(database)
    previews = _build_previews(
        database,
        protection,
        args.library_root,
        args.series,
    )

    print(f"Validated moves: {len(previews)}")
    for book_id, values, source, destination in previews:
        changes = ", ".join(f"{key}={value}" for key, value in values.items())
        print(f"[{book_id}] {source}")
        print(f"    -> {destination}")
        if changes:
            print(f"       metadata: {changes}")

    if not args.apply:
        print("Dry run only. No ebook or catalogue record was changed.")
        return 0

    policy = protection.build_policy(protection.default_backup_folder(), 0)
    applied = 0
    moved_sources: list[Path] = []
    for book_id, values, source, _destination in previews:
        plan = protection.build_metadata_update_plan(
            book_id,
            values,
            organise_file=True,
        )
        operation = protection.record_change_plan(plan)
        approved = protection.approve_change_plan(
            operation.operation_id,
            PlanConfirmation(
                plan_token=plan.plan_token,
                approved=True,
                confirmer="Twano series migration",
            ),
            current_basis_token=protection.current_basis_token(operation),
        )
        protection.apply_approved_operation(
            approved.operation_id,
            policy,
            ProtectionMode.STANDARD,
        )
        applied += 1
        moved_sources.append(source)
        print(f"Applied {applied}/{len(previews)}: book {book_id}")

    print(f"Protected moves applied: {applied}")
    removed = _remove_empty_source_folders(moved_sources, args.library_root)
    print(f"Empty affected series folders removed: {removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

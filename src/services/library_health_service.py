"""Deterministic, actionable library-health reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from database.database import DatabaseManager


ISSUE_PREVIEW_LIMIT = 4


@dataclass(frozen=True)
class HealthIssue:
    issue_id: str
    title: str
    count: int
    severity: str
    explanation: str
    action_label: str
    destination: str
    preview_items: tuple[str, ...] = ()


@dataclass(frozen=True)
class LibraryHealthReport:
    score: int
    total_books: int
    issues: tuple[HealthIssue, ...]


class LibraryHealthService:
    """Calculate the same explainable score for the same catalogue state."""

    def __init__(self, database: DatabaseManager | None = None) -> None:
        self.database = database or DatabaseManager()

    def get_report(self) -> LibraryHealthReport:
        rows = self.database.get_books(include_missing=True)
        sources = self.database.list_library_sources(include_archived=False)
        total = len(rows)
        metadata_rows = tuple(
            row
            for row in rows
            if (
                not str(row["title"] or "").strip()
                or not str(row["author"] or "").strip()
                or str(row["author"] or "").strip().casefold()
                in {"unknown", "unknown author"}
                or not str(row["description"] or "").strip()
                or bool(str(row["series"] or "").strip())
                != bool(str(row["series_number"] or "").strip())
                or int(row["metadata_workflow_complete"] or 0) != 1
            )
        )
        cover_rows = tuple(
            row for row in rows if not str(row["cover_path"] or "").strip()
        )
        missing_file_rows = tuple(
            row for row in rows if bool(row["is_missing"])
        )
        unavailable_source_rows = tuple(
            source
            for source in sources
            if str(source["connection_status"] or "")
            in {"unavailable", "permission_denied", "not_found", "error"}
        )
        stale_source_rows = tuple(
            source
            for source in sources
            if self._is_stale(source["last_scanned_at"])
        )
        duplicate_groups = self._probable_duplicate_groups(rows)

        missing_metadata = len(metadata_rows)
        missing_covers = len(cover_rows)
        missing_files = len(missing_file_rows)
        unavailable_sources = len(unavailable_source_rows)
        stale_sources = len(stale_source_rows)
        duplicate_group_count = len(duplicate_groups)
        rows_by_id = {int(row["id"]): row for row in rows}

        issues = (
            HealthIssue(
                "metadata",
                "Metadata needs attention",
                missing_metadata,
                "warning",
                "Books missing a title, author, description, complete series "
                "details, cover, or a completed Metadata & Covers review.",
                "Review Metadata",
                "metadata",
                self._preview_books(metadata_rows),
            ),
            HealthIssue(
                "covers",
                "Covers are missing",
                missing_covers,
                "information",
                "Books without a selected cover image.",
                "Find Covers",
                "metadata",
                self._preview_books(cover_rows),
            ),
            HealthIssue(
                "files",
                "Files cannot be found",
                missing_files,
                "urgent",
                "Catalogue records whose ebook file is currently unavailable.",
                "Review Scan",
                "scan",
                self._preview_books(missing_file_rows),
            ),
            HealthIssue(
                "sources",
                "Library locations are unavailable",
                unavailable_sources,
                "urgent",
                "Offline or inaccessible library locations are kept separate "
                "from deleted books.",
                "Check Locations",
                "scan",
                self._preview_sources(unavailable_source_rows),
            ),
            HealthIssue(
                "stale",
                "Library locations need a new scan",
                stale_sources,
                "information",
                "Locations never scanned or not scanned in the last 30 days.",
                "Open Scan",
                "scan",
                self._preview_sources(stale_source_rows),
            ),
            HealthIssue(
                "duplicates",
                "Possible duplicate groups",
                duplicate_group_count,
                "warning",
                "Books sharing an ISBN or the same normalised title and author.",
                "Review Duplicates",
                "duplicates",
                self._preview_duplicate_groups(duplicate_groups, rows_by_id),
            ),
        )
        active_issues = tuple(issue for issue in issues if issue.count)
        if total <= 0:
            score = 100
        else:
            book_deductions = (
                missing_metadata
                + missing_covers
                + missing_files * 2
                + duplicate_group_count
            )
            source_deductions = unavailable_sources * 8 + stale_sources * 2
            score = max(
                0,
                min(
                    100,
                    round(
                        100
                        - (book_deductions / max(1, total * 4)) * 100
                        - source_deductions
                    ),
                ),
            )
        return LibraryHealthReport(
            score=score,
            total_books=total,
            issues=active_issues,
        )

    @staticmethod
    def _is_stale(value: object) -> bool:
        text = str(value or "").strip()
        if not text:
            return True
        try:
            timestamp = datetime.fromisoformat(text)
        except ValueError:
            return True
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp < datetime.now(timezone.utc) - timedelta(days=30)

    @staticmethod
    def _probable_duplicate_groups(rows) -> tuple[tuple[int, ...], ...]:
        groups: set[tuple[int, ...]] = set()
        for getter in (
            lambda row: "".join(
                character
                for character in str(row["isbn"] or "").upper()
                if character.isdigit() or character == "X"
            ),
            lambda row: "\x1f".join(
                (
                    _normalise(str(row["title"] or "")),
                    _normalise(str(row["author"] or "")),
                )
            ),
        ):
            buckets: dict[str, list[int]] = {}
            for row in rows:
                value = getter(row)
                if value and value != "\x1f":
                    buckets.setdefault(value, []).append(int(row["id"]))
            groups.update(
                tuple(sorted(ids))
                for ids in buckets.values()
                if len(ids) > 1
            )
        return tuple(sorted(groups))

    @classmethod
    def _probable_duplicate_count(cls, rows) -> int:
        return len(cls._probable_duplicate_groups(rows))

    @staticmethod
    def _preview_books(rows) -> tuple[str, ...]:
        return tuple(
            _book_label(row)
            for row in rows[:ISSUE_PREVIEW_LIMIT]
        )

    @staticmethod
    def _preview_sources(sources) -> tuple[str, ...]:
        return tuple(
            _source_label(source)
            for source in sources[:ISSUE_PREVIEW_LIMIT]
        )

    @staticmethod
    def _preview_duplicate_groups(
        groups: tuple[tuple[int, ...], ...],
        rows_by_id: dict[int, object],
    ) -> tuple[str, ...]:
        previews: list[str] = []
        for group in groups[:ISSUE_PREVIEW_LIMIT]:
            first = next(
                (
                    rows_by_id[book_id]
                    for book_id in group
                    if book_id in rows_by_id
                ),
                None,
            )
            if first is not None:
                previews.append(
                    f"{_book_label(first)} ({len(group)} records)"
                )
        return tuple(previews)


def _normalise(value: str) -> str:
    return " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in value.casefold()
        ).split()
    )


def _book_label(row) -> str:
    title = str(row["title"] or row["file_name"] or "Untitled book").strip()
    author = str(row["author"] or "").strip()
    return f"{title} - {author}" if author else title


def _source_label(source) -> str:
    return str(
        source["display_name"] or source["folder_path"] or "Unnamed location"
    ).strip()

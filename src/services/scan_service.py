"""UI-independent scan discovery and persistence orchestration."""

import json
import ntpath
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from fnmatch import fnmatchcase
from pathlib import Path
import re
from uuid import uuid4

from core.scanner import BookFile, SUPPORTED_EXTENSIONS
from database.database import DatabaseManager
from metadata.models import MetadataResult
from metadata.provider_manager import (
    ProviderManager,
    create_default_provider_manager,
)
from preferences import ProtectionMode
from services.library_service import (
    DELETED_FOLDER_NAME,
    MANUAL_REVIEW_FOLDER_NAME,
)
from services.protection_service import (
    BackupCancelled,
    ProtectionService,
)


class SourceConnectionStatus(str, Enum):
    """Stable source connection states used by services and UI."""

    NOT_TESTED = "not_tested"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_FOLDER = "not_folder"
    PERMISSION_DENIED = "permission_denied"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class LibrarySource:
    """Detached watched-library source configuration."""

    source_id: int
    folder_path: str
    display_name: str
    enabled: bool
    include_subfolders: bool
    include_patterns: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    created_at: str
    last_scanned_at: str
    archived_at: str
    connection_status: SourceConnectionStatus
    connection_message: str
    connection_tested_at: str
    last_scan_status: str
    last_scan_duration_ms: int | None
    last_scan_discovered_count: int
    last_scan_new_count: int
    last_scan_changed_count: int
    last_scan_missing_count: int
    last_scan_unreadable_count: int
    last_scan_skipped_count: int
    last_scan_error: str


@dataclass(frozen=True, slots=True)
class SourceConnectionResult:
    """Result of one read-only source connection test."""

    source_id: int
    status: SourceConnectionStatus
    message: str
    tested_at: str

    @property
    def available(self) -> bool:
        return self.status == SourceConnectionStatus.AVAILABLE


@dataclass(frozen=True, slots=True)
class SourceRemovalResult:
    """Result of removing one watch and its Twano catalogue entries."""

    source_id: int
    source_name: str
    folder_path: str
    removed_book_count: int


class ScanItemStatus(str, Enum):
    """Preview classifications produced without catalogue mutation."""

    NEW = "new"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    MISSING = "missing"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class ScanAnalysisItem:
    """One detached candidate or existing book in an analysis preview."""

    status: ScanItemStatus
    file_path: str
    relative_path: str
    name: str
    file_format: str
    size_bytes: int
    modified_at: str
    fingerprint: str
    existing_book_id: int | None = None
    message: str = ""
    expected_file_size: int = 0
    expected_modified_at: str = ""
    expected_fingerprint: str = ""
    expected_is_missing: bool = False


@dataclass(frozen=True, slots=True)
class ScanAnalysisIssue:
    """One non-fatal source-analysis diagnostic."""

    path: str
    category: str
    message: str


@dataclass(frozen=True, slots=True)
class ScanAnalysisResult:
    """Immutable non-mutating result passed from worker to preview UI."""

    source: LibrarySource
    scan_token: str
    items: tuple[ScanAnalysisItem, ...]
    issues: tuple[ScanAnalysisIssue, ...]
    started_at: str
    finished_at: str
    completed: bool
    cancelled: bool
    connected: bool
    skipped_count: int

    def count(self, status: ScanItemStatus) -> int:
        return sum(1 for item in self.items if item.status == status)

    @property
    def discovered_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.status != ScanItemStatus.MISSING
        )

    @property
    def applicable_count(self) -> int:
        return sum(
            self.count(status)
            for status in (
                ScanItemStatus.NEW,
                ScanItemStatus.CHANGED,
                ScanItemStatus.MISSING,
            )
        )


class ScanApplyStatus(str, Enum):
    """Terminal outcomes for an explicitly approved preview."""

    APPLIED = "applied"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ScanApplySkip:
    """One preview candidate deliberately not changed during Apply."""

    file_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class ScanApplyResult:
    """Immutable result emitted after an approved Apply attempt."""

    source_id: int
    scan_token: str
    status: ScanApplyStatus
    applied_new_count: int
    applied_changed_count: int
    applied_missing_count: int
    refreshed_count: int
    safely_skipped: tuple[ScanApplySkip, ...]
    finished_at: str
    protection_operation_id: int | None = None

    @property
    def changed_catalogue(self) -> bool:
        return any(
            (
                self.applied_new_count,
                self.applied_changed_count,
                self.applied_missing_count,
            )
        )


@dataclass(frozen=True, slots=True)
class ScanHistoryEntry:
    """Detached scan-history row suitable for presentation."""

    history_id: int
    source_id: int
    finished_at: str
    status: str
    duration_ms: int
    new_count: int
    changed_count: int
    missing_count: int
    safely_skipped_count: int
    error_summary: str
    protection_operation_id: int | None = None


class ScanService:
    """Discover books and coordinate their persistence and metadata."""

    def __init__(
        self,
        database: DatabaseManager | None = None,
        provider_manager: ProviderManager | None = None,
    ) -> None:
        self._database = database or DatabaseManager()
        self._provider_manager = (
            provider_manager
            or create_default_provider_manager()
        )

    def get_sources(
        self,
        *,
        include_archived: bool = False,
    ) -> tuple[LibrarySource, ...]:
        """Return configured sources without exposing SQLite rows."""
        rows = self._database.list_library_sources(
            include_archived=include_archived
        )
        return tuple(self._source_from_row(row) for row in rows)

    def get_source(
        self,
        source_id: int,
        *,
        include_archived: bool = False,
    ) -> LibrarySource:
        """Return one source or raise a useful validation error."""
        row = self._database.get_library_source(
            int(source_id),
            include_archived=include_archived,
        )
        if row is None:
            raise ValueError("The watched source is no longer available.")
        return self._source_from_row(row)

    def add_source(
        self,
        folder_path: str | Path,
        *,
        display_name: str = "",
        include_subfolders: bool = True,
        include_patterns: str | tuple[str, ...] = (),
        exclude_patterns: str | tuple[str, ...] = (),
    ) -> LibrarySource:
        """Add or restore a source without requiring it to be online."""
        folder = self.normalise_source_path(folder_path)
        includes = self.normalise_patterns(include_patterns)
        excludes = self.normalise_patterns(exclude_patterns)
        name = display_name.strip() or folder.name or str(folder)

        normalised_key = os.path.normcase(str(folder))
        for existing in self.get_sources(include_archived=True):
            if os.path.normcase(existing.folder_path) != normalised_key:
                continue
            if not existing.archived_at:
                raise ValueError("This folder is already being watched.")

        row = self._database.save_library_source(
            folder,
            display_name=name,
            include_subfolders=include_subfolders,
            include_patterns=self._encode_patterns(includes),
            exclude_patterns=self._encode_patterns(excludes),
        )
        return self._source_from_row(row)

    def update_source(
        self,
        source_id: int,
        *,
        display_name: str,
        include_subfolders: bool,
        include_patterns: str | tuple[str, ...] = (),
        exclude_patterns: str | tuple[str, ...] = (),
    ) -> LibrarySource:
        """Update safe source settings while keeping its path stable."""
        name = display_name.strip()
        if not name:
            raise ValueError("Enter a name for this source.")
        includes = self.normalise_patterns(include_patterns)
        excludes = self.normalise_patterns(exclude_patterns)
        row = self._database.update_library_source(
            int(source_id),
            display_name=name,
            include_subfolders=include_subfolders,
            include_patterns=self._encode_patterns(includes),
            exclude_patterns=self._encode_patterns(excludes),
        )
        return self._source_from_row(row)

    def set_source_enabled(
        self,
        source_id: int,
        enabled: bool,
    ) -> LibrarySource:
        """Enable or disable a source without altering its books."""
        row = self._database.set_library_source_enabled(
            int(source_id),
            bool(enabled),
        )
        return self._source_from_row(row)

    def count_source_books(self, source_id: int) -> int:
        """Return the number shown in the Remove Watch confirmation."""
        self.get_source(int(source_id))
        return self._database.count_library_source_books(int(source_id))

    def remove_source(self, source_id: int) -> SourceRemovalResult:
        """Remove one watch and its catalogue rows, never ebook files."""
        source = self.get_source(int(source_id))
        removed = self._database.remove_library_source_and_books(
            source.source_id
        )
        return SourceRemovalResult(
            source_id=source.source_id,
            source_name=source.display_name,
            folder_path=source.folder_path,
            removed_book_count=removed,
        )

    def test_source(self, source_id: int) -> SourceConnectionResult:
        """Perform and persist one read-only source connection check."""
        source = self.get_source(source_id)
        result = self.check_source_connection(source)
        row = self._database.record_library_source_connection(
            source.source_id,
            status=result.status.value,
            message=result.message,
        )
        tested_source = self._source_from_row(row)
        return SourceConnectionResult(
            source_id=tested_source.source_id,
            status=tested_source.connection_status,
            message=tested_source.connection_message,
            tested_at=tested_source.connection_tested_at,
        )

    @staticmethod
    def check_source_connection(
        source: LibrarySource,
    ) -> SourceConnectionResult:
        """Check source readability without persisting any evidence."""
        if not source.enabled:
            status = SourceConnectionStatus.DISABLED
            message = "Enable this source before testing its connection."
        else:
            folder = Path(source.folder_path)
            try:
                if not folder.exists():
                    status = SourceConnectionStatus.UNAVAILABLE
                    message = (
                        "The source is unavailable. Check the drive, network "
                        "connection, or folder path."
                    )
                elif not folder.is_dir():
                    status = SourceConnectionStatus.NOT_FOLDER
                    message = "The configured source path is not a folder."
                else:
                    with os.scandir(folder) as entries:
                        next(entries, None)
                    status = SourceConnectionStatus.AVAILABLE
                    message = "Connection successful. The folder is readable."
            except PermissionError:
                status = SourceConnectionStatus.PERMISSION_DENIED
                message = (
                    "Twano does not have permission to read this source."
                )
            except OSError as error:
                status = SourceConnectionStatus.UNAVAILABLE
                message = (
                    "The source could not be reached: "
                    f"{error.strerror or str(error)}"
                )
        return SourceConnectionResult(
            source_id=source.source_id,
            status=status,
            message=message,
            tested_at=ScanService._utc_now(),
        )

    def analyse_source(
        self,
        source_id: int,
        *,
        is_cancelled: Callable[[], bool],
        on_current_location: Callable[[str], None] | None = None,
        on_discovery_count: Callable[[int], None] | None = None,
    ) -> ScanAnalysisResult:
        """Classify source changes without modifying catalogue state."""
        started_at = self._utc_now()
        scan_token = uuid4().hex
        source = self.get_source(source_id)
        connection = self.check_source_connection(source)
        issues: list[ScanAnalysisIssue] = []
        items: list[ScanAnalysisItem] = []
        skipped_count = 0

        if not connection.available:
            issues.append(
                ScanAnalysisIssue(
                    path=source.folder_path,
                    category=connection.status.value,
                    message=connection.message,
                )
            )
            return ScanAnalysisResult(
                source=source,
                scan_token=scan_token,
                items=(),
                issues=tuple(issues),
                started_at=started_at,
                finished_at=self._utc_now(),
                completed=False,
                cancelled=False,
                connected=False,
                skipped_count=0,
            )

        existing_rows = self._database.get_library_source_book_snapshot(
            source.source_id
        )
        existing_by_path: dict[str, object] = {}
        existing_path_keys: dict[int, str] = {}
        for row in existing_rows:
            path_key = os.path.normcase(
                str(Path(row["file_path"]).resolve(strict=False))
            )
            existing_by_path[path_key] = row
            existing_path_keys[int(row["id"])] = path_key
        discovered_paths: set[str] = set()
        root = Path(source.folder_path)
        root_resolved = root.resolve(strict=False)
        complete = True
        cancelled = False
        last_scanned_at_dt: datetime | None = None
        if source.last_scanned_at:
            try:
                last_scanned_at_dt = datetime.fromisoformat(
                    source.last_scanned_at
                )
                if last_scanned_at_dt.tzinfo is None:
                    last_scanned_at_dt = last_scanned_at_dt.replace(
                        tzinfo=timezone.utc
                    )
            except ValueError:
                last_scanned_at_dt = None

        def walk_error(error: OSError) -> None:
            nonlocal complete
            complete = False
            issues.append(
                ScanAnalysisIssue(
                    path=str(getattr(error, "filename", "") or root),
                    category=(
                        "permission_denied"
                        if isinstance(error, PermissionError)
                        else "inaccessible"
                    ),
                    message=str(error),
                )
            )

        for current_folder, folder_names, file_names in os.walk(
            root,
            onerror=walk_error,
        ):
            if is_cancelled():
                cancelled = True
                complete = False
                break

            current_path = Path(current_folder)
            if on_current_location is not None:
                on_current_location(str(current_path))

            folder_names.sort(key=str.casefold)
            file_names.sort(key=str.casefold)
            if not source.include_subfolders:
                folder_names.clear()
            else:
                folder_names[:] = [
                    folder_name
                    for folder_name in folder_names
                    if (
                        folder_name.casefold()
                        != MANUAL_REVIEW_FOLDER_NAME.casefold()
                        and folder_name.casefold()
                        != DELETED_FOLDER_NAME.casefold()
                        and not self._directory_is_excluded(
                            self._relative_path(
                                current_path / folder_name,
                                root_resolved,
                            ),
                            source.exclude_patterns,
                        )
                    )
                ]

            # A folder's own modified time only advances when an entry is
            # added, removed, or renamed inside it — editing a file's
            # contents in place does not touch it. Trusting that lets an
            # already-organised folder (e.g. an author or -=Series=-
            # folder Twano created) be skipped entirely when nothing has
            # changed there since the last scan, without missing a newly
            # added file, while still re-checking anything genuinely new.
            directory_unchanged = False
            if last_scanned_at_dt is not None:
                try:
                    directory_modified_at = datetime.fromtimestamp(
                        current_path.stat().st_mtime,
                        tz=timezone.utc,
                    )
                    directory_unchanged = (
                        directory_modified_at <= last_scanned_at_dt
                    )
                except (OSError, PermissionError):
                    directory_unchanged = False

            for filename in file_names:
                if is_cancelled():
                    cancelled = True
                    complete = False
                    break

                file_path = current_path / filename
                if on_current_location is not None:
                    on_current_location(str(file_path))

                extension = file_path.suffix.lower()
                if extension not in SUPPORTED_EXTENSIONS:
                    skipped_count += 1
                    continue
                resolved_file_path = file_path.resolve(strict=False)
                relative_path = self._relative_resolved_path(
                    resolved_file_path,
                    root_resolved,
                )
                if not self._file_matches_rules(
                    relative_path,
                    source.include_patterns,
                    source.exclude_patterns,
                ):
                    skipped_count += 1
                    continue

                resolved_path = str(resolved_file_path)
                path_key = os.path.normcase(resolved_path)
                discovered_paths.add(path_key)
                existing = existing_by_path.get(path_key)
                if (
                    directory_unchanged
                    and existing is not None
                    and not bool(existing["is_missing"])
                    and str(existing["file_fingerprint"] or "")
                ):
                    items.append(
                        ScanAnalysisItem(
                            status=ScanItemStatus.UNCHANGED,
                            file_path=resolved_path,
                            relative_path=relative_path,
                            name=file_path.stem,
                            file_format=extension.removeprefix(".").upper(),
                            size_bytes=int(existing["file_size"] or 0),
                            modified_at=str(
                                existing["file_modified_at"] or ""
                            ),
                            fingerprint=str(
                                existing["file_fingerprint"] or ""
                            ),
                            existing_book_id=int(existing["id"]),
                            expected_file_size=int(
                                existing["file_size"] or 0
                            ),
                            expected_modified_at=str(
                                existing["file_modified_at"] or ""
                            ),
                            expected_fingerprint=str(
                                existing["file_fingerprint"] or ""
                            ),
                            expected_is_missing=False,
                        )
                    )
                    self._notify_discovery_count(items, on_discovery_count)
                    continue
                try:
                    file_stat = file_path.stat()
                except (OSError, PermissionError) as error:
                    message = (
                        "Twano could not read this supported ebook: "
                        f"{error}"
                    )
                    items.append(
                        ScanAnalysisItem(
                            status=ScanItemStatus.UNREADABLE,
                            file_path=resolved_path,
                            relative_path=relative_path,
                            name=file_path.stem,
                            file_format=extension.removeprefix(".").upper(),
                            size_bytes=0,
                            modified_at="",
                            fingerprint="",
                            existing_book_id=(
                                int(existing["id"])
                                if existing is not None
                                else None
                            ),
                            message=message,
                            expected_file_size=(
                                int(existing["file_size"] or 0)
                                if existing is not None
                                else 0
                            ),
                            expected_modified_at=(
                                str(existing["file_modified_at"] or "")
                                if existing is not None
                                else ""
                            ),
                            expected_fingerprint=(
                                str(existing["file_fingerprint"] or "")
                                if existing is not None
                                else ""
                            ),
                            expected_is_missing=(
                                bool(existing["is_missing"])
                                if existing is not None
                                else False
                            ),
                        )
                    )
                    issues.append(
                        ScanAnalysisIssue(
                            path=resolved_path,
                            category="unreadable",
                            message=message,
                        )
                    )
                    self._notify_discovery_count(
                        items,
                        on_discovery_count,
                    )
                    continue

                modified_at = datetime.fromtimestamp(
                    file_stat.st_mtime,
                    tz=timezone.utc,
                ).isoformat()
                fingerprint = (
                    f"{file_stat.st_size}:{file_stat.st_mtime_ns}"
                )
                status = self._candidate_status(
                    existing,
                    size_bytes=file_stat.st_size,
                    modified_at=modified_at,
                    fingerprint=fingerprint,
                )
                items.append(
                    ScanAnalysisItem(
                        status=status,
                        file_path=resolved_path,
                        relative_path=relative_path,
                        name=file_path.stem,
                        file_format=extension.removeprefix(".").upper(),
                        size_bytes=file_stat.st_size,
                        modified_at=modified_at,
                        fingerprint=fingerprint,
                        existing_book_id=(
                            int(existing["id"])
                            if existing is not None
                            else None
                        ),
                        expected_file_size=(
                            int(existing["file_size"] or 0)
                            if existing is not None
                            else 0
                        ),
                        expected_modified_at=(
                            str(existing["file_modified_at"] or "")
                            if existing is not None
                            else ""
                        ),
                        expected_fingerprint=(
                            str(existing["file_fingerprint"] or "")
                            if existing is not None
                            else ""
                        ),
                        expected_is_missing=(
                            bool(existing["is_missing"])
                            if existing is not None
                            else False
                        ),
                    )
                )
                self._notify_discovery_count(
                    items,
                    on_discovery_count,
                )

            if cancelled:
                break

        if is_cancelled():
            cancelled = True
            complete = False

        if complete and not cancelled:
            for existing in existing_rows:
                existing_path = str(existing["file_path"])
                path_key = existing_path_keys[int(existing["id"])]
                if path_key in discovered_paths:
                    continue
                relative_path = self._existing_relative_in_scope(
                    existing_path,
                    root_resolved,
                    source,
                )
                if relative_path is None:
                    continue
                items.append(
                    ScanAnalysisItem(
                        status=ScanItemStatus.MISSING,
                        file_path=existing_path,
                        relative_path=relative_path,
                        name=str(
                            existing["title"]
                            or Path(existing_path).stem
                        ),
                        file_format=str(existing["file_format"] or ""),
                        size_bytes=int(existing["file_size"] or 0),
                        modified_at=str(
                            existing["file_modified_at"] or ""
                        ),
                        fingerprint=str(
                            existing["file_fingerprint"] or ""
                        ),
                        existing_book_id=int(existing["id"]),
                        message=(
                            "The file was not found during a complete source "
                            "analysis."
                        ),
                        expected_file_size=int(existing["file_size"] or 0),
                        expected_modified_at=str(
                            existing["file_modified_at"] or ""
                        ),
                        expected_fingerprint=str(
                            existing["file_fingerprint"] or ""
                        ),
                        expected_is_missing=bool(existing["is_missing"]),
                    )
                )

        order = {
            ScanItemStatus.NEW: 0,
            ScanItemStatus.CHANGED: 1,
            ScanItemStatus.MISSING: 2,
            ScanItemStatus.UNREADABLE: 3,
            ScanItemStatus.UNCHANGED: 4,
        }
        items.sort(
            key=lambda item: (
                order[item.status],
                item.relative_path.casefold(),
            )
        )
        return ScanAnalysisResult(
            source=source,
            scan_token=scan_token,
            items=tuple(items),
            issues=tuple(issues),
            started_at=started_at,
            finished_at=self._utc_now(),
            completed=complete and not cancelled,
            cancelled=cancelled,
            connected=True,
            skipped_count=skipped_count,
        )

    def apply_analysis(
        self,
        analysis: ScanAnalysisResult,
        *,
        is_cancelled: Callable[[], bool],
        on_current_item: Callable[[str], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_backup_progress: Callable[[int, str], None] | None = None,
        backup_folder: str | Path | None = None,
        retention_days: int = 0,
        protection_mode: ProtectionMode | str = ProtectionMode.STANDARD,
    ) -> ScanApplyResult:
        """Back up, revalidate, and atomically apply a confirmed preview."""
        apply_started_at = self._utc_now()
        preview_counts = self._analysis_counts(analysis)
        skips: list[ScanApplySkip] = []
        protection_operation_id: int | None = None
        protection_basis_token = ""
        backup_identity = ""

        try:
            self._validate_analysis_for_apply(analysis)
            if self._database.scan_token_handled(analysis.scan_token):
                raise ValueError(
                    "This preview has already been handled. Run Preview "
                    "Scan again before applying."
                )
            try:
                mode = ProtectionMode(protection_mode)
            except ValueError as error:
                raise ValueError(
                    "The current protection mode is invalid."
                ) from error
            if mode != ProtectionMode.STANDARD:
                raise ValueError(
                    "Apply Preview is unavailable in Read-Only mode. Change "
                    "Protection Mode to Standard in Settings first."
                )

            protection = ProtectionService(self._database)
            policy = protection.build_policy(
                (
                    backup_folder
                    if backup_folder is not None and str(backup_folder).strip()
                    else protection.default_backup_folder()
                ),
                retention_days,
            )
            operation = protection.record_confirmed_scan_apply(
                source_id=analysis.source.source_id,
                source_name=analysis.source.display_name,
                scan_token=analysis.scan_token,
                preview_counts=preview_counts,
            )
            protection_operation_id = operation.operation_id
            protection_basis_token = operation.plan.basis_token

            current_source = self.get_source(analysis.source.source_id)
            if not self._same_source_configuration(
                analysis.source,
                current_source,
            ):
                raise ValueError(
                    "Source settings changed after this preview. Run Preview "
                    "Scan again before applying."
                )

            existing_rows = self._database.get_library_source_book_snapshot(
                current_source.source_id
            )
            existing_by_id = {
                int(row["id"]): row
                for row in existing_rows
            }
            existing_by_path = {
                os.path.normcase(str(row["file_path"])): row
                for row in existing_rows
            }
            prepared: list[tuple[ScanAnalysisItem, MetadataResult | None]] = []
            candidates = tuple(
                item
                for item in analysis.items
                if item.status != ScanItemStatus.UNREADABLE
            )
            total = len(candidates)

            for index, item in enumerate(candidates, start=1):
                if is_cancelled():
                    return self._cancel_apply(
                        analysis,
                        apply_started_at,
                        preview_counts,
                        skips,
                        protection_operation_id=protection_operation_id,
                        protection_basis_token=protection_basis_token,
                        backup_identity=backup_identity,
                    )
                if on_current_item is not None:
                    on_current_item(item.file_path)

                current_row = (
                    existing_by_id.get(item.existing_book_id)
                    if item.existing_book_id is not None
                    else existing_by_path.get(
                        os.path.normcase(item.file_path)
                    )
                )
                row_issue = self._row_recheck_issue(item, current_row)
                file_issue = self._file_recheck_issue(item)
                issue = row_issue or file_issue
                if issue:
                    skips.append(
                        ScanApplySkip(
                            file_path=item.file_path,
                            reason=issue,
                        )
                    )
                else:
                    metadata = None
                    if item.status in (
                        ScanItemStatus.NEW,
                        ScanItemStatus.CHANGED,
                    ):
                        try:
                            metadata = self._provider_manager.extract(
                                item.file_path
                            )
                        except Exception:
                            metadata = MetadataResult(
                                extraction_status="unavailable"
                            )
                    prepared.append((item, metadata))
                if on_progress is not None:
                    on_progress(index, total)

            if is_cancelled():
                return self._cancel_apply(
                    analysis,
                    apply_started_at,
                    preview_counts,
                    skips,
                    protection_operation_id=protection_operation_id,
                    protection_basis_token=protection_basis_token,
                    backup_identity=backup_identity,
                )

            final_prepared: list[
                tuple[ScanAnalysisItem, MetadataResult | None]
            ] = []
            for item, metadata in prepared:
                issue = self._file_recheck_issue(item)
                if issue:
                    skips.append(
                        ScanApplySkip(
                            file_path=item.file_path,
                            reason=(
                                "Final safety check: "
                                f"{issue}"
                            ),
                        )
                    )
                    continue
                final_prepared.append((item, metadata))

            if is_cancelled():
                return self._cancel_apply(
                    analysis,
                    apply_started_at,
                    preview_counts,
                    skips,
                    protection_operation_id=protection_operation_id,
                    protection_basis_token=protection_basis_token,
                    backup_identity=backup_identity,
                )

            if on_status is not None:
                on_status(
                    "Safety checks complete. Creating an automatic catalogue "
                    "backup..."
                )

            def backup_progress(percent: int, message: str) -> None:
                if on_status is not None:
                    on_status(message)
                if on_backup_progress is not None:
                    on_backup_progress(percent, message)

            try:
                backup = protection.create_verified_backup(
                    policy,
                    is_cancelled=is_cancelled,
                    on_progress=(
                        backup_progress
                        if (
                            on_status is not None
                            or on_backup_progress is not None
                        )
                        else None
                    ),
                )
            except BackupCancelled:
                return self._cancel_apply(
                    analysis,
                    apply_started_at,
                    preview_counts,
                    skips,
                    protection_operation_id=protection_operation_id,
                    protection_basis_token=protection_basis_token,
                    backup_identity=backup_identity,
                )
            backup_identity = str(backup.path)
            if is_cancelled():
                return self._cancel_apply(
                    analysis,
                    apply_started_at,
                    preview_counts,
                    skips,
                    protection_operation_id=protection_operation_id,
                    protection_basis_token=protection_basis_token,
                    backup_identity=backup_identity,
                )
            if on_status is not None:
                on_status(
                    "Safety backup verified. Applying catalogue changes..."
                )

            finished_at = self._utc_now()
            duration_ms = self._duration_ms(
                analysis.started_at,
                finished_at,
            )
            changes = [
                self._database_change(item, metadata)
                for item, metadata in final_prepared
            ]
            summary = self._skip_summary(skips)
            applied = self._database.apply_scan_preview(
                source_id=current_source.source_id,
                scan_token=analysis.scan_token,
                started_at=analysis.started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                preview_counts=preview_counts,
                changes=changes,
                safely_skipped_count=len(skips),
                error_summary=summary,
                protection_operation_id=protection_operation_id,
                protection_basis_token=protection_basis_token,
                backup_identity=backup_identity,
            )
            database_skips = applied["safely_skipped"] - len(skips)
            if database_skips > 0:
                skips.extend(
                    ScanApplySkip(
                        file_path="Catalogue",
                        reason=(
                            "The catalogue changed after preview, so a stale "
                            "candidate was safely skipped."
                        ),
                    )
                    for _ in range(database_skips)
                )
            return ScanApplyResult(
                source_id=current_source.source_id,
                scan_token=analysis.scan_token,
                status=ScanApplyStatus.APPLIED,
                applied_new_count=applied["new"],
                applied_changed_count=applied["changed"],
                applied_missing_count=applied["missing"],
                refreshed_count=applied["refreshed"],
                safely_skipped=tuple(skips),
                finished_at=finished_at,
                protection_operation_id=protection_operation_id,
            )
        except Exception as error:
            self._record_failed_apply(
                analysis,
                apply_started_at,
                preview_counts,
                str(error),
                len(skips),
                protection_operation_id=protection_operation_id,
                protection_basis_token=protection_basis_token,
                backup_identity=backup_identity,
            )
            raise

    def get_scan_history(
        self,
        source_id: int,
        *,
        limit: int = 20,
    ) -> tuple[ScanHistoryEntry, ...]:
        """Return recent approved Apply outcomes for one source."""
        return tuple(
            ScanHistoryEntry(
                history_id=int(row["id"]),
                source_id=int(row["library_id"]),
                finished_at=str(row["finished_at"]),
                status=str(row["status"]),
                duration_ms=int(row["duration_ms"] or 0),
                new_count=int(row["applied_new_count"] or 0),
                changed_count=int(row["applied_changed_count"] or 0),
                missing_count=int(row["applied_missing_count"] or 0),
                safely_skipped_count=int(
                    row["safely_skipped_count"] or 0
                ),
                error_summary=str(row["error_summary"] or ""),
                protection_operation_id=(
                    int(row["protection_operation_id"])
                    if row["protection_operation_id"] is not None
                    else None
                ),
            )
            for row in self._database.list_scan_history(
                int(source_id),
                limit=limit,
            )
        )

    @staticmethod
    def _validate_analysis_for_apply(
        analysis: ScanAnalysisResult,
    ) -> None:
        if analysis.cancelled or not analysis.completed or not analysis.connected:
            raise ValueError(
                "Only a complete, connected preview can be applied."
            )
        if analysis.applicable_count <= 0:
            raise ValueError("This preview contains no catalogue changes.")

    @staticmethod
    def _same_source_configuration(
        previewed: LibrarySource,
        current: LibrarySource,
    ) -> bool:
        return (
            previewed.source_id == current.source_id
            and os.path.normcase(previewed.folder_path)
            == os.path.normcase(current.folder_path)
            and current.enabled
            and not current.archived_at
            and previewed.include_subfolders == current.include_subfolders
            and previewed.include_patterns == current.include_patterns
            and previewed.exclude_patterns == current.exclude_patterns
        )

    @staticmethod
    def _row_recheck_issue(item: ScanAnalysisItem, row) -> str:
        if item.status == ScanItemStatus.NEW:
            return (
                "A catalogue row now exists for this path."
                if row is not None
                else ""
            )
        if row is None or int(row["id"]) != item.existing_book_id:
            return "The catalogue row changed after preview."
        if (
            int(row["file_size"] or 0) != item.expected_file_size
            or str(row["file_modified_at"] or "")
            != item.expected_modified_at
            or str(row["file_fingerprint"] or "")
            != item.expected_fingerprint
            or bool(row["is_missing"]) != item.expected_is_missing
        ):
            return "The catalogue facts changed after preview."
        return ""

    @staticmethod
    def _file_recheck_issue(item: ScanAnalysisItem) -> str:
        path = Path(item.file_path)
        if item.status == ScanItemStatus.MISSING:
            try:
                path.stat()
            except FileNotFoundError:
                return ""
            except OSError as error:
                return (
                    "Twano could not confirm that the file is missing: "
                    f"{error}"
                )
            return "The file reappeared after preview."
        try:
            file_stat = path.stat()
        except OSError as error:
            return f"The file is no longer readable: {error}"
        if not path.is_file():
            return "The candidate is no longer a file."
        fingerprint = f"{file_stat.st_size}:{file_stat.st_mtime_ns}"
        if (
            file_stat.st_size != item.size_bytes
            or fingerprint != item.fingerprint
        ):
            return "The file changed after preview."
        return ""

    @staticmethod
    def _database_change(
        item: ScanAnalysisItem,
        metadata: MetadataResult | None,
    ) -> dict[str, object]:
        metadata = metadata or MetadataResult(
            extraction_status="unavailable"
        )
        return {
            "status": item.status.value,
            "file_path": item.file_path,
            "file_name": Path(item.file_path).name,
            "title": (
                metadata.title or item.name
                if item.status == ScanItemStatus.NEW
                else metadata.title
            ),
            "author": metadata.author,
            "isbn": metadata.isbn,
            "publisher": metadata.publisher,
            "language": metadata.language,
            "published_date": metadata.published_date,
            "file_format": item.file_format,
            "file_size": item.size_bytes,
            "file_modified_at": item.modified_at,
            "file_fingerprint": item.fingerprint,
            "metadata_status": metadata.extraction_status,
            "existing_book_id": item.existing_book_id,
            "expected_file_size": item.expected_file_size,
            "expected_modified_at": item.expected_modified_at,
            "expected_fingerprint": item.expected_fingerprint,
            "expected_is_missing": item.expected_is_missing,
        }

    def _cancel_apply(
        self,
        analysis: ScanAnalysisResult,
        apply_started_at: str,
        preview_counts: dict[str, int],
        skips: list[ScanApplySkip],
        *,
        protection_operation_id: int | None,
        protection_basis_token: str,
        backup_identity: str,
    ) -> ScanApplyResult:
        finished_at = self._utc_now()
        self._database.record_scan_attempt(
            source_id=analysis.source.source_id,
            scan_token=analysis.scan_token,
            started_at=apply_started_at,
            finished_at=finished_at,
            status="cancelled",
            duration_ms=self._duration_ms(apply_started_at, finished_at),
            preview_counts=preview_counts,
            safely_skipped_count=len(skips),
            error_summary="Apply was cancelled before catalogue changes.",
            protection_operation_id=protection_operation_id,
            protection_basis_token=protection_basis_token,
            backup_identity=backup_identity,
        )
        return ScanApplyResult(
            source_id=analysis.source.source_id,
            scan_token=analysis.scan_token,
            status=ScanApplyStatus.CANCELLED,
            applied_new_count=0,
            applied_changed_count=0,
            applied_missing_count=0,
            refreshed_count=0,
            safely_skipped=tuple(skips),
            finished_at=finished_at,
            protection_operation_id=protection_operation_id,
        )

    def _record_failed_apply(
        self,
        analysis: ScanAnalysisResult,
        apply_started_at: str,
        preview_counts: dict[str, int],
        message: str,
        safely_skipped_count: int,
        *,
        protection_operation_id: int | None,
        protection_basis_token: str,
        backup_identity: str,
    ) -> None:
        finished_at = self._utc_now()
        try:
            self._database.record_scan_attempt(
                source_id=analysis.source.source_id,
                scan_token=analysis.scan_token,
                started_at=apply_started_at,
                finished_at=finished_at,
                status="failed",
                duration_ms=self._duration_ms(
                    apply_started_at,
                    finished_at,
                ),
                preview_counts=preview_counts,
                safely_skipped_count=safely_skipped_count,
                error_summary=message[:1000],
                protection_operation_id=protection_operation_id,
                protection_basis_token=protection_basis_token,
                backup_identity=backup_identity,
            )
        except Exception:
            # Preserve the original Apply failure if history cannot be saved.
            pass

    @staticmethod
    def _analysis_counts(
        analysis: ScanAnalysisResult,
    ) -> dict[str, int]:
        return {
            "discovered": analysis.discovered_count,
            "new": analysis.count(ScanItemStatus.NEW),
            "changed": analysis.count(ScanItemStatus.CHANGED),
            "missing": analysis.count(ScanItemStatus.MISSING),
            "unchanged": analysis.count(ScanItemStatus.UNCHANGED),
            "unreadable": analysis.count(ScanItemStatus.UNREADABLE),
            "skipped": analysis.skipped_count,
        }

    @staticmethod
    def _duration_ms(started_at: str, finished_at: str) -> int:
        try:
            started = datetime.fromisoformat(started_at)
            finished = datetime.fromisoformat(finished_at)
        except ValueError:
            return 0
        return max(0, int((finished - started).total_seconds() * 1000))

    @staticmethod
    def _skip_summary(skips: list[ScanApplySkip]) -> str:
        if not skips:
            return ""
        reasons = "; ".join(skip.reason for skip in skips[:5])
        if len(skips) > 5:
            reasons += f"; and {len(skips) - 5} more"
        return reasons[:1000]

    @staticmethod
    def _candidate_status(
        existing,
        *,
        size_bytes: int,
        modified_at: str,
        fingerprint: str,
    ) -> ScanItemStatus:
        if existing is None:
            return ScanItemStatus.NEW
        if bool(existing["is_missing"]):
            return ScanItemStatus.CHANGED
        existing_fingerprint = str(existing["file_fingerprint"] or "")
        if existing_fingerprint:
            return (
                ScanItemStatus.UNCHANGED
                if existing_fingerprint == fingerprint
                else ScanItemStatus.CHANGED
            )
        if (
            int(existing["file_size"] or 0) == size_bytes
            and str(existing["file_modified_at"] or "") == modified_at
        ):
            return ScanItemStatus.UNCHANGED
        return ScanItemStatus.CHANGED

    @staticmethod
    def _notify_discovery_count(
        items: list[ScanAnalysisItem],
        callback: Callable[[int], None] | None,
    ) -> None:
        if callback is not None:
            callback(len(items))

    @staticmethod
    def _relative_path(path: Path, root: Path) -> str:
        try:
            return path.resolve(strict=False).relative_to(root).as_posix()
        except ValueError:
            return path.name

    @staticmethod
    def _relative_resolved_path(path: Path, root: Path) -> str:
        """Return a relative path when both inputs are already resolved."""
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.name

    @classmethod
    def _file_matches_rules(
        cls,
        relative_path: str,
        include_patterns: tuple[str, ...],
        exclude_patterns: tuple[str, ...],
    ) -> bool:
        if any(
            cls._glob_matches(relative_path, pattern)
            for pattern in exclude_patterns
        ):
            return False
        if not include_patterns:
            return True
        return any(
            cls._glob_matches(relative_path, pattern)
            for pattern in include_patterns
        )

    @classmethod
    def _directory_is_excluded(
        cls,
        relative_path: str,
        exclude_patterns: tuple[str, ...],
    ) -> bool:
        probe = relative_path.rstrip("/") + "/_"
        return any(
            cls._glob_matches(relative_path, pattern)
            or cls._glob_matches(probe, pattern)
            for pattern in exclude_patterns
        )

    @staticmethod
    def _glob_matches(relative_path: str, pattern: str) -> bool:
        path_value = relative_path.casefold()
        pattern_value = pattern.casefold()
        candidates = {path_value, Path(path_value).name}
        patterns = {pattern_value}
        if pattern_value.startswith("**/"):
            patterns.add(pattern_value[3:])
        return any(
            fnmatchcase(candidate, candidate_pattern)
            for candidate in candidates
            for candidate_pattern in patterns
        )

    @classmethod
    def _existing_relative_in_scope(
        cls,
        file_path: str,
        root: Path,
        source: LibrarySource,
    ) -> str | None:
        try:
            relative = (
                Path(file_path)
                .resolve(strict=False)
                .relative_to(root)
            )
        except ValueError:
            return None
        if not source.include_subfolders and len(relative.parts) > 1:
            return None
        relative_path = relative.as_posix()
        if Path(file_path).suffix.lower() not in SUPPORTED_EXTENSIONS:
            return None
        if not cls._file_matches_rules(
            relative_path,
            source.include_patterns,
            source.exclude_patterns,
        ):
            return None
        return relative_path

    @staticmethod
    def normalise_source_path(folder_path: str | Path) -> Path:
        """Return one absolute local, mapped-drive, or UNC-shaped path."""
        raw_path = str(folder_path).strip().strip('"')
        if not raw_path:
            raise ValueError("Enter a folder path.")
        expanded = os.path.expandvars(os.path.expanduser(raw_path))
        if not ntpath.isabs(expanded):
            raise ValueError(
                "Use an absolute folder path, mapped drive, or UNC path."
            )
        return Path(expanded).resolve(strict=False)

    @staticmethod
    def normalise_patterns(
        patterns: str | tuple[str, ...],
    ) -> tuple[str, ...]:
        """Validate and de-duplicate source-relative glob patterns."""
        raw_patterns = (
            re.split(r"[;\r\n]+", patterns)
            if isinstance(patterns, str)
            else list(patterns)
        )
        result: list[str] = []
        seen: set[str] = set()
        for raw_pattern in raw_patterns:
            pattern = str(raw_pattern).strip().replace("\\", "/")
            if not pattern:
                continue
            while pattern.startswith("./"):
                pattern = pattern[2:]
            parts = tuple(part for part in pattern.split("/") if part)
            if ntpath.isabs(pattern) or ".." in parts:
                raise ValueError(
                    "Source rules must be relative patterns without '..'."
                )
            key = pattern.casefold()
            if key not in seen:
                seen.add(key)
                result.append(pattern)
        return tuple(result)

    @staticmethod
    def _encode_patterns(patterns: tuple[str, ...]) -> str:
        return json.dumps(patterns, ensure_ascii=False)

    @staticmethod
    def _decode_patterns(value: object) -> tuple[str, ...]:
        text = str(value or "")
        try:
            decoded = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return ScanService.normalise_patterns(text)
        if not isinstance(decoded, list):
            return ()
        return tuple(str(pattern) for pattern in decoded)

    @staticmethod
    def _source_from_row(row) -> LibrarySource:
        status_text = str(row["connection_status"] or "not_tested")
        try:
            status = SourceConnectionStatus(status_text)
        except ValueError:
            status = SourceConnectionStatus.NOT_TESTED
        folder_path = str(row["folder_path"])
        display_name = str(row["display_name"] or "").strip()
        if not display_name:
            folder = Path(folder_path)
            display_name = folder.name or folder_path
        return LibrarySource(
            source_id=int(row["id"]),
            folder_path=folder_path,
            display_name=display_name,
            enabled=bool(row["is_enabled"]),
            include_subfolders=bool(row["include_subfolders"]),
            include_patterns=ScanService._decode_patterns(
                row["include_patterns"]
            ),
            exclude_patterns=ScanService._decode_patterns(
                row["exclude_patterns"]
            ),
            created_at=str(row["created_at"] or ""),
            last_scanned_at=str(row["last_scanned_at"] or ""),
            archived_at=str(row["archived_at"] or ""),
            connection_status=status,
            connection_message=str(row["connection_message"] or ""),
            connection_tested_at=str(row["connection_tested_at"] or ""),
            last_scan_status=str(row["last_scan_status"] or ""),
            last_scan_duration_ms=(
                int(row["last_scan_duration_ms"])
                if row["last_scan_duration_ms"] is not None
                else None
            ),
            last_scan_discovered_count=int(
                row["last_scan_discovered_count"] or 0
            ),
            last_scan_new_count=int(row["last_scan_new_count"] or 0),
            last_scan_changed_count=int(
                row["last_scan_changed_count"] or 0
            ),
            last_scan_missing_count=int(
                row["last_scan_missing_count"] or 0
            ),
            last_scan_unreadable_count=int(
                row["last_scan_unreadable_count"] or 0
            ),
            last_scan_skipped_count=int(
                row["last_scan_skipped_count"] or 0
            ),
            last_scan_error=str(row["last_scan_error"] or ""),
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def validate_library_folder(library_folder: str | Path) -> Path:
        """Validate and return a library folder path."""
        folder = Path(library_folder)

        if not folder.exists():
            raise FileNotFoundError(
                f"The selected folder does not exist:\n{folder}"
            )

        if not folder.is_dir():
            raise NotADirectoryError(
                f"The selected path is not a folder:\n{folder}"
            )

        return folder

    def discover_books(
        self,
        library_folder: str | Path,
        *,
        is_cancelled: Callable[[], bool],
        on_discovery_count: Callable[[int], None] | None = None,
    ) -> list[BookFile]:
        """Recursively find supported eBooks while honoring cancellation."""
        folder = Path(library_folder)
        discovered: list[BookFile] = []

        def handle_walk_error(_error: OSError) -> None:
            return

        for current_folder, folder_names, filenames in os.walk(
            folder,
            onerror=handle_walk_error,
        ):
            if is_cancelled():
                break

            current_path = Path(current_folder)
            folder_names[:] = [
                name
                for name in folder_names
                if name.casefold() != MANUAL_REVIEW_FOLDER_NAME.casefold()
                and name.casefold() != DELETED_FOLDER_NAME.casefold()
            ]

            for filename in filenames:
                if is_cancelled():
                    break

                file_path = current_path / filename
                extension = file_path.suffix.lower()

                if extension not in SUPPORTED_EXTENSIONS:
                    continue

                try:
                    size_bytes = file_path.stat().st_size
                except (OSError, PermissionError):
                    continue

                discovered.append(
                    BookFile(
                        name=file_path.stem,
                        extension=extension.removeprefix(".").upper(),
                        size_bytes=size_bytes,
                        path=file_path,
                    )
                )

                if (
                    on_discovery_count is not None
                    and len(discovered) % 100 == 0
                ):
                    on_discovery_count(len(discovered))

        return sorted(
            discovered,
            key=lambda book: (
                book.name.lower(),
                str(book.path).lower(),
            ),
        )

    def save_discovered_books(
        self,
        library_folder: str | Path,
        books: list[BookFile],
    ) -> int:
        """Persist a completed discovery pass."""
        return self._database.save_scan_results(library_folder, books)

    def process_metadata(self, book: BookFile) -> MetadataResult:
        """Resolve and persist the best provider metadata for one book."""
        metadata = self._provider_manager.extract(book.path)

        if metadata is None:
            metadata = MetadataResult(extraction_status="unavailable")

        self._database.update_book_metadata(
            book.path,
            title=metadata.title,
            author=metadata.author,
            isbn=metadata.isbn,
            publisher=metadata.publisher,
            language=metadata.language,
            published_date=metadata.published_date,
            metadata_status=metadata.extraction_status,
        )
        return metadata

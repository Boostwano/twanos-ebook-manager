"""Verified database backup services for RC6.7 protection workflows."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from config import APP_VERSION
from database.database import (
    DEFAULT_DATABASE_PATH,
    DatabaseBackupCancelled,
    DatabaseManager,
    InvalidDatabaseBackup,
)
from services.protection_models import (
    ChangePlan,
    ChangePlanItem,
    ChangeTarget,
    ConfirmationRequirement,
    OperationItemRecord,
    OperationRecord,
    OperationRisk,
    OperationStatus,
    PlanConfirmation,
    PlanValidationError,
    Reversibility,
)
from services.series_metadata import canonical_series_details, match_existing_series
from preferences import PreferencesStore, ProtectionMode


BACKUP_FILE_PREFIX = "Twano-library-"
BACKUP_FILE_SUFFIX = ".sqlite3"
MANIFEST_SUFFIX = ".manifest.json"
MANIFEST_SCHEMA_VERSION = 1


class BackupCancelled(RuntimeError):
    """Raised when backup creation or verification is cancelled."""


class ReportExportCancelled(RuntimeError):
    """Raised when an operation-report export is cancelled."""


class ProtectedExecutionError(RuntimeError):
    """Raised when a protected database operation cannot finish safely."""


class BackupStatus(StrEnum):
    """Truthful state shown for one discovered backup."""

    VERIFIED = "verified"
    MODIFIED = "modified"
    INVALID = "invalid"
    UNVERIFIED = "unverified"
    MISSING = "missing"


@dataclass(frozen=True)
class BackupPolicy:
    """Validated user-controlled backup location and retention age."""

    folder: Path
    retention_days: int = 0


@dataclass(frozen=True)
class BackupRecord:
    """Presentation-neutral description of one database backup."""

    path: Path
    manifest_path: Path
    created_at: str
    size_bytes: int
    status: BackupStatus
    sha256: str = ""
    message: str = ""


@dataclass(frozen=True)
class RetentionPreview:
    """Exact dry-run outcome for one saved retention policy."""

    operation: OperationRecord | None
    cutoff_at: str
    candidate_count: int
    candidate_bytes: int
    retained_count: int
    excluded_count: int


ProgressCallback = Callable[[int, str], None]
CancellationCheck = Callable[[], bool]


class ProtectionService:
    """Create, inspect, and verify Twano-owned database backups."""

    def __init__(
        self,
        database: DatabaseManager | None = None,
        *,
        database_path: str | Path = DEFAULT_DATABASE_PATH,
        preferences: PreferencesStore | None = None,
    ) -> None:
        self._database = database
        self._database_path = (
            database.database_path
            if database is not None
            else Path(database_path)
        )
        self._preferences = preferences or PreferencesStore()

    @property
    def database(self) -> DatabaseManager:
        """Create the database manager only when database work is needed."""
        if self._database is None:
            self._database = DatabaseManager(self._database_path)
        return self._database

    @property
    def live_database_path(self) -> Path:
        return self._database_path.resolve()

    def default_backup_folder(self) -> Path:
        """Return the database-adjacent default without creating it."""
        return self.live_database_path.parent / "backups"

    @staticmethod
    def build_policy(
        folder: str | Path,
        retention_days: int,
    ) -> BackupPolicy:
        """Validate policy values before filesystem work begins."""
        folder_path = Path(folder).expanduser()
        if not folder_path.is_absolute():
            raise ValueError("Backup folder must be an absolute path.")
        try:
            days = int(retention_days)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Backup retention must be a whole number of days."
            ) from error
        if not 0 <= days <= 36500:
            raise ValueError(
                "Backup retention must be between 0 and 36500 days."
            )
        return BackupPolicy(folder=folder_path, retention_days=days)

    @staticmethod
    def build_safety_check_plan() -> ChangePlan:
        """Build the non-catalogue test plan exposed by Milestone 2."""
        return ChangePlan(
            operation_type="protection_readiness_check",
            title="Record a protection readiness check",
            summary=(
                "Confirm that change-plan preview, approval, cancellation, "
                "persistent history, and reporting are ready. This plan "
                "does not change books, metadata, or ebook files."
            ),
            component="protection_centre",
            initiator="user",
            affected_book_count=0,
            risk=OperationRisk.LOW,
            reversibility=Reversibility.NOT_APPLICABLE,
            confirmation_requirement=ConfirmationRequirement.NONE,
            basis_token="protection-audit-contract-v1",
            database_changes=(
                ChangePlanItem(
                    target=ChangeTarget.DATABASE,
                    action="record_audit_evidence",
                    description=(
                        "Store this preview and its chosen outcome only in "
                        "the protection audit history."
                    ),
                    after_summary=(
                        "One persistent protection-history entry."
                    ),
                    reversible=False,
                ),
            ),
            warnings=(
                "No catalogue, metadata, collection, or ebook-file change "
                "will be executed.",
                "This readiness-check plan has no executor; approval records "
                "intent only.",
            ),
        )

    def build_reversible_test_plan(
        self,
        collection_name: str = "",
    ) -> ChangePlan:
        """Build one narrow reversible catalogue plan for Milestone 3."""
        cleaned_name = " ".join(str(collection_name).split())
        if not cleaned_name:
            cleaned_name = (
                "Twano Protected Change "
                f"{datetime.now().strftime('%d %b %H%M%S')}-"
                f"{uuid4().hex[:6]}"
            )
        basis_token = self._collection_create_basis(cleaned_name)
        if self.database.get_collection_by_name(cleaned_name) is not None:
            raise PlanValidationError(
                "That collection already exists. Choose a different name."
            )
        return ChangePlan(
            operation_type="collection_create",
            title="Create a reversible test collection",
            summary=(
                f"Create the empty collection “{cleaned_name}” through the "
                "protected executor. No book, metadata, or ebook file will "
                "be changed."
            ),
            component="protection_centre",
            initiator="user",
            affected_book_count=0,
            risk=OperationRisk.LOW,
            reversibility=Reversibility.FULL,
            confirmation_requirement=ConfirmationRequirement.EXPLICIT,
            basis_token=basis_token,
            database_changes=(
                ChangePlanItem(
                    target=ChangeTarget.DATABASE,
                    action="create_collection",
                    description=(
                        f"Create one empty catalogue collection named "
                        f"“{cleaned_name}”."
                    ),
                    before_summary="Collection does not exist.",
                    after_summary=cleaned_name,
                    reversible=True,
                ),
            ),
            warnings=(
                "A verified catalogue backup is required before Apply.",
                "This test changes only the collections table and can be "
                "undone while the created collection remains empty.",
            ),
        )

    def build_metadata_update_plan(
        self,
        book_id: int,
        values: Mapping[str, object],
        *,
        organise_file: bool = False,
    ) -> ChangePlan:
        """Build one reviewed, backup-protected metadata update plan."""
        row = self.database.get_book_by_id(int(book_id))
        if row is None:
            raise PlanValidationError(f"Unknown book ID: {book_id}")
        allowed = (
            "title",
            "author",
            "isbn",
            "publisher",
            "language",
            "published_date",
            "series",
            "series_number",
            "series_group",
            "series_group_number",
            "description",
            "cover_path",
            "provider_rating",
            "rating_count",
            "rating_source",
        )
        unknown = set(values) - set(allowed)
        if unknown:
            raise PlanValidationError(
                "Unsupported metadata fields: " + ", ".join(sorted(unknown))
            )
        cleaned: dict[str, object] = {}
        for field in allowed:
            if field not in values:
                continue
            value = values[field]
            if field in {"series_number", "series_group_number"}:
                if value in (None, ""):
                    cleaned[field] = None
                else:
                    try:
                        cleaned[field] = float(value)
                    except (TypeError, ValueError) as error:
                        label = (
                            "Series group number"
                            if field == "series_group_number"
                            else "Series number"
                        )
                        raise PlanValidationError(
                            f"{label} must be a number."
                        ) from error
            elif field == "provider_rating":
                try:
                    rating = float(value or 0)
                except (TypeError, ValueError) as error:
                    raise PlanValidationError(
                        "Website rating must be a number between 0 and 5."
                    ) from error
                if rating < 0 or rating > 5:
                    raise PlanValidationError(
                        "Website rating must be between 0 and 5."
                    )
                cleaned[field] = round(rating, 2)
            elif field == "rating_count":
                try:
                    count = int(value or 0)
                except (TypeError, ValueError) as error:
                    raise PlanValidationError(
                        "Website rating count must be a whole number."
                    ) from error
                if count < 0:
                    raise PlanValidationError(
                        "Website rating count cannot be negative."
                    )
                cleaned[field] = count
            else:
                cleaned[field] = " ".join(str(value or "").split())
        self._canonicalise_series_values(row, cleaned)
        changed = {
            field: value
            for field, value in cleaned.items()
            if row[field] != value
            and not (row[field] is None and value in ("", None))
        }
        file_changes: tuple[ChangePlanItem, ...] = ()
        destination: Path | None = None
        if organise_file:
            destination = self._metadata_destination(row, cleaned)
            source = Path(str(row["file_path"])).resolve()
            if destination != source:
                destination = self._resolve_catalogued_edition_collision(
                    row,
                    cleaned,
                    destination,
                )
                if destination != source:
                    if destination.exists():
                        raise PlanValidationError(
                            "The proposed organised filename already exists: "
                            f"{destination}"
                        )
                    file_changes = (
                        ChangePlanItem(
                            target=ChangeTarget.FILE,
                            action="move_book_file",
                            description=(
                                "Move and rename the ebook inside its watched "
                                "library."
                            ),
                            book_id=int(book_id),
                            book_title=str(
                                cleaned.get("title")
                                or row["title"]
                                or row["file_name"]
                            ),
                            before_summary=str(source),
                            after_summary=str(destination),
                            reversible=True,
                        ),
                    )
        if not changed and not file_changes:
            raise PlanValidationError(
                "The selected metadata and organised file path already "
                "match the catalogue."
            )

        title = str(row["title"] or row["file_name"] or "Untitled")
        before = {field: row[field] for field in changed}
        fields = ", ".join(field.replace("_", " ") for field in changed)
        summary_parts: list[str] = []
        if changed:
            summary_parts.append(
                f"Update the reviewed {fields} for '{title}'."
            )
        if destination is not None and file_changes:
            summary_parts.append(
                "Create the required Author or shared -=Series=- folders, then "
                "move and rename the ebook.\n"
                f"From: {file_changes[0].before_summary}\n"
                f"To: {destination}"
            )
        return ChangePlan(
            operation_type="metadata_update",
            title=f"Update metadata for {title}",
            summary=" ".join(summary_parts) or (
                f"Update the reviewed {fields} for “{title}”. "
                "The ebook file itself will not be edited."
            ),
            component="metadata_studio",
            initiator="user",
            affected_book_count=1,
            risk=(
                OperationRisk.HIGH
                if file_changes
                else OperationRisk.MEDIUM
            ),
            reversibility=Reversibility.PARTIAL,
            confirmation_requirement=ConfirmationRequirement.EXPLICIT,
            basis_token=self._metadata_update_basis(
                int(book_id),
                destination=destination if file_changes else None,
            ),
            database_changes=(
                ChangePlanItem(
                    target=ChangeTarget.DATABASE,
                    action="update_book_metadata",
                    description=(
                        (
                            f"Replace {len(changed)} reviewed metadata "
                            f"{'field' if len(changed) == 1 else 'fields'}."
                        )
                        if changed
                        else "Keep the reviewed metadata unchanged."
                    ),
                    book_id=int(book_id),
                    book_title=title,
                    before_summary=json.dumps(
                        before,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    after_summary=json.dumps(
                        changed,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    reversible=False,
                ),
            ),
            file_changes=file_changes,
            warnings=(
                "A verified catalogue backup is created before Apply.",
                (
                    "The ebook contents are not rewritten. The physical file "
                    "will be moved only to the exact path shown above."
                    if file_changes
                    else "The ebook file itself will not be changed."
                ),
                "Twano refuses to overwrite an existing file and restores "
                "the original path if the catalogue update fails.",
            ),
        )

    def preview_metadata_destination(
        self,
        book_id: int,
        reviewed: Mapping[str, object],
    ) -> Path:
        """Return the proposed organised path without recording a plan."""
        row = self.database.get_book_by_id(int(book_id))
        if row is None:
            raise PlanValidationError(f"Unknown book ID: {book_id}")
        cleaned = dict(reviewed)
        for field, label in (
            ("series_number", "Series number"),
            ("series_group_number", "Series group number"),
        ):
            number = cleaned.get(field)
            if number not in (None, ""):
                try:
                    cleaned[field] = float(number)
                except (TypeError, ValueError) as error:
                    raise PlanValidationError(f"{label} must be a number.") from error
        self._canonicalise_series_values(row, cleaned)
        destination = self._metadata_destination(row, cleaned)
        source = Path(str(row["file_path"])).resolve()
        if destination == source:
            return destination
        return self._resolve_catalogued_edition_collision(
            row,
            cleaned,
            destination,
        )

    def _canonicalise_series_values(
        self,
        row: Mapping[str, object],
        cleaned: dict[str, object],
    ) -> None:
        """Normalise verified provider aliases before metadata or path changes."""
        current_series = cleaned.get("series", row["series"])
        current_title = cleaned.get("title", row["title"])
        current_number = cleaned.get("series_number", row["series_number"])
        series, number = canonical_series_details(
            str(current_series or ""),
            title=str(current_title or ""),
            number=current_number,
        )
        if series:
            # A free-text resolver (a web search snippet, a scraped
            # article) can return this exact series under slightly
            # different wording on different runs. Snap back onto
            # whatever name this user's own library already established,
            # so every volume keeps landing in the same shared folder
            # regardless of what a later lookup happens to return.
            series = match_existing_series(
                series,
                self.database.get_distinct_series_names(),
            )
        if series != str(current_series or "").strip():
            cleaned["series"] = series
        if number != str(current_number or "").strip():
            cleaned["series_number"] = float(number) if number else None

    def _organized_destination_root(self, row: Mapping[str, object]) -> Path:
        """Return the user's configured destination, or the watched root.

        Organised books move into one shared destination folder when the
        user has configured one in Settings, instead of staying inside
        whichever watched library they happened to be scanned from.
        """
        configured = (
            self._preferences.load_organization_preferences()
            .destination_folder
        )
        if configured:
            return Path(configured).resolve()
        return Path(str(row["library_folder"])).resolve()

    def _metadata_destination(
        self,
        row: Mapping[str, object],
        reviewed: Mapping[str, object],
    ) -> Path:
        """Return one safe Author or shared-Series path inside the destination."""
        title = self._safe_path_part(reviewed.get("title") or row["title"])
        author = self._safe_path_part(reviewed.get("author") or row["author"])
        if not title or not author:
            raise PlanValidationError(
                "A title and author are required before the file can be "
                "organised."
            )
        series = self._safe_path_part(reviewed.get("series") or row["series"])
        series_group = self._safe_path_part(
            reviewed.get("series_group") or row["series_group"]
        )
        series_number = (
            reviewed["series_number"]
            if "series_number" in reviewed
            else row["series_number"]
        )
        root = self._organized_destination_root(row)
        extension = Path(str(row["file_path"])).suffix
        if not extension:
            raise PlanValidationError(
                "The selected ebook has no filename extension."
            )
        if series:
            # Volumes in one series can have different authors. A shared
            # series path preserves one continuous reading order.
            folder = root / "-=Series=-"
            if series_group:
                folder /= series_group
            folder /= series
            if series_number in (None, ""):
                filename = f"{title} - {author}{extension}"
            else:
                prefix = self._series_order_prefix(float(series_number))
                filename = f"{prefix} - {title} - {author}{extension}"
        else:
            folder = root / author
            filename = f"{title} - {author}{extension}"
        destination = (folder / filename).resolve()
        try:
            destination.relative_to(root)
        except ValueError as error:
            raise PlanValidationError(
                "The organised path would leave the configured destination."
            ) from error
        return destination

    def _resolve_catalogued_edition_collision(
        self,
        row: Mapping[str, object],
        reviewed: Mapping[str, object],
        destination: Path,
    ) -> Path:
        """Keep separately catalogued ISBN editions without overwriting either."""
        if not destination.exists():
            return destination
        existing = self.database.get_book_by_file_path(destination)
        if existing is None or int(existing["id"]) == int(row["id"]):
            return destination
        reviewed_isbn = self._normalised_isbn(
            reviewed.get("isbn") or row["isbn"]
        )
        existing_isbn = self._normalised_isbn(existing["isbn"])
        if not reviewed_isbn or not existing_isbn or reviewed_isbn == existing_isbn:
            return destination
        edition_destination = destination.with_name(
            f"{destination.stem} [ISBN {reviewed_isbn}]{destination.suffix}"
        )
        if edition_destination.exists():
            current_path = Path(str(row["file_path"])).resolve()
            if edition_destination.resolve() == current_path:
                return current_path
            return destination
        return edition_destination

    @staticmethod
    def _normalised_isbn(value: object) -> str:
        """Return a filename-safe ISBN comparison value."""
        return "".join(
            character
            for character in str(value or "").upper()
            if character.isdigit() or character == "X"
        )

    def metadata_workflow_is_complete(self, book_id: int) -> bool:
        """Return whether metadata, cover, filename, and folder are complete."""
        row = self.database.get_book_by_id(int(book_id))
        if row is None:
            return False
        return self.metadata_workflow_record_is_complete(row)

    def metadata_workflow_record_is_complete(
        self,
        row: Mapping[str, object],
    ) -> bool:
        """Validate an already loaded catalogue record without another query."""
        return self._metadata_result_is_complete(row, {}, None)

    def _metadata_result_is_complete(
        self,
        row: Mapping[str, object],
        reviewed: Mapping[str, object],
        destination: Path | None,
    ) -> bool:
        """Validate the final reviewed state used by the completion marker."""
        row_keys = set(row.keys()) if hasattr(row, "keys") else set()

        def final_value(field: str) -> str:
            if field in reviewed:
                return str(reviewed[field] or "").strip()
            if field in row_keys:
                return str(row[field] or "").strip()
            return ""

        title = final_value("title")
        author = final_value("author")
        description = final_value("description")
        cover_path = final_value("cover_path")
        series = final_value("series")
        series_number = final_value("series_number")
        if (
            not title
            or not author
            or author.casefold() in {"unknown", "unknown author"}
            or not description
            or not cover_path
            or bool(series) != bool(series_number)
        ):
            return False
        try:
            expected = self._metadata_destination(row, reviewed)
            expected = self._resolve_catalogued_edition_collision(
                row,
                reviewed,
                expected,
            )
        except PlanValidationError:
            return False
        final_path = destination or Path(str(row["file_path"])).resolve()
        return os.path.normcase(str(final_path.resolve())) == os.path.normcase(
            str(expected.resolve())
        )

    @staticmethod
    def _safe_path_part(value: object) -> str:
        """Make one user-visible metadata value safe for Windows paths."""
        text = " ".join(str(value or "").split())
        for character in '<>:"/\\|?*':
            text = text.replace(character, "-")
        text = text.rstrip(" .")
        reserved = {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{number}" for number in range(1, 10)),
            *(f"LPT{number}" for number in range(1, 10)),
        }
        if text.upper() in reserved:
            text = f"{text}-book"
        return text[:150].rstrip(" .")

    @staticmethod
    def _series_order_prefix(value: float) -> str:
        if value <= 0:
            raise PlanValidationError(
                "Series number must be greater than zero."
            )
        if value.is_integer():
            return f"{int(value):02d}"
        return f"{value:05.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def scan_apply_basis(
        *,
        source_id: int,
        scan_token: str,
        preview_counts: dict[str, int],
    ) -> str:
        """Bind one protection record to one immutable Scan preview."""
        payload = {
            "source_id": int(source_id),
            "scan_token": str(scan_token),
            "preview_counts": {
                key: max(0, int(preview_counts.get(key, 0)))
                for key in (
                    "discovered",
                    "new",
                    "changed",
                    "missing",
                    "unchanged",
                    "unreadable",
                    "skipped",
                )
            },
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"scan-apply-v1:{hashlib.sha256(encoded).hexdigest()}"

    def record_confirmed_scan_apply(
        self,
        *,
        source_id: int,
        source_name: str,
        scan_token: str,
        preview_counts: dict[str, int],
    ) -> OperationRecord:
        """Record the user's existing Apply confirmation as a protected plan."""
        counts = {
            key: max(0, int(preview_counts.get(key, 0)))
            for key in (
                "discovered",
                "new",
                "changed",
                "missing",
                "unchanged",
                "unreadable",
                "skipped",
            )
        }
        applicable = counts["new"] + counts["changed"] + counts["missing"]
        if applicable <= 0:
            raise PlanValidationError(
                "This scan preview contains no catalogue changes."
            )
        display_name = " ".join(str(source_name).split()) or (
            f"Source {int(source_id)}"
        )
        changes: list[ChangePlanItem] = []
        descriptions = (
            (
                "scan_add_books",
                counts["new"],
                "Add",
                "newly discovered books",
            ),
            (
                "scan_refresh_books",
                counts["changed"],
                "Refresh",
                "changed catalogue records",
            ),
            (
                "scan_mark_missing",
                counts["missing"],
                "Mark",
                "catalogue records whose files are missing",
            ),
            (
                "scan_refresh_seen",
                counts["unchanged"],
                "Confirm",
                "unchanged catalogue records as seen",
            ),
        )
        for action, count, verb, description in descriptions:
            if count <= 0:
                continue
            changes.append(
                ChangePlanItem(
                    target=ChangeTarget.DATABASE,
                    action=action,
                    description=(
                        f"{verb} up to {count:,} {description} after final "
                        "file and catalogue safety checks."
                    ),
                    before_summary=f"Preview classified {count:,}.",
                    after_summary=(
                        "The exact applied and safely skipped counts will be "
                        "stored in Scan History."
                    ),
                    reversible=False,
                )
            )
        basis_token = self.scan_apply_basis(
            source_id=source_id,
            scan_token=scan_token,
            preview_counts=counts,
        )
        plan = ChangePlan(
            operation_type="scan_apply",
            title=f"Apply scan preview for {display_name}",
            summary=(
                f"Apply the confirmed preview for {display_name}: "
                f"{counts['new']:,} new, {counts['changed']:,} changed, "
                f"{counts['missing']:,} missing, and "
                f"{counts['unchanged']:,} unchanged. Every candidate is "
                "rechecked before the catalogue transaction."
            ),
            component="scan",
            initiator="user",
            affected_book_count=(
                counts["new"]
                + counts["changed"]
                + counts["missing"]
                + counts["unchanged"]
            ),
            risk=OperationRisk.MEDIUM,
            reversibility=Reversibility.PARTIAL,
            confirmation_requirement=ConfirmationRequirement.EXPLICIT,
            basis_token=basis_token,
            database_changes=tuple(changes),
            warnings=(
                "A verified catalogue backup is created automatically before "
                "the scan changes commit.",
                "Ebook files are never changed by Scan Apply.",
                "Scan Apply has no one-click Undo. The automatic backup can "
                "restore the complete earlier catalogue if needed.",
                "Candidates changed after preview are safely skipped.",
            ),
        )
        record = self.record_change_plan(plan)
        confirmation = PlanConfirmation(
            plan_token=plan.plan_token,
            approved=True,
            confirmer="user",
            confirmation_text="Apply Preview",
        )
        try:
            return self.approve_change_plan(
                record.operation_id,
                confirmation,
                current_basis_token=basis_token,
            )
        except Exception:
            try:
                self.cancel_change_plan(record.operation_id)
            except Exception:
                pass
            raise

    def preview_restore_operation(
        self,
        backup_path: str | Path,
    ) -> OperationRecord:
        """Record a critical, mutation-free preview for one exact backup."""
        path = Path(backup_path)
        record = self.inspect_backup(path, verify_contents=False)
        if record.status != BackupStatus.VERIFIED:
            raise PlanValidationError(
                "Only a Twano-owned backup with valid verification evidence "
                "can be previewed for Restore."
            )
        payload = self._owned_backup_payload(path)
        basis_token = self._restore_basis(payload)
        created_label = self._display_timestamp(
            str(payload["created_at"])
        )
        plan = ChangePlan(
            operation_type="database_restore",
            title="Restore the catalogue from a verified backup",
            summary=(
                f"Replace the live catalogue with {path.name}, created "
                f"{created_label}. The selected backup will be fully "
                "re-verified and the current catalogue will receive its "
                "own verified recovery backup before replacement."
            ),
            component="protection_centre",
            initiator="user",
            affected_book_count=0,
            risk=OperationRisk.HIGH,
            reversibility=Reversibility.PARTIAL,
            confirmation_requirement=ConfirmationRequirement.EXPLICIT,
            basis_token=basis_token,
            database_changes=(
                ChangePlanItem(
                    target=ChangeTarget.DATABASE,
                    action="restore_catalogue",
                    description=(
                        f"Replace the live catalogue with the exact verified "
                        f"snapshot {path.name}."
                    ),
                    before_summary=str(self.live_database_path),
                    after_summary=json.dumps(
                        payload,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    reversible=True,
                ),
            ),
            warnings=(
                "Restore replaces the complete catalogue, including books, "
                "collections, sources, scan history, and protection history "
                "recorded after the selected backup.",
                "The selected backup is re-verified before any replacement.",
                "A separate verified recovery backup of the current live "
                "catalogue is mandatory and is retained after Restore.",
                "No ebook file is changed.",
            ),
        )
        return self.record_change_plan(plan)

    def preview_retention_cleanup(
        self,
        policy: BackupPolicy,
        *,
        now: datetime | None = None,
        is_cancelled: CancellationCheck | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> RetentionPreview:
        """Verify and record the exact backups an age cleanup would delete."""
        if policy.retention_days == 0:
            return RetentionPreview(
                operation=None,
                cutoff_at="",
                candidate_count=0,
                candidate_bytes=0,
                retained_count=len(self.list_backups(policy)),
                excluded_count=0,
            )
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("Retention preview time must include a timezone.")
        cutoff = current.astimezone(timezone.utc) - timedelta(
            days=policy.retention_days
        )
        paths = (
            sorted(
                (
                    path
                    for path in policy.folder.glob(
                        f"{BACKUP_FILE_PREFIX}*{BACKUP_FILE_SUFFIX}"
                    )
                    if path.is_file() and not path.is_symlink()
                ),
                key=lambda path: path.name,
            )
            if policy.folder.is_dir()
            else []
        )
        candidates: list[dict[str, object]] = []
        retained_count = 0
        excluded_count = 0
        for index, path in enumerate(paths, start=1):
            self._check_cancelled(is_cancelled)
            self._progress(
                on_progress,
                int(((index - 1) / max(1, len(paths))) * 90),
                f"Checking retention evidence for {path.name}...",
            )
            try:
                payload = self._owned_backup_payload(path)
                created_at = self._aware_timestamp(
                    str(payload["created_at"]),
                    "backup creation",
                )
            except (OSError, PlanValidationError, ValueError):
                excluded_count += 1
                continue
            if created_at >= cutoff:
                retained_count += 1
                continue
            verified = self.verify_backup(
                path,
                is_cancelled=is_cancelled,
            )
            if verified.status != BackupStatus.VERIFIED:
                excluded_count += 1
                continue
            payload.update(
                {
                    "retention_days": policy.retention_days,
                    "cutoff_at": cutoff.isoformat(),
                    "backup_folder": str(policy.folder.resolve()),
                }
            )
            candidates.append(payload)

        self._check_cancelled(is_cancelled)
        candidate_bytes = sum(
            int(candidate["size_bytes"]) for candidate in candidates
        )
        if not candidates:
            self._progress(
                on_progress,
                100,
                "Retention dry run found no verified expired backups.",
            )
            return RetentionPreview(
                operation=None,
                cutoff_at=cutoff.isoformat(),
                candidate_count=0,
                candidate_bytes=0,
                retained_count=retained_count,
                excluded_count=excluded_count,
            )

        basis_token = self._retention_basis(tuple(candidates))
        file_changes = tuple(
            ChangePlanItem(
                target=ChangeTarget.FILE,
                action="delete_verified_backup",
                description=(
                    f"Delete Twano-owned verified backup "
                    f"{Path(str(candidate['backup_path'])).name} and its "
                    "exact verification manifest."
                ),
                before_summary=(
                    f"{int(candidate['size_bytes'])} bytes; created "
                    f"{self._display_timestamp(str(candidate['created_at']))}"
                ),
                after_summary=json.dumps(
                    candidate,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                reversible=False,
            )
            for candidate in candidates
        )
        plan = ChangePlan(
            operation_type="backup_retention_cleanup",
            title="Delete expired verified catalogue backups",
            summary=(
                f"Delete {len(candidates)} exact Twano-owned verified "
                f"backup(s), totalling {candidate_bytes} bytes, because "
                f"they are older than {policy.retention_days} days."
            ),
            component="protection_centre",
            initiator="user",
            affected_book_count=0,
            risk=OperationRisk.MEDIUM,
            reversibility=Reversibility.NONE,
            confirmation_requirement=ConfirmationRequirement.EXPLICIT,
            basis_token=basis_token,
            file_changes=file_changes,
            warnings=(
                "This is the recorded dry-run result; approval and Apply "
                "remain separate.",
                "Every exact backup and manifest pair will be fully "
                "re-verified immediately before deletion.",
                "Unrelated, changed, corrupt, legacy, unverified, recent, "
                "and symbolic-link files are excluded.",
                "Deleted backup artifacts do not have Undo.",
            ),
        )
        operation = self.record_change_plan(plan)
        self._progress(on_progress, 100, "Retention dry run recorded.")
        return RetentionPreview(
            operation=operation,
            cutoff_at=cutoff.isoformat(),
            candidate_count=len(candidates),
            candidate_bytes=candidate_bytes,
            retained_count=retained_count,
            excluded_count=excluded_count,
        )

    def record_change_plan(
        self,
        plan: ChangePlan,
        *,
        source_operation_id: int | None = None,
    ) -> OperationRecord:
        """Persist a mutation-free plan preview and its item evidence."""
        plan_payload = plan.to_dict()
        operation_token = uuid4().hex
        operation = {
            "operation_token": operation_token,
            "plan_token": plan.plan_token,
            "operation_type": plan.operation_type,
            "title": plan.title,
            "summary": plan.summary,
            "initiator": plan.initiator,
            "component": plan.component,
            "created_at": plan.created_at,
            "updated_at": plan.created_at,
            "status": OperationStatus.PLANNED.value,
            "risk": plan.risk.value,
            "reversibility": plan.reversibility.value,
            "confirmation_requirement": (
                plan.confirmation_requirement.value
            ),
            "affected_book_count": plan.affected_book_count,
            "database_change_count": len(plan.database_changes),
            "file_change_count": len(plan.file_changes),
            "warnings_json": json.dumps(list(plan.warnings)),
            "plan_json": json.dumps(
                plan_payload,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "source_operation_id": source_operation_id,
        }
        items = []
        for sequence, item in enumerate(
            plan.database_changes + plan.file_changes,
            start=1,
        ):
            items.append(
                {
                    "item_sequence": sequence,
                    **item.to_dict(),
                    "status": OperationStatus.PLANNED.value,
                }
            )
        operation_id = self.database.create_protection_operation(
            operation,
            items,
        )
        return self.get_operation(operation_id)

    def current_basis_token(
        self,
        record: OperationRecord,
    ) -> str:
        """Recalculate the exact mutable fact used by an executable plan."""
        plan = record.plan
        if plan.operation_type == "collection_create":
            item = self._single_executable_item(
                plan,
                expected_action="create_collection",
            )
            return self._collection_create_basis(item.after_summary)
        if plan.operation_type == "undo_collection_create":
            if record.source_operation_id is None:
                raise PlanValidationError(
                    "The Undo plan has no source operation."
                )
            source = self.get_operation(record.source_operation_id)
            inverse = self._validated_collection_inverse(source)
            return self._collection_undo_basis(source, inverse)
        if plan.operation_type == "database_restore":
            return self._restore_basis(
                self._validated_restore_payload(plan)
            )
        if plan.operation_type == "backup_retention_cleanup":
            return self._retention_basis(
                self._validated_retention_payloads(plan)
            )
        if plan.operation_type == "metadata_update":
            book_id, _values, move = self._validated_metadata_payload(plan)
            return self._metadata_update_basis(
                book_id,
                destination=(Path(move[1]) if move is not None else None),
            )
        return plan.basis_token

    def preview_undo_operation(
        self,
        source_operation_id: int,
    ) -> OperationRecord:
        """Record a detached Undo plan for one exact applied operation."""
        source = self.get_operation(source_operation_id)
        inverse = self._validated_collection_inverse(source)
        if self.database.get_active_undo_operation(source_operation_id):
            raise PlanValidationError(
                "An active Undo already exists for this operation."
            )
        basis_token = self._collection_undo_basis(source, inverse)
        name = str(inverse["collection_name"])
        plan = ChangePlan(
            operation_type="undo_collection_create",
            title=f"Undo: {source.plan.title}",
            summary=(
                f"Remove the exact empty collection “{name}” created by "
                f"operation {source.operation_id}. The original operation "
                "will remain in history as Undone."
            ),
            component="protection_centre",
            initiator="user",
            affected_book_count=0,
            risk=OperationRisk.MEDIUM,
            reversibility=Reversibility.NONE,
            confirmation_requirement=ConfirmationRequirement.EXPLICIT,
            basis_token=basis_token,
            database_changes=(
                ChangePlanItem(
                    target=ChangeTarget.DATABASE,
                    action="delete_collection",
                    description=(
                        f"Delete the empty collection “{name}” created by "
                        f"operation {source.operation_id}."
                    ),
                    before_summary=name,
                    after_summary="Collection removed.",
                    reversible=False,
                ),
            ),
            warnings=(
                "A verified catalogue backup is required before Undo.",
                "Undo stops if the collection was renamed, removed, or now "
                "contains books.",
                "Redo is not enabled in this milestone.",
            ),
        )
        return self.record_change_plan(
            plan,
            source_operation_id=source.operation_id,
        )

    def can_preview_undo(self, operation_id: int) -> bool:
        """Return whether an applied operation still has a provable Undo."""
        try:
            source = self.get_operation(operation_id)
            self._validated_collection_inverse(source)
            if self.database.get_active_undo_operation(operation_id):
                return False
            self._collection_undo_basis(
                source,
                self._validated_collection_inverse(source),
            )
        except (KeyError, PlanValidationError, ValueError):
            return False
        return True

    @staticmethod
    def validate_plan_confirmation(
        plan: ChangePlan,
        confirmation: PlanConfirmation,
        *,
        current_basis_token: str,
        applied_plan_tokens: tuple[str, ...] = (),
    ) -> None:
        """Reject stale, repeated, mismatched, or weak approval evidence."""
        if plan.is_expired():
            raise PlanValidationError(
                "This change plan has expired. Create a fresh preview."
            )
        if current_basis_token != plan.basis_token:
            raise PlanValidationError(
                "The catalogue basis changed after preview. Create a fresh "
                "plan before approval."
            )
        if plan.plan_token in applied_plan_tokens:
            raise PlanValidationError(
                "This change plan has already been applied."
            )
        if confirmation.plan_token != plan.plan_token:
            raise PlanValidationError(
                "Confirmation does not match this exact plan."
            )
        if not confirmation.approved:
            raise PlanValidationError("The change plan was not approved.")
        requirement = plan.confirmation_requirement
        if (
            requirement == ConfirmationRequirement.TYPE_PHRASE
            and confirmation.confirmation_text.strip()
            != plan.confirmation_phrase.strip()
        ):
            raise PlanValidationError(
                "The required confirmation phrase did not match."
            )
        if (
            plan.risk in {OperationRisk.HIGH, OperationRisk.CRITICAL}
            and requirement == ConfirmationRequirement.NONE
        ):
            raise PlanValidationError(
                "High-risk plans require explicit confirmation."
            )

    def approve_change_plan(
        self,
        operation_id: int,
        confirmation: PlanConfirmation,
        *,
        current_basis_token: str,
    ) -> OperationRecord:
        """Record approval without executing the proposed changes."""
        record = self.get_operation(operation_id)
        if record.status != OperationStatus.PLANNED:
            raise PlanValidationError(
                "Only a pending plan can be approved."
            )
        self.validate_plan_confirmation(
            record.plan,
            confirmation,
            current_basis_token=current_basis_token,
        )
        now = datetime.now(timezone.utc).isoformat()
        self.database.transition_protection_operation(
            operation_id,
            expected_statuses=(OperationStatus.PLANNED.value,),
            new_status=OperationStatus.APPROVED.value,
            updated_at=now,
            confirmation_json=json.dumps(
                confirmation.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        return self.get_operation(operation_id)

    def cancel_change_plan(self, operation_id: int) -> OperationRecord:
        """Record cancellation without applying any intended change."""
        now = datetime.now(timezone.utc).isoformat()
        self.database.transition_protection_operation(
            operation_id,
            expected_statuses=(
                OperationStatus.PLANNED.value,
                OperationStatus.APPROVED.value,
            ),
            new_status=OperationStatus.CANCELLED.value,
            updated_at=now,
            finished_at=now,
            item_status=OperationStatus.CANCELLED.value,
        )
        return self.get_operation(operation_id)

    def apply_approved_operation(
        self,
        operation_id: int,
        policy: BackupPolicy,
        protection_mode: ProtectionMode | str,
        *,
        is_cancelled: CancellationCheck | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> OperationRecord:
        """Back up, revalidate, and atomically apply one approved plan."""
        try:
            mode = ProtectionMode(protection_mode)
        except ValueError as error:
            raise PlanValidationError(
                "The current protection mode is invalid."
            ) from error
        if mode != ProtectionMode.STANDARD:
            raise PlanValidationError(
                "Protected Apply is unavailable in Read-Only mode."
            )
        record = self.get_operation(operation_id)
        if record.status != OperationStatus.APPROVED:
            raise PlanValidationError(
                "Only an approved plan can be applied."
            )
        if record.confirmation is None:
            raise PlanValidationError(
                "The approved plan has no confirmation evidence."
            )
        if record.plan.file_changes and record.plan.operation_type not in {
            "backup_retention_cleanup",
            "metadata_update",
        }:
            raise PlanValidationError(
                "This protected executor cannot run the proposed file "
                "changes."
            )
        if record.plan.operation_type not in {
            "collection_create",
            "undo_collection_create",
            "metadata_update",
            "database_restore",
            "backup_retention_cleanup",
        }:
            raise PlanValidationError(
                "This plan type has no protected executor."
            )
        current_basis = self.current_basis_token(record)
        self.validate_plan_confirmation(
            record.plan,
            record.confirmation,
            current_basis_token=current_basis,
        )
        self._check_cancelled(is_cancelled)
        if record.plan.operation_type == "database_restore":
            return self._apply_database_restore(
                record,
                policy,
                is_cancelled=is_cancelled,
                on_progress=on_progress,
            )
        if record.plan.operation_type == "backup_retention_cleanup":
            return self._apply_retention_cleanup(
                record,
                policy,
                is_cancelled=is_cancelled,
                on_progress=on_progress,
            )
        if on_progress is not None:
            on_progress(0, "Creating the required verified backup…")
        try:
            backup = self.create_verified_backup(
                policy,
                is_cancelled=is_cancelled,
                on_progress=(
                    (
                        lambda percent, message: on_progress(
                            min(85, int(percent * 0.85)),
                            message,
                        )
                    )
                    if on_progress is not None
                    else None
                ),
            )
        except BackupCancelled:
            raise
        except Exception as error:
            self._record_execution_failure(
                record.operation_id,
                error=error,
                backup_identity="",
                rollback_outcome=(
                    "No catalogue mutation started because the required "
                    "verified backup did not complete."
                ),
            )
            raise ProtectedExecutionError(
                "The required verified backup failed; no catalogue change "
                "was attempted."
            ) from error

        self._check_cancelled(is_cancelled)
        if on_progress is not None:
            on_progress(90, "Applying one protected database transaction…")
        now = datetime.now(timezone.utc).isoformat()
        try:
            record = self.get_operation(operation_id)
            if record.confirmation is None:
                raise PlanValidationError(
                    "The approved plan has no confirmation evidence."
                )
            self.validate_plan_confirmation(
                record.plan,
                record.confirmation,
                current_basis_token=self.current_basis_token(record),
            )
            if record.plan.operation_type == "collection_create":
                item = self._single_executable_item(
                    record.plan,
                    expected_action="create_collection",
                )
                self.database.apply_collection_create_operation(
                    record.operation_id,
                    collection_name=item.after_summary,
                    backup_identity=str(backup.path),
                    updated_at=now,
                )
            elif record.plan.operation_type == "metadata_update":
                book_id, values, move = self._validated_metadata_payload(
                    record.plan
                )
                self._apply_metadata_update(
                    record.operation_id,
                    book_id=book_id,
                    values=values,
                    move=move,
                    backup_identity=str(backup.path),
                    updated_at=now,
                )
            else:
                if record.source_operation_id is None:
                    raise PlanValidationError(
                        "The Undo plan has no source operation."
                    )
                source = self.get_operation(record.source_operation_id)
                inverse = self._validated_collection_inverse(source)
                self.database.apply_collection_undo_operation(
                    record.operation_id,
                    source_operation_id=source.operation_id,
                    collection_id=int(inverse["collection_id"]),
                    collection_name=str(inverse["collection_name"]),
                    backup_identity=str(backup.path),
                    updated_at=now,
                )
        except Exception as error:
            self._record_execution_failure(
                record.operation_id,
                error=error,
                backup_identity=str(backup.path),
                rollback_outcome=(
                    "The database transaction rolled back; no partial "
                    "catalogue change was committed."
                ),
            )
            raise ProtectedExecutionError(
                "Protected execution failed and its database transaction "
                "was rolled back."
            ) from error
        if on_progress is not None:
            on_progress(100, "Protected operation completed.")
        return self.get_operation(record.operation_id)

    def _apply_metadata_update(
        self,
        operation_id: int,
        *,
        book_id: int,
        values: Mapping[str, object],
        move: tuple[str, str] | None,
        backup_identity: str,
        updated_at: str,
    ) -> None:
        """Move one ebook safely, then commit its catalogue path and metadata."""
        source: Path | None = None
        destination: Path | None = None
        created_directories: list[Path] = []
        moved = False
        row = self.database.get_book_by_id(int(book_id))
        if row is None:
            raise PlanValidationError(
                "The selected book is no longer in the catalogue."
            )
        workflow_complete = self._metadata_result_is_complete(
            row,
            values,
            Path(move[1]) if move is not None else None,
        )
        try:
            if move is not None:
                source = Path(move[0])
                destination = Path(move[1])
                if not source.is_file():
                    raise FileNotFoundError(
                        "The ebook is no longer at its previewed path: "
                        f"{source}"
                    )
                if destination.exists():
                    raise FileExistsError(
                        "Twano will not overwrite the existing file: "
                        f"{destination}"
                    )
                pending: list[Path] = []
                parent = destination.parent
                while not parent.exists():
                    pending.append(parent)
                    parent = parent.parent
                destination.parent.mkdir(parents=True, exist_ok=True)
                created_directories = list(reversed(pending))
                os.replace(source, destination)
                moved = True
            self.database.apply_metadata_update_operation(
                operation_id,
                book_id=book_id,
                values=values,
                source_path=(str(source) if source is not None else None),
                destination_path=(
                    str(destination) if destination is not None else None
                ),
                organized_root=(
                    str(self._organized_destination_root(row))
                    if move is not None
                    else None
                ),
                metadata_workflow_complete=workflow_complete,
                backup_identity=backup_identity,
                updated_at=updated_at,
            )
        except Exception:
            if moved and source is not None and destination is not None:
                source.parent.mkdir(parents=True, exist_ok=True)
                if source.exists():
                    raise ProtectedExecutionError(
                        "The organised file could not be restored because "
                        f"its original path now exists: {source}"
                    )
                os.replace(destination, source)
                for directory in reversed(created_directories):
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
            raise

    def _apply_database_restore(
        self,
        record: OperationRecord,
        policy: BackupPolicy,
        *,
        is_cancelled: CancellationCheck | None,
        on_progress: ProgressCallback | None,
    ) -> OperationRecord:
        """Restore one verified snapshot after preserving current live state."""
        payload = self._validated_restore_payload(record.plan)
        backup_path = Path(str(payload["backup_path"]))
        recovery: BackupRecord | None = None
        staged_path = self.live_database_path.parent / (
            f".{self.live_database_path.name}."
            f"{record.operation_token}.restore.partial"
        )
        rollback_stage = self.live_database_path.parent / (
            f".{self.live_database_path.name}."
            f"{record.operation_token}.rollback.partial"
        )
        replaced = False
        try:
            self._progress(
                on_progress,
                2,
                "Checking the selected backup...",
            )
            verified = self.verify_backup(
                backup_path,
                is_cancelled=is_cancelled,
                on_progress=(
                    (
                        lambda percent, message: self._progress(
                            on_progress,
                            2 + int(percent * 0.18),
                            message,
                        )
                    )
                    if on_progress is not None
                    else None
                ),
            )
            if (
                verified.status != BackupStatus.VERIFIED
                or verified.sha256 != str(payload["sha256"])
            ):
                raise PlanValidationError(
                    "The selected backup no longer matches the Restore "
                    "preview."
                )
            self._check_cancelled(is_cancelled)
            self._progress(
                on_progress,
                22,
                "Creating a safety copy of the current catalogue...",
            )
            recovery = self.create_verified_backup(
                policy,
                is_cancelled=is_cancelled,
                on_progress=(
                    (
                        lambda percent, message: self._progress(
                            on_progress,
                            22 + int(percent * 0.48),
                            message,
                        )
                    )
                    if on_progress is not None
                    else None
                ),
            )
            self._check_cancelled(is_cancelled)
            self._progress(
                on_progress,
                72,
                "Preparing the restored catalogue...",
            )
            self._copy_file(
                backup_path,
                staged_path,
                is_cancelled=is_cancelled,
                on_progress=on_progress,
                progress_start=72,
                progress_end=88,
            )
            self.database.verify_database_backup(
                staged_path,
                is_cancelled=is_cancelled,
            )
            staged_sha256 = self._sha256(
                staged_path,
                is_cancelled=is_cancelled,
                on_progress=on_progress,
                progress_start=88,
                progress_end=94,
            )
            if staged_sha256 != str(payload["sha256"]):
                raise PlanValidationError(
                    "The prepared Restore copy failed its checksum check."
                )
            self._check_cancelled(is_cancelled)
            applying_at = datetime.now(timezone.utc).isoformat()
            self.database.transition_protection_operation(
                record.operation_id,
                expected_statuses=(OperationStatus.APPROVED.value,),
                new_status=OperationStatus.APPLYING.value,
                updated_at=applying_at,
                started_at=applying_at,
                backup_identity=str(recovery.path),
                item_status=OperationStatus.APPLYING.value,
            )
            self._progress(
                on_progress,
                96,
                "Restoring the catalogue...",
            )
            os.replace(staged_path, self.live_database_path)
            replaced = True
            self.database.initialise_database()
            finished_at = datetime.now(timezone.utc).isoformat()
            self.database.complete_embedded_backup_operation(
                backup_path,
                updated_at=finished_at,
            )
            restored = self._persist_completed_restore_operation(
                record,
                recovery,
                started_at=applying_at,
                finished_at=finished_at,
            )
            self._progress(
                on_progress,
                100,
                "Catalogue restored. The safety copy was kept.",
            )
            return restored
        except BackupCancelled:
            raise
        except Exception as error:
            recovery_identity = str(recovery.path) if recovery else ""
            if replaced and recovery is not None:
                try:
                    self._copy_file(
                        recovery.path,
                        rollback_stage,
                        is_cancelled=None,
                        on_progress=None,
                        progress_start=0,
                        progress_end=100,
                    )
                    self.database.verify_database_backup(rollback_stage)
                    rollback_sha256 = self._sha256(
                        rollback_stage,
                        is_cancelled=None,
                        on_progress=None,
                        progress_start=0,
                        progress_end=100,
                    )
                    if rollback_sha256 != recovery.sha256:
                        raise InvalidDatabaseBackup(
                            "The recovery copy checksum did not match."
                        )
                    os.replace(rollback_stage, self.live_database_path)
                    self.database.initialise_database()
                    rollback_at = datetime.now(timezone.utc).isoformat()
                    self.database.complete_embedded_backup_operation(
                        recovery.path,
                        updated_at=rollback_at,
                    )
                    self._record_execution_failure(
                        record.operation_id,
                        error=error,
                        backup_identity=recovery_identity,
                        rollback_outcome=(
                            "Restore did not finish; the pre-restore "
                            "catalogue was recovered from the verified "
                            "safety copy."
                        ),
                    )
                except Exception as rollback_error:
                    raise ProtectedExecutionError(
                        "Restore could not finish. The verified safety copy "
                        f"is preserved at {recovery.path}. Automatic recovery "
                        f"also failed: {rollback_error}"
                    ) from error
            else:
                try:
                    current = self.get_operation(record.operation_id)
                    expected = (
                        (OperationStatus.APPLYING,)
                        if current.status == OperationStatus.APPLYING
                        else (OperationStatus.APPROVED,)
                    )
                    self._record_execution_failure(
                        record.operation_id,
                        error=error,
                        backup_identity=recovery_identity,
                        rollback_outcome=(
                            "The live catalogue was not replaced. "
                            + (
                                "The verified safety copy remains available."
                                if recovery is not None
                                else (
                                    "No safety copy was required because "
                                    "Restore stopped earlier."
                                )
                            )
                        ),
                        expected_statuses=expected,
                    )
                except Exception:
                    pass
            raise ProtectedExecutionError(
                "Restore stopped safely. The current catalogue was kept."
                if not replaced
                else (
                    "Restore failed after replacement and the pre-restore "
                    "catalogue was recovered."
                )
            ) from error
        finally:
            staged_path.unlink(missing_ok=True)
            rollback_stage.unlink(missing_ok=True)

    def _apply_retention_cleanup(
        self,
        record: OperationRecord,
        policy: BackupPolicy,
        *,
        is_cancelled: CancellationCheck | None,
        on_progress: ProgressCallback | None,
    ) -> OperationRecord:
        """Revalidate and delete only the exact owned dry-run candidates."""
        payloads = self._validated_retention_payloads(record.plan)
        try:
            for index, payload in enumerate(payloads, start=1):
                if (
                    int(payload["retention_days"])
                    != policy.retention_days
                    or Path(str(payload["backup_folder"])).resolve()
                    != policy.folder.resolve()
                ):
                    raise PlanValidationError(
                        "Backup settings changed after the cleanup review."
                    )
                self._check_cancelled(is_cancelled)
                path = Path(str(payload["backup_path"]))
                self._progress(
                    on_progress,
                    int(((index - 1) / len(payloads)) * 75),
                    f"Rechecking {path.name}...",
                )
                verified = self.verify_backup(
                    path,
                    is_cancelled=is_cancelled,
                )
                if (
                    verified.status != BackupStatus.VERIFIED
                    or verified.sha256 != str(payload["sha256"])
                ):
                    raise PlanValidationError(
                        f"{path.name} changed after the cleanup review."
                    )
            self._check_cancelled(is_cancelled)
        except BackupCancelled:
            raise
        except Exception as error:
            self._record_execution_failure(
                record.operation_id,
                error=error,
                backup_identity="",
                rollback_outcome=(
                    "No backup was deleted because validation did not "
                    "complete."
                ),
            )
            raise ProtectedExecutionError(
                "Cleanup stopped before deleting any backup."
            ) from error

        applying_at = datetime.now(timezone.utc).isoformat()
        self.database.transition_protection_operation(
            record.operation_id,
            expected_statuses=(OperationStatus.APPROVED.value,),
            new_status=OperationStatus.APPLYING.value,
            updated_at=applying_at,
            started_at=applying_at,
            item_status=OperationStatus.APPLYING.value,
        )
        quarantine = policy.folder / (
            f".twano-retention-{record.operation_token}"
        )
        moved: list[tuple[Path, Path]] = []
        try:
            quarantine.mkdir()
            for index, payload in enumerate(payloads, start=1):
                backup_path = Path(str(payload["backup_path"]))
                manifest_path = Path(str(payload["manifest_path"]))
                for original in (backup_path, manifest_path):
                    quarantined = quarantine / (
                        f"{index}-{original.name}"
                    )
                    os.replace(original, quarantined)
                    moved.append((original, quarantined))
            self._progress(
                on_progress,
                90,
                "Removing the reviewed old backups...",
            )
        except Exception as error:
            rollback_error = self._restore_quarantined_files(moved)
            if rollback_error is None and quarantine.is_dir():
                quarantine.rmdir()
            outcome = (
                "All moved backup artifacts were returned to their original "
                "locations."
                if rollback_error is None
                else f"Cleanup rollback needs attention: {rollback_error}"
            )
            self._record_execution_failure(
                record.operation_id,
                error=error,
                backup_identity="",
                rollback_outcome=outcome,
                expected_statuses=(OperationStatus.APPLYING,),
                outcome_status=(
                    OperationStatus.ROLLED_BACK
                    if rollback_error is None
                    else OperationStatus.PARTIAL
                ),
            )
            raise ProtectedExecutionError(
                "Cleanup could not move the reviewed backups safely."
            ) from error

        try:
            for _original, quarantined in moved:
                quarantined.unlink()
            quarantine.rmdir()
        except Exception as error:
            rollback_error = self._restore_quarantined_files(moved)
            if rollback_error is None and quarantine.is_dir():
                quarantine.rmdir()
            missing_originals = tuple(
                original for original, _quarantined in moved
                if not original.exists()
            )
            outcome = (
                "Some reviewed backup artifacts were deleted; any remaining "
                "quarantined artifacts were returned. Missing: "
                + ", ".join(str(path) for path in missing_originals)
            )
            if rollback_error is not None:
                outcome += f". Additional recovery issue: {rollback_error}"
            self._record_execution_failure(
                record.operation_id,
                error=error,
                backup_identity="",
                rollback_outcome=outcome,
                expected_statuses=(OperationStatus.APPLYING,),
                outcome_status=OperationStatus.PARTIAL,
            )
            raise ProtectedExecutionError(
                "Cleanup only partly completed; the history records the "
                "remaining recovery evidence."
            ) from error

        finished_at = datetime.now(timezone.utc).isoformat()
        self.database.transition_protection_operation(
            record.operation_id,
            expected_statuses=(OperationStatus.APPLYING.value,),
            new_status=OperationStatus.APPLIED.value,
            updated_at=finished_at,
            finished_at=finished_at,
            rollback_outcome=(
                f"Not required; {len(payloads)} exact verified backup "
                "pair(s) were removed."
            ),
            item_status=OperationStatus.APPLIED.value,
        )
        self._progress(on_progress, 100, "Old backups removed.")
        return self.get_operation(record.operation_id)

    def _record_execution_failure(
        self,
        operation_id: int,
        *,
        error: Exception,
        backup_identity: str,
        rollback_outcome: str,
        expected_statuses: tuple[OperationStatus, ...] = (
            OperationStatus.APPROVED,
        ),
        outcome_status: OperationStatus = OperationStatus.FAILED,
    ) -> None:
        """Persist concise failure evidence after the mutation rolled back."""
        now = datetime.now(timezone.utc).isoformat()
        self.database.transition_protection_operation(
            operation_id,
            expected_statuses=tuple(
                status.value for status in expected_statuses
            ),
            new_status=outcome_status.value,
            updated_at=now,
            finished_at=now,
            backup_identity=backup_identity,
            error_summary=str(error) or error.__class__.__name__,
            rollback_outcome=rollback_outcome,
            item_status=outcome_status.value,
        )

    def list_operation_history(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[OperationRecord, ...]:
        rows = self.database.list_protection_operations(
            limit=limit,
            offset=offset,
        )
        return tuple(self._operation_from_rows(row, ()) for row in rows)

    def get_operation(self, operation_id: int) -> OperationRecord:
        result = self.database.get_protection_operation(operation_id)
        if result is None:
            raise KeyError(
                f"Protection operation not found: {operation_id}"
            )
        return self._operation_from_rows(*result)

    def export_operation_report(
        self,
        operation_id: int,
        destination: str | Path,
        *,
        overwrite: bool = False,
        is_cancelled: CancellationCheck | None = None,
    ) -> Path:
        """Write one readable report atomically outside the GUI thread."""
        path = Path(destination)
        if not path.is_absolute():
            raise ValueError("Report destination must be an absolute path.")
        if not path.parent.is_dir():
            raise FileNotFoundError(
                f"Report folder does not exist: {path.parent}"
            )
        if path.exists() and not overwrite:
            raise FileExistsError(f"Report already exists: {path}")
        if is_cancelled is not None and is_cancelled():
            raise ReportExportCancelled("Report export cancelled.")
        record = self.get_operation(operation_id)
        report = self.render_operation_report(record)
        partial = path.parent / (
            f".{path.name}.{uuid4().hex}.partial"
        )
        try:
            partial.write_text(report, encoding="utf-8")
            if is_cancelled is not None and is_cancelled():
                raise ReportExportCancelled("Report export cancelled.")
            if path.exists() and not overwrite:
                raise FileExistsError(f"Report already exists: {path}")
            os.replace(partial, path)
        finally:
            partial.unlink(missing_ok=True)
        return path

    @staticmethod
    def render_operation_report(record: OperationRecord) -> str:
        """Return a concise Markdown report for one persistent operation."""
        plan = record.plan
        lines = [
            "# Twano Operation Report",
            "",
            f"- Operation ID: {record.operation_id}",
            f"- Operation token: `{record.operation_token}`",
            f"- Plan token: `{plan.plan_token}`",
            f"- Status: {record.status.value}",
            f"- Type: {plan.operation_type}",
            f"- Title: {plan.title}",
            f"- Initiator: {plan.initiator}",
            f"- Component: {plan.component}",
            f"- Created: {record.created_at}",
            f"- Updated: {record.updated_at}",
            f"- Risk: {plan.risk.value}",
            f"- Reversibility: {plan.reversibility.value}",
            f"- Affected books: {plan.affected_book_count}",
            f"- Database changes: {len(plan.database_changes)}",
            f"- File changes: {len(plan.file_changes)}",
            (
                f"- Source operation: "
                f"{record.source_operation_id or 'None'}"
            ),
            (
                "- Validated inverse data: "
                + (
                    "Stored"
                    if any(item.inverse_json for item in record.items)
                    else "None"
                )
            ),
            "",
            "## Summary",
            "",
            plan.summary,
            "",
            "## Intended database changes",
            "",
        ]
        lines.extend(
            ProtectionService._report_items(plan.database_changes)
        )
        lines.extend(("", "## Intended file changes", ""))
        lines.extend(
            ProtectionService._report_items(plan.file_changes)
        )
        lines.extend(("", "## Warnings", ""))
        lines.extend(
            [f"- {warning}" for warning in plan.warnings]
            or ["- None recorded."]
        )
        lines.extend(
            (
                "",
                "## Outcome evidence",
                "",
                f"- Backup identity: {record.backup_identity or 'None'}",
                f"- Error: {record.error_summary or 'None'}",
                f"- Rollback: {record.rollback_outcome or 'Not required'}",
                "",
                (
                    "This report describes recorded intent and outcome. "
                    "A planned or approved status does not mean the changes "
                    "were applied."
                ),
                "",
            )
        )
        return "\n".join(lines)

    @staticmethod
    def _report_items(
        items: tuple[ChangePlanItem, ...],
    ) -> list[str]:
        if not items:
            return ["- None."]
        return [
            (
                f"{index}. **{item.action}** — {item.description}"
                + (
                    f" (Book: {item.book_title or item.book_id})"
                    if item.book_id is not None
                    else ""
                )
            )
            for index, item in enumerate(items, start=1)
        ]

    @staticmethod
    def _operation_from_rows(
        row: object,
        item_rows: tuple[object, ...] | list[object],
    ) -> OperationRecord:
        plan_value = json.loads(str(row["plan_json"]))
        if not isinstance(plan_value, dict):
            raise ValueError("Stored operation plan is invalid.")
        plan = ChangePlan.from_dict(plan_value)
        confirmation = None
        confirmation_json = str(row["confirmation_json"])
        if confirmation_json:
            value = json.loads(confirmation_json)
            if not isinstance(value, dict):
                raise ValueError("Stored plan confirmation is invalid.")
            confirmation = PlanConfirmation(
                plan_token=str(value["plan_token"]),
                approved=bool(value["approved"]),
                confirmer=str(value["confirmer"]),
                confirmation_text=str(
                    value.get("confirmation_text", "")
                ),
                confirmed_at=str(value["confirmed_at"]),
            )
        items = tuple(
            OperationItemRecord(
                sequence=int(item["item_sequence"]),
                target=ChangeTarget(str(item["target"])),
                action=str(item["action"]),
                description=str(item["description"]),
                book_id=(
                    int(item["book_id"])
                    if item["book_id"] is not None
                    else None
                ),
                book_title=str(item["book_title"]),
                before_summary=str(item["before_summary"]),
                after_summary=str(item["after_summary"]),
                reversible=bool(item["reversible"]),
                status=str(item["status"]),
                error_summary=str(item["error_summary"]),
                inverse_json=str(item["inverse_json"]),
            )
            for item in item_rows
        )
        return OperationRecord(
            operation_id=int(row["id"]),
            operation_token=str(row["operation_token"]),
            plan=plan,
            status=OperationStatus(str(row["status"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            started_at=str(row["started_at"]),
            finished_at=str(row["finished_at"]),
            confirmation=confirmation,
            backup_identity=str(row["backup_identity"]),
            error_summary=str(row["error_summary"]),
            rollback_outcome=str(row["rollback_outcome"]),
            source_operation_id=(
                int(row["source_operation_id"])
                if row["source_operation_id"] is not None
                else None
            ),
            items=items,
        )

    def _owned_backup_payload(
        self,
        backup_path: str | Path,
    ) -> dict[str, object]:
        """Return exact identity for one regular Twano backup/manifest pair."""
        path = Path(backup_path)
        if not path.is_absolute():
            raise PlanValidationError("Backup path must be absolute.")
        if (
            path.is_symlink()
            or not path.is_file()
            or not path.name.startswith(BACKUP_FILE_PREFIX)
            or not path.name.endswith(BACKUP_FILE_SUFFIX)
        ):
            raise PlanValidationError(
                "The selected file is not a regular Twano-owned backup."
            )
        resolved_path = path.resolve()
        if resolved_path == self.live_database_path:
            raise PlanValidationError(
                "The live catalogue cannot be used as its own backup."
            )
        manifest_path = self.manifest_path(path)
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise PlanValidationError(
                "The backup has no regular Twano verification manifest."
            )
        manifest, error = self._read_manifest(path)
        if manifest is None:
            raise PlanValidationError(error)
        sha256 = str(manifest.get("sha256", "")).lower()
        size_bytes = self._manifest_integer(manifest, "size_bytes")
        backup_id = str(manifest.get("backup_id", "")).strip()
        created_at = str(manifest.get("created_at", "")).strip()
        if (
            manifest.get("backup_file") != path.name
            or size_bytes is None
            or size_bytes != path.stat().st_size
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
            or not backup_id
        ):
            raise PlanValidationError(
                "The backup verification manifest is incomplete or stale."
            )
        self._aware_timestamp(created_at, "backup creation")
        return {
            "schema_version": 1,
            "backup_id": backup_id,
            "backup_path": str(resolved_path),
            "manifest_path": str(manifest_path.resolve()),
            "created_at": created_at,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "mtime_ns": path.stat().st_mtime_ns,
        }

    def _validated_restore_payload(
        self,
        plan: ChangePlan,
    ) -> dict[str, object]:
        item = self._single_executable_item(
            plan,
            expected_action="restore_catalogue",
        )
        try:
            payload = json.loads(item.after_summary)
        except (TypeError, json.JSONDecodeError) as error:
            raise PlanValidationError(
                "The Restore plan has invalid backup identity."
            ) from error
        required = {
            "schema_version",
            "backup_id",
            "backup_path",
            "manifest_path",
            "created_at",
            "size_bytes",
            "sha256",
            "mtime_ns",
        }
        if not isinstance(payload, dict) or set(payload) != required:
            raise PlanValidationError(
                "The Restore plan has invalid backup identity."
            )
        try:
            schema_version = int(payload["schema_version"])
            size_bytes = int(payload["size_bytes"])
            mtime_ns = int(payload["mtime_ns"])
        except (TypeError, ValueError) as error:
            raise PlanValidationError(
                "The Restore plan has invalid backup identity."
            ) from error
        if schema_version != 1 or size_bytes <= 0 or mtime_ns <= 0:
            raise PlanValidationError(
                "The Restore plan has invalid backup identity."
            )
        return {
            "schema_version": 1,
            "backup_id": str(payload["backup_id"]),
            "backup_path": str(payload["backup_path"]),
            "manifest_path": str(payload["manifest_path"]),
            "created_at": str(payload["created_at"]),
            "size_bytes": size_bytes,
            "sha256": str(payload["sha256"]).lower(),
            "mtime_ns": mtime_ns,
        }

    def _restore_basis(self, payload: dict[str, object]) -> str:
        current = self._owned_backup_payload(
            str(payload["backup_path"])
        )
        if current != payload:
            raise PlanValidationError(
                "The selected backup changed after the Restore preview."
            )
        encoded = json.dumps(
            current,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "database-restore-v1:" + hashlib.sha256(
            encoded.encode("utf-8")
        ).hexdigest()

    def _validated_retention_payloads(
        self,
        plan: ChangePlan,
    ) -> tuple[dict[str, object], ...]:
        if (
            plan.operation_type != "backup_retention_cleanup"
            or plan.database_changes
            or not plan.file_changes
            or any(
                item.action != "delete_verified_backup"
                for item in plan.file_changes
            )
        ):
            raise PlanValidationError(
                "The cleanup plan does not match its allowlisted shape."
            )
        payloads: list[dict[str, object]] = []
        required = {
            "schema_version",
            "backup_id",
            "backup_path",
            "manifest_path",
            "created_at",
            "size_bytes",
            "sha256",
            "mtime_ns",
            "retention_days",
            "cutoff_at",
            "backup_folder",
        }
        for item in plan.file_changes:
            try:
                value = json.loads(item.after_summary)
            except (TypeError, json.JSONDecodeError) as error:
                raise PlanValidationError(
                    "The cleanup plan contains invalid backup identity."
                ) from error
            if not isinstance(value, dict) or set(value) != required:
                raise PlanValidationError(
                    "The cleanup plan contains invalid backup identity."
                )
            try:
                payload = {
                    "schema_version": int(value["schema_version"]),
                    "backup_id": str(value["backup_id"]),
                    "backup_path": str(value["backup_path"]),
                    "manifest_path": str(value["manifest_path"]),
                    "created_at": str(value["created_at"]),
                    "size_bytes": int(value["size_bytes"]),
                    "sha256": str(value["sha256"]).lower(),
                    "mtime_ns": int(value["mtime_ns"]),
                    "retention_days": int(value["retention_days"]),
                    "cutoff_at": str(value["cutoff_at"]),
                    "backup_folder": str(value["backup_folder"]),
                }
            except (TypeError, ValueError) as error:
                raise PlanValidationError(
                    "The cleanup plan contains invalid backup identity."
                ) from error
            if (
                payload["schema_version"] != 1
                or payload["retention_days"] <= 0
                or payload["size_bytes"] <= 0
            ):
                raise PlanValidationError(
                    "The cleanup plan contains invalid backup identity."
                )
            payloads.append(payload)
        return tuple(payloads)

    def _retention_basis(
        self,
        payloads: tuple[dict[str, object], ...],
    ) -> str:
        if not payloads:
            raise PlanValidationError(
                "The cleanup plan has no verified backup candidates."
            )
        current_payloads: list[dict[str, object]] = []
        seen_paths: set[Path] = set()
        for payload in payloads:
            path = Path(str(payload["backup_path"]))
            folder = Path(str(payload["backup_folder"]))
            if (
                path.parent.resolve() != folder.resolve()
                or path.resolve() in seen_paths
            ):
                raise PlanValidationError(
                    "The cleanup plan contains an unsafe or repeated path."
                )
            seen_paths.add(path.resolve())
            created_at = self._aware_timestamp(
                str(payload["created_at"]),
                "backup creation",
            )
            cutoff = self._aware_timestamp(
                str(payload["cutoff_at"]),
                "retention cutoff",
            )
            if created_at >= cutoff:
                raise PlanValidationError(
                    "The cleanup plan contains a backup that is not expired."
                )
            current = self._owned_backup_payload(path)
            expected_base = {
                key: payload[key]
                for key in (
                    "schema_version",
                    "backup_id",
                    "backup_path",
                    "manifest_path",
                    "created_at",
                    "size_bytes",
                    "sha256",
                    "mtime_ns",
                )
            }
            if current != expected_base:
                raise PlanValidationError(
                    f"{path.name} changed after the cleanup review."
                )
            current_payloads.append(payload)
        encoded = json.dumps(
            sorted(
                current_payloads,
                key=lambda value: str(value["backup_path"]),
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        return "backup-retention-v1:" + hashlib.sha256(
            encoded.encode("utf-8")
        ).hexdigest()

    def _persist_completed_restore_operation(
        self,
        record: OperationRecord,
        recovery: BackupRecord,
        *,
        started_at: str,
        finished_at: str,
    ) -> OperationRecord:
        if record.confirmation is None:
            raise PlanValidationError(
                "The Restore approval evidence is missing."
            )
        inverse_json = json.dumps(
            {
                "schema_version": 1,
                "action": "restore_database",
                "backup_path": str(recovery.path),
                "manifest_path": str(recovery.manifest_path),
                "size_bytes": recovery.size_bytes,
                "sha256": recovery.sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        operation = {
            "operation_token": record.operation_token,
            "plan_token": record.plan.plan_token,
            "operation_type": record.plan.operation_type,
            "title": record.plan.title,
            "summary": record.plan.summary,
            "initiator": record.plan.initiator,
            "component": record.plan.component,
            "created_at": record.created_at,
            "updated_at": finished_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": OperationStatus.APPLIED.value,
            "risk": record.plan.risk.value,
            "reversibility": record.plan.reversibility.value,
            "confirmation_requirement": (
                record.plan.confirmation_requirement.value
            ),
            "affected_book_count": record.plan.affected_book_count,
            "database_change_count": len(
                record.plan.database_changes
            ),
            "file_change_count": len(record.plan.file_changes),
            "warnings_json": json.dumps(list(record.plan.warnings)),
            "plan_json": json.dumps(
                record.plan.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            ),
            "confirmation_json": json.dumps(
                record.confirmation.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            ),
            "backup_identity": str(recovery.path),
            "rollback_outcome": (
                "Not required; the selected catalogue was restored and the "
                "verified pre-restore safety copy was retained."
            ),
            "source_operation_id": None,
        }
        items = [
            {
                "item_sequence": sequence,
                **item.to_dict(),
                "status": OperationStatus.APPLIED.value,
                "inverse_json": (
                    inverse_json
                    if item.action == "restore_catalogue"
                    else ""
                ),
            }
            for sequence, item in enumerate(
                record.plan.database_changes + record.plan.file_changes,
                start=1,
            )
        ]
        operation_id = self.database.create_protection_operation(
            operation,
            items,
        )
        return self.get_operation(operation_id)

    @staticmethod
    def _restore_quarantined_files(
        moved: list[tuple[Path, Path]],
    ) -> str | None:
        errors: list[str] = []
        for original, quarantined in reversed(moved):
            if not quarantined.exists():
                continue
            try:
                if original.exists():
                    raise FileExistsError(
                        f"Original path already exists: {original}"
                    )
                os.replace(quarantined, original)
            except Exception as error:
                errors.append(f"{original}: {error}")
        return "; ".join(errors) if errors else None

    def _copy_file(
        self,
        source: Path,
        destination: Path,
        *,
        is_cancelled: CancellationCheck | None,
        on_progress: ProgressCallback | None,
        progress_start: int,
        progress_end: int,
    ) -> None:
        if destination.exists():
            raise FileExistsError(
                f"Private Restore file already exists: {destination}"
            )
        total = max(1, source.stat().st_size)
        copied = 0
        try:
            with source.open("rb") as input_stream, destination.open(
                "xb"
            ) as output_stream:
                while True:
                    self._check_cancelled(is_cancelled)
                    block = input_stream.read(1024 * 1024)
                    if not block:
                        break
                    output_stream.write(block)
                    copied += len(block)
                    percent = progress_start + int(
                        (copied / total)
                        * (progress_end - progress_start)
                    )
                    self._progress(
                        on_progress,
                        percent,
                        "Preparing a private catalogue copy...",
                    )
                output_stream.flush()
                os.fsync(output_stream.fileno())
            self._check_cancelled(is_cancelled)
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    @staticmethod
    def _aware_timestamp(value: str, label: str) -> datetime:
        try:
            timestamp = datetime.fromisoformat(str(value))
        except ValueError as error:
            raise PlanValidationError(
                f"The {label} time is invalid."
            ) from error
        if timestamp.tzinfo is None:
            raise PlanValidationError(
                f"The {label} time has no timezone."
            )
        return timestamp.astimezone(timezone.utc)

    @staticmethod
    def _display_timestamp(value: str) -> str:
        try:
            timestamp = datetime.fromisoformat(str(value))
            if timestamp.tzinfo is not None:
                timestamp = timestamp.astimezone()
            return timestamp.strftime("%d %b %Y at %H:%M")
        except ValueError:
            return "an unknown time"

    @staticmethod
    def _single_executable_item(
        plan: ChangePlan,
        *,
        expected_action: str,
    ) -> ChangePlanItem:
        if (
            len(plan.database_changes) != 1
            or plan.file_changes
            or plan.database_changes[0].action != expected_action
        ):
            raise PlanValidationError(
                "The executable plan does not match its allowlisted shape."
            )
        return plan.database_changes[0]

    def _collection_create_basis(self, collection_name: str) -> str:
        cleaned_name = " ".join(str(collection_name).split())
        if not cleaned_name:
            raise PlanValidationError(
                "The collection plan has no exact collection name."
            )
        row = self.database.get_collection_by_name(cleaned_name)
        state = {
            "schema_version": 1,
            "collection_name": cleaned_name.casefold(),
            "state": "absent" if row is None else "present",
            "collection_id": int(row["id"]) if row is not None else None,
        }
        payload = json.dumps(
            state,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "collection-create-v1:" + hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    def _metadata_update_basis(
        self,
        book_id: int,
        *,
        destination: Path | None = None,
    ) -> str:
        """Bind a metadata plan to the exact current catalogue record."""
        row = self.database.get_book_by_id(int(book_id))
        if row is None:
            raise PlanValidationError(
                "The selected book is no longer in the catalogue."
            )
        fields = (
            "title",
            "author",
            "isbn",
            "publisher",
            "language",
            "published_date",
            "series",
            "series_number",
            "series_group",
            "series_group_number",
            "description",
            "cover_path",
            "provider_rating",
            "rating_count",
            "rating_source",
            "metadata_status",
            "review_required",
        )
        payload = {
            "book_id": int(book_id),
            "file_path": str(row["file_path"]),
            "source_exists": Path(str(row["file_path"])).is_file(),
            "destination_path": (
                str(destination) if destination is not None else ""
            ),
            "destination_exists": (
                destination.exists() if destination is not None else False
            ),
            "values": {field: row[field] for field in fields},
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "metadata-update-v2:" + hashlib.sha256(encoded).hexdigest()

    def _validated_metadata_payload(
        self,
        plan: ChangePlan,
    ) -> tuple[int, dict[str, object], tuple[str, str] | None]:
        """Return allowlisted values from one exact metadata plan."""
        if (
            plan.operation_type != "metadata_update"
            or len(plan.database_changes) != 1
            or len(plan.file_changes) > 1
        ):
            raise PlanValidationError(
                "The metadata plan does not match its allowlisted shape."
            )
        item = plan.database_changes[0]
        if item.action != "update_book_metadata" or item.book_id is None:
            raise PlanValidationError(
                "The metadata plan has no exact book update."
            )
        try:
            raw = json.loads(item.after_summary)
        except (json.JSONDecodeError, TypeError) as error:
            raise PlanValidationError(
                "The metadata plan values are invalid."
            ) from error
        if not isinstance(raw, dict) or (not raw and not plan.file_changes):
            raise PlanValidationError(
                "The metadata plan has no reviewed fields."
            )
        allowed = {
            "title",
            "author",
            "isbn",
            "publisher",
            "language",
            "published_date",
            "series",
            "series_number",
            "series_group",
            "series_group_number",
            "description",
            "cover_path",
            "provider_rating",
            "rating_count",
            "rating_source",
        }
        if set(raw) - allowed:
            raise PlanValidationError(
                "The metadata plan contains unsupported fields."
            )
        move: tuple[str, str] | None = None
        if plan.file_changes:
            file_item = plan.file_changes[0]
            if (
                file_item.action != "move_book_file"
                or file_item.book_id != item.book_id
            ):
                raise PlanValidationError(
                    "The metadata plan has no exact ebook move."
                )
            row = self.database.get_book_by_id(int(item.book_id))
            if row is None:
                raise PlanValidationError(
                    "The selected book is no longer in the catalogue."
                )
            source = Path(file_item.before_summary)
            destination = Path(file_item.after_summary)
            root = self._organized_destination_root(row)
            if (
                not source.is_absolute()
                or not destination.is_absolute()
                or source.resolve() != Path(str(row["file_path"])).resolve()
            ):
                raise PlanValidationError(
                    "The metadata plan has an invalid source path."
                )
            try:
                destination.resolve().relative_to(root)
            except ValueError as error:
                raise PlanValidationError(
                    "The organised path would leave the configured "
                    "destination."
                ) from error
            move = (str(source.resolve()), str(destination.resolve()))
        return int(item.book_id), dict(raw), move

    def _validated_collection_inverse(
        self,
        source: OperationRecord,
    ) -> dict[str, object]:
        if (
            source.status != OperationStatus.APPLIED
            or source.plan.operation_type != "collection_create"
            or source.plan.reversibility != Reversibility.FULL
            or len(source.items) != 1
        ):
            raise PlanValidationError(
                "This operation has no available full Undo."
            )
        inverse_json = source.items[0].inverse_json
        try:
            inverse = json.loads(inverse_json)
        except (TypeError, json.JSONDecodeError) as error:
            raise PlanValidationError(
                "Stored inverse data is missing or invalid."
            ) from error
        if not isinstance(inverse, dict):
            raise PlanValidationError(
                "Stored inverse data is missing or invalid."
            )
        required_keys = {
            "schema_version",
            "action",
            "collection_id",
            "collection_name",
        }
        if set(inverse) != required_keys:
            raise PlanValidationError(
                "Stored inverse data does not match its schema."
            )
        try:
            collection_id = int(inverse["collection_id"])
        except (TypeError, ValueError) as error:
            raise PlanValidationError(
                "Stored inverse collection identity is invalid."
            ) from error
        collection_name = " ".join(
            str(inverse["collection_name"]).split()
        )
        try:
            schema_version = int(inverse["schema_version"])
        except (TypeError, ValueError) as error:
            raise PlanValidationError(
                "Stored inverse data does not match its schema."
            ) from error
        if (
            schema_version != 1
            or str(inverse["action"]) != "delete_collection"
            or collection_id <= 0
            or not collection_name
        ):
            raise PlanValidationError(
                "Stored inverse data does not match its schema."
            )
        return {
            "schema_version": 1,
            "action": "delete_collection",
            "collection_id": collection_id,
            "collection_name": collection_name,
        }

    def _collection_undo_basis(
        self,
        source: OperationRecord,
        inverse: dict[str, object],
    ) -> str:
        if source.status != OperationStatus.APPLIED:
            raise PlanValidationError(
                "The source operation is no longer applied."
            )
        collection_id = int(inverse["collection_id"])
        collection_name = str(inverse["collection_name"])
        row = self.database.get_collection_by_id(collection_id)
        if (
            row is None
            or str(row["name"]) != collection_name
            or int(row["book_count"]) != 0
        ):
            raise PlanValidationError(
                "Undo is stale because the created collection changed."
            )
        state = {
            "schema_version": 1,
            "source_operation_id": source.operation_id,
            "source_operation_token": source.operation_token,
            "collection_id": collection_id,
            "collection_name": collection_name,
            "book_count": 0,
            "source_status": source.status.value,
        }
        payload = json.dumps(
            state,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "collection-undo-v1:" + hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    def create_verified_backup(
        self,
        policy: BackupPolicy,
        *,
        is_cancelled: CancellationCheck | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> BackupRecord:
        """Create an online backup and publish it only after verification."""
        self._check_cancelled(is_cancelled)
        policy.folder.mkdir(parents=True, exist_ok=True)
        if not policy.folder.is_dir():
            raise NotADirectoryError(
                f"Backup location is not a folder: {policy.folder}"
            )

        backup_id = uuid4().hex
        created_at = datetime.now(timezone.utc)
        filename = (
            f"{BACKUP_FILE_PREFIX}"
            f"{created_at.strftime('%Y%m%d-%H%M%S')}-"
            f"{backup_id[:8]}{BACKUP_FILE_SUFFIX}"
        )
        final_path = policy.folder / filename
        manifest_path = self.manifest_path(final_path)
        partial_path = policy.folder / f".{filename}.{backup_id}.partial"
        partial_manifest = policy.folder / (
            f".{filename}.{backup_id}.manifest.partial"
        )
        audit_plan = ChangePlan(
            operation_type="database_backup",
            title="Create a verified catalogue backup",
            summary=(
                "Copy the open catalogue through SQLite's online backup "
                "API, verify database integrity, and publish SHA256 "
                "evidence."
            ),
            component="protection_centre",
            initiator="user",
            affected_book_count=0,
            risk=OperationRisk.LOW,
            reversibility=Reversibility.NOT_APPLICABLE,
            confirmation_requirement=ConfirmationRequirement.NONE,
            basis_token="verified-backup-workflow-v1",
            file_changes=(
                ChangePlanItem(
                    target=ChangeTarget.FILE,
                    action="create_verified_backup",
                    description=(
                        "Create a new Twano-owned SQLite backup and sidecar "
                        "manifest without overwriting an existing file."
                    ),
                    after_summary=str(final_path),
                    reversible=False,
                ),
            ),
            warnings=(
                "This creates backup artifacts only; it does not change "
                "the live catalogue or ebook files.",
            ),
        )
        audit_record = self.record_change_plan(audit_plan)
        started_at = datetime.now(timezone.utc).isoformat()
        self.database.transition_protection_operation(
            audit_record.operation_id,
            expected_statuses=(OperationStatus.PLANNED.value,),
            new_status=OperationStatus.APPLYING.value,
            updated_at=started_at,
            started_at=started_at,
            item_status=OperationStatus.APPLYING.value,
        )

        def database_progress(completed: int, total: int) -> None:
            percent = 5 + int((completed / max(1, total)) * 65)
            self._progress(
                on_progress,
                percent,
                "Copying a consistent snapshot of the live catalogue…",
            )

        published = False
        try:
            self._progress(
                on_progress,
                2,
                "Preparing a private backup file…",
            )
            self.database.backup_database(
                partial_path,
                is_cancelled=is_cancelled,
                on_progress=database_progress,
            )
            self._check_cancelled(is_cancelled)
            self._progress(
                on_progress,
                74,
                "Checking SQLite database integrity…",
            )
            self.database.verify_database_backup(
                partial_path,
                is_cancelled=is_cancelled,
            )
            self._check_cancelled(is_cancelled)
            sha256 = self._sha256(
                partial_path,
                is_cancelled=is_cancelled,
                on_progress=on_progress,
                progress_start=78,
                progress_end=94,
            )
            size_bytes = partial_path.stat().st_size
            manifest = {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "backup_id": backup_id,
                "backup_file": final_path.name,
                "created_at": created_at.isoformat(),
                "source_database": str(self.live_database_path),
                "size_bytes": size_bytes,
                "sha256": sha256,
                "application_version": APP_VERSION,
                "sqlite_integrity_check": "ok",
                "verification_completed_at": (
                    datetime.now(timezone.utc).isoformat()
                ),
                "retention_days_at_creation": policy.retention_days,
            }
            partial_manifest.write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self._check_cancelled(is_cancelled)
            os.replace(partial_path, final_path)
            os.replace(partial_manifest, manifest_path)
            finished_at = datetime.now(timezone.utc).isoformat()
            self.database.transition_protection_operation(
                audit_record.operation_id,
                expected_statuses=(OperationStatus.APPLYING.value,),
                new_status=OperationStatus.APPLIED.value,
                updated_at=finished_at,
                finished_at=finished_at,
                backup_identity=str(final_path),
                rollback_outcome="Not required; backup creation succeeded.",
                item_status=OperationStatus.APPLIED.value,
            )
            published = True
            self._progress(
                on_progress,
                100,
                "Verified backup created.",
            )
            return BackupRecord(
                path=final_path,
                manifest_path=manifest_path,
                created_at=created_at.isoformat(),
                size_bytes=size_bytes,
                status=BackupStatus.VERIFIED,
                sha256=sha256,
                message="SQLite integrity and SHA256 were verified.",
            )
        except (DatabaseBackupCancelled, BackupCancelled) as error:
            finished_at = datetime.now(timezone.utc).isoformat()
            self.database.transition_protection_operation(
                audit_record.operation_id,
                expected_statuses=(OperationStatus.APPLYING.value,),
                new_status=OperationStatus.CANCELLED.value,
                updated_at=finished_at,
                finished_at=finished_at,
                error_summary="Cancelled before publication.",
                rollback_outcome=(
                    "Partial and unpublished backup artifacts removed."
                ),
                item_status=OperationStatus.CANCELLED.value,
            )
            raise BackupCancelled(str(error)) from error
        except Exception as error:
            finished_at = datetime.now(timezone.utc).isoformat()
            self.database.transition_protection_operation(
                audit_record.operation_id,
                expected_statuses=(OperationStatus.APPLYING.value,),
                new_status=OperationStatus.FAILED.value,
                updated_at=finished_at,
                finished_at=finished_at,
                error_summary=str(error),
                rollback_outcome=(
                    "Partial and unpublished backup artifacts removed."
                ),
                item_status=OperationStatus.FAILED.value,
            )
            raise
        finally:
            partial_path.unlink(missing_ok=True)
            partial_manifest.unlink(missing_ok=True)
            if not published:
                final_path.unlink(missing_ok=True)
                manifest_path.unlink(missing_ok=True)

    def list_backups(self, policy: BackupPolicy) -> tuple[BackupRecord, ...]:
        """List Twano-owned final backups without expensive full hashing."""
        if not policy.folder.is_dir():
            return ()
        records = [
            self.inspect_backup(path, verify_contents=False)
            for path in policy.folder.glob(
                f"{BACKUP_FILE_PREFIX}*{BACKUP_FILE_SUFFIX}"
            )
            if path.is_file()
        ]
        records.sort(
            key=lambda record: (record.created_at, record.path.name),
            reverse=True,
        )
        return tuple(records)

    def verify_backup(
        self,
        backup_path: str | Path,
        *,
        is_cancelled: CancellationCheck | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> BackupRecord:
        """Perform SQLite integrity and manifest checksum verification."""
        path = Path(backup_path)
        self._check_cancelled(is_cancelled)
        self._progress(
            on_progress,
            8,
            "Checking SQLite database integrity…",
        )
        try:
            self.database.verify_database_backup(
                path,
                is_cancelled=is_cancelled,
            )
        except DatabaseBackupCancelled as error:
            raise BackupCancelled(str(error)) from error
        except (InvalidDatabaseBackup, FileNotFoundError) as error:
            return self._record_for_failure(
                path,
                BackupStatus.INVALID
                if path.exists()
                else BackupStatus.MISSING,
                str(error),
            )
        self._check_cancelled(is_cancelled)
        manifest, manifest_error = self._read_manifest(path)
        if manifest is None:
            self._progress(
                on_progress,
                100,
                "Database is readable but has no valid Twano manifest.",
            )
            return self._record_for_failure(
                path,
                BackupStatus.UNVERIFIED,
                manifest_error,
            )
        sha256 = self._sha256(
            path,
            is_cancelled=is_cancelled,
            on_progress=on_progress,
            progress_start=15,
            progress_end=96,
        )
        expected_sha256 = str(manifest.get("sha256", ""))
        expected_size = self._manifest_integer(manifest, "size_bytes")
        size_bytes = path.stat().st_size
        if (
            not expected_sha256
            or expected_size is None
            or manifest.get("backup_file") != path.name
        ):
            return self._record_from_manifest(
                path,
                manifest,
                BackupStatus.UNVERIFIED,
                "The verification manifest is incomplete.",
                sha256=sha256,
            )
        if expected_size != size_bytes or expected_sha256 != sha256:
            return self._record_from_manifest(
                path,
                manifest,
                BackupStatus.MODIFIED,
                "The backup no longer matches its verified manifest.",
                sha256=sha256,
            )
        self._progress(on_progress, 100, "Backup verification passed.")
        return self._record_from_manifest(
            path,
            manifest,
            BackupStatus.VERIFIED,
            "SQLite integrity and SHA256 match the manifest.",
            sha256=sha256,
        )

    def inspect_backup(
        self,
        backup_path: str | Path,
        *,
        verify_contents: bool = False,
    ) -> BackupRecord:
        """Inspect inexpensive evidence, or request full verification."""
        path = Path(backup_path)
        if verify_contents:
            return self.verify_backup(path)
        if not path.is_file():
            return self._record_for_failure(
                path,
                BackupStatus.MISSING,
                "The backup file is missing.",
            )
        manifest, manifest_error = self._read_manifest(path)
        if manifest is None:
            return self._record_for_failure(
                path,
                BackupStatus.UNVERIFIED,
                manifest_error,
            )
        expected_size = self._manifest_integer(manifest, "size_bytes")
        if (
            expected_size is None
            or not str(manifest.get("sha256", ""))
            or manifest.get("backup_file") != path.name
        ):
            return self._record_from_manifest(
                path,
                manifest,
                BackupStatus.UNVERIFIED,
                "The verification manifest is incomplete.",
            )
        if path.stat().st_size != expected_size:
            return self._record_from_manifest(
                path,
                manifest,
                BackupStatus.MODIFIED,
                "The backup size no longer matches its manifest.",
            )
        return self._record_from_manifest(
            path,
            manifest,
            BackupStatus.VERIFIED,
            "Verified when created; use Verify Backup to recheck it.",
        )

    @staticmethod
    def manifest_path(backup_path: str | Path) -> Path:
        path = Path(backup_path)
        return Path(f"{path}{MANIFEST_SUFFIX}")

    def _record_for_failure(
        self,
        path: Path,
        status: BackupStatus,
        message: str,
    ) -> BackupRecord:
        size_bytes = path.stat().st_size if path.is_file() else 0
        created_at = (
            datetime.fromtimestamp(
                path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()
            if path.is_file()
            else ""
        )
        return BackupRecord(
            path=path,
            manifest_path=self.manifest_path(path),
            created_at=created_at,
            size_bytes=size_bytes,
            status=status,
            message=message,
        )

    def _record_from_manifest(
        self,
        path: Path,
        manifest: dict[str, object],
        status: BackupStatus,
        message: str,
        *,
        sha256: str = "",
    ) -> BackupRecord:
        size_bytes = path.stat().st_size if path.is_file() else 0
        return BackupRecord(
            path=path,
            manifest_path=self.manifest_path(path),
            created_at=str(manifest.get("created_at", "")),
            size_bytes=size_bytes,
            status=status,
            sha256=sha256 or str(manifest.get("sha256", "")),
            message=message,
        )

    def _read_manifest(
        self,
        backup_path: Path,
    ) -> tuple[dict[str, object] | None, str]:
        manifest_path = self.manifest_path(backup_path)
        if not manifest_path.is_file():
            return None, "No Twano verification manifest was found."
        try:
            value = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            return None, f"The verification manifest is invalid: {error}"
        if not isinstance(value, dict):
            return None, "The verification manifest is invalid."
        if value.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            return None, "The verification manifest version is unsupported."
        return value, ""

    @staticmethod
    def _manifest_integer(
        manifest: dict[str, object],
        key: str,
    ) -> int | None:
        try:
            return int(manifest[key])
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _check_cancelled(
        is_cancelled: CancellationCheck | None,
    ) -> None:
        if is_cancelled is not None and is_cancelled():
            raise BackupCancelled("Backup operation cancelled.")

    @staticmethod
    def _progress(
        callback: ProgressCallback | None,
        percent: int,
        message: str,
    ) -> None:
        if callback is not None:
            callback(max(0, min(100, percent)), message)

    def _sha256(
        self,
        path: Path,
        *,
        is_cancelled: CancellationCheck | None,
        on_progress: ProgressCallback | None,
        progress_start: int,
        progress_end: int,
    ) -> str:
        digest = hashlib.sha256()
        size_bytes = max(1, path.stat().st_size)
        processed = 0
        with path.open("rb") as stream:
            while True:
                self._check_cancelled(is_cancelled)
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
                processed += len(block)
                fraction = processed / size_bytes
                percent = progress_start + int(
                    fraction * (progress_end - progress_start)
                )
                self._progress(
                    on_progress,
                    percent,
                    "Calculating SHA256 verification evidence…",
                )
        self._check_cancelled(is_cancelled)
        return digest.hexdigest()

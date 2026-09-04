"""SQLite database management for Twano's eBook Manager."""

import json
import logging
import os
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import get_ident
from typing import Iterator

from core.scanner import BookFile


logger = logging.getLogger(__name__)

APP_DATA_FOLDER = Path(
    os.getenv(
        "TWANO_DATA_FOLDER",
        str(
            Path(os.getenv("LOCALAPPDATA", str(Path.home())))
            / "Twano"
        ),
    )
).expanduser()
DEFAULT_DATABASE_PATH = APP_DATA_FOLDER / "library.db"


class DatabaseBackupCancelled(RuntimeError):
    """Raised when a caller cancels an online SQLite backup."""


class InvalidDatabaseBackup(RuntimeError):
    """Raised when SQLite integrity verification fails."""


class DatabaseManager:
    """Manage the application's SQLite database."""

    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialise_database()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Open a database connection and close it safely."""
        thread_id = get_ident()
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        logger.debug(
            "SQLite connection opened path=%s thread=%s",
            self.database_path,
            thread_id,
        )

        try:
            yield connection
            connection.commit()
            logger.debug(
                "SQLite transaction committed path=%s thread=%s",
                self.database_path,
                thread_id,
            )
        except Exception:
            connection.rollback()
            logger.exception(
                "SQLite transaction rolled back path=%s thread=%s",
                self.database_path,
                thread_id,
            )
            raise
        finally:
            connection.close()
            logger.debug(
                "SQLite connection closed path=%s thread=%s",
                self.database_path,
                thread_id,
            )

    def backup_database(
        self,
        destination: str | Path,
        *,
        is_cancelled: Callable[[], bool] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Create one consistent online backup without sharing connections."""
        destination_path = Path(destination)
        source_path = self.database_path.resolve()
        if destination_path.resolve() == source_path:
            raise ValueError(
                "The backup destination cannot be the live database."
            )
        if destination_path.exists():
            raise FileExistsError(
                f"Backup destination already exists: {destination_path}"
            )
        if not destination_path.parent.is_dir():
            raise FileNotFoundError(
                f"Backup folder does not exist: {destination_path.parent}"
            )
        if is_cancelled is not None and is_cancelled():
            raise DatabaseBackupCancelled("Backup cancelled.")

        source = sqlite3.connect(source_path)
        target: sqlite3.Connection | None = None

        def report_progress(
            _status: int,
            remaining_pages: int,
            total_pages: int,
        ) -> None:
            if is_cancelled is not None and is_cancelled():
                raise DatabaseBackupCancelled("Backup cancelled.")
            if on_progress is not None:
                completed_pages = max(0, total_pages - remaining_pages)
                on_progress(completed_pages, max(1, total_pages))

        try:
            target = sqlite3.connect(destination_path)
            source.backup(
                target,
                pages=64,
                progress=report_progress,
            )
            if is_cancelled is not None and is_cancelled():
                raise DatabaseBackupCancelled("Backup cancelled.")
            target.commit()
        except Exception:
            if target is not None:
                target.close()
                target = None
            destination_path.unlink(missing_ok=True)
            raise
        finally:
            if target is not None:
                target.close()
            source.close()
        return destination_path

    @staticmethod
    def verify_database_backup(
        backup_path: str | Path,
        *,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> None:
        """Raise if a database file does not pass SQLite integrity checks."""
        path = Path(backup_path)
        if not path.is_file():
            raise FileNotFoundError(f"Backup file not found: {path}")
        if is_cancelled is not None and is_cancelled():
            raise DatabaseBackupCancelled("Backup verification cancelled.")
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{path.resolve().as_uri()}?mode=ro",
                uri=True,
            )
            if is_cancelled is not None:
                connection.set_progress_handler(
                    lambda: 1 if is_cancelled() else 0,
                    1000,
                )
            rows = connection.execute("PRAGMA integrity_check").fetchall()
        except sqlite3.DatabaseError as error:
            if is_cancelled is not None and is_cancelled():
                raise DatabaseBackupCancelled(
                    "Backup verification cancelled."
                ) from error
            raise InvalidDatabaseBackup(
                f"SQLite could not read the backup: {error}"
            ) from error
        finally:
            if connection is not None:
                connection.close()
        results = tuple(str(row[0]) for row in rows)
        if results != ("ok",):
            detail = "; ".join(results) or "No integrity result was returned."
            raise InvalidDatabaseBackup(
                f"SQLite integrity check failed: {detail}"
            )

    def initialise_database(self) -> None:
        """Create or update the application database tables."""
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS libraries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    folder_path TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    last_scanned_at TEXT
                );

                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    library_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL UNIQUE,
                    file_name TEXT NOT NULL,
                    title TEXT,
                    author TEXT,
                    isbn TEXT,
                    file_format TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_modified_at TEXT,
                    discovered_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    metadata_status TEXT NOT NULL DEFAULT 'pending',
                    review_required INTEGER NOT NULL DEFAULT 0,
                    is_missing INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (library_id)
                        REFERENCES libraries(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_books_library_id
                    ON books(library_id);

                CREATE INDEX IF NOT EXISTS idx_books_title
                    ON books(title);

                CREATE INDEX IF NOT EXISTS idx_books_isbn
                    ON books(isbn);

                CREATE INDEX IF NOT EXISTS idx_books_metadata_status
                    ON books(metadata_status);

                CREATE TABLE IF NOT EXISTS collections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS book_collections (
                    book_id INTEGER NOT NULL,
                    collection_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (book_id, collection_id),
                    FOREIGN KEY (book_id)
                        REFERENCES books(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (collection_id)
                        REFERENCES collections(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_book_collections_collection
                    ON book_collections(collection_id);
                """
            )

            self._add_column_if_missing(
                connection,
                "books",
                "publisher",
                "TEXT",
            )
            self._add_column_if_missing(
                connection,
                "books",
                "language",
                "TEXT",
            )
            self._add_column_if_missing(
                connection,
                "books",
                "published_date",
                "TEXT",
            )
            self._add_column_if_missing(
                connection,
                "books",
                "series",
                "TEXT",
            )
            self._add_column_if_missing(
                connection,
                "books",
                "description",
                "TEXT",
            )
            self._add_column_if_missing(
                connection,
                "books",
                "cover_path",
                "TEXT",
            )
            self._add_column_if_missing(
                connection,
                "books",
                "series_number",
                "REAL",
            )
            self._add_column_if_missing(
                connection,
                "books",
                "series_group",
                "TEXT",
            )
            self._add_column_if_missing(
                connection,
                "books",
                "series_group_number",
                "REAL",
            )
            self._add_column_if_missing(
                connection,
                "books",
                "provider_rating",
                "REAL NOT NULL DEFAULT 0",
            )
            self._add_column_if_missing(
                connection, "books", "rating_count", "INTEGER NOT NULL DEFAULT 0"
            )
            self._add_column_if_missing(
                connection, "books", "rating_source", "TEXT NOT NULL DEFAULT ''"
            )
            self._add_column_if_missing(
                connection,
                "books",
                "metadata_workflow_complete",
                "INTEGER NOT NULL DEFAULT 0",
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_books_provider_rating "
                "ON books(provider_rating)"
            )
            self._add_column_if_missing(
                connection,
                "books",
                "file_fingerprint",
                "TEXT",
            )
            self._add_column_if_missing(
                connection,
                "libraries",
                "display_name",
                "TEXT",
            )
            self._add_column_if_missing(
                connection,
                "libraries",
                "is_enabled",
                "INTEGER NOT NULL DEFAULT 1",
            )
            self._add_column_if_missing(
                connection,
                "libraries",
                "include_subfolders",
                "INTEGER NOT NULL DEFAULT 1",
            )
            self._add_column_if_missing(
                connection,
                "libraries",
                "include_patterns",
                "TEXT NOT NULL DEFAULT '[]'",
            )
            self._add_column_if_missing(
                connection,
                "libraries",
                "exclude_patterns",
                "TEXT NOT NULL DEFAULT '[]'",
            )
            self._add_column_if_missing(
                connection,
                "libraries",
                "archived_at",
                "TEXT",
            )
            self._add_column_if_missing(
                connection,
                "libraries",
                "connection_status",
                "TEXT NOT NULL DEFAULT 'not_tested'",
            )
            self._add_column_if_missing(
                connection,
                "libraries",
                "connection_message",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._add_column_if_missing(
                connection,
                "libraries",
                "connection_tested_at",
                "TEXT",
            )
            for column_name, column_type in (
                ("last_scan_status", "TEXT NOT NULL DEFAULT ''"),
                ("last_scan_duration_ms", "INTEGER"),
                ("last_scan_discovered_count", "INTEGER NOT NULL DEFAULT 0"),
                ("last_scan_new_count", "INTEGER NOT NULL DEFAULT 0"),
                ("last_scan_changed_count", "INTEGER NOT NULL DEFAULT 0"),
                ("last_scan_missing_count", "INTEGER NOT NULL DEFAULT 0"),
                ("last_scan_unreadable_count", "INTEGER NOT NULL DEFAULT 0"),
                ("last_scan_skipped_count", "INTEGER NOT NULL DEFAULT 0"),
                ("last_scan_error", "TEXT NOT NULL DEFAULT ''"),
            ):
                self._add_column_if_missing(
                    connection,
                    "libraries",
                    column_name,
                    column_type,
                )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS scan_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    library_id INTEGER NOT NULL,
                    protection_operation_id INTEGER,
                    scan_token TEXT NOT NULL UNIQUE,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    discovered_count INTEGER NOT NULL DEFAULT 0,
                    new_count INTEGER NOT NULL DEFAULT 0,
                    changed_count INTEGER NOT NULL DEFAULT 0,
                    missing_count INTEGER NOT NULL DEFAULT 0,
                    unchanged_count INTEGER NOT NULL DEFAULT 0,
                    unreadable_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    applied_new_count INTEGER NOT NULL DEFAULT 0,
                    applied_changed_count INTEGER NOT NULL DEFAULT 0,
                    applied_missing_count INTEGER NOT NULL DEFAULT 0,
                    refreshed_count INTEGER NOT NULL DEFAULT 0,
                    safely_skipped_count INTEGER NOT NULL DEFAULT 0,
                    error_summary TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (library_id)
                        REFERENCES libraries(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (protection_operation_id)
                        REFERENCES protection_operations(id)
                        ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_scan_history_library_finished
                    ON scan_history(library_id, finished_at DESC, id DESC);

                CREATE TABLE IF NOT EXISTS protection_operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_token TEXT NOT NULL UNIQUE,
                    plan_token TEXT NOT NULL UNIQUE,
                    operation_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    initiator TEXT NOT NULL,
                    component TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    reversibility TEXT NOT NULL,
                    confirmation_requirement TEXT NOT NULL,
                    affected_book_count INTEGER NOT NULL DEFAULT 0,
                    database_change_count INTEGER NOT NULL DEFAULT 0,
                    file_change_count INTEGER NOT NULL DEFAULT 0,
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    plan_json TEXT NOT NULL,
                    confirmation_json TEXT NOT NULL DEFAULT '',
                    backup_identity TEXT NOT NULL DEFAULT '',
                    error_summary TEXT NOT NULL DEFAULT '',
                    rollback_outcome TEXT NOT NULL DEFAULT '',
                    source_operation_id INTEGER,
                    FOREIGN KEY (source_operation_id)
                        REFERENCES protection_operations(id)
                        ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS protection_operation_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_id INTEGER NOT NULL,
                    item_sequence INTEGER NOT NULL,
                    target TEXT NOT NULL,
                    action TEXT NOT NULL,
                    description TEXT NOT NULL,
                    book_id INTEGER,
                    book_title TEXT NOT NULL DEFAULT '',
                    before_summary TEXT NOT NULL DEFAULT '',
                    after_summary TEXT NOT NULL DEFAULT '',
                    reversible INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'planned',
                    error_summary TEXT NOT NULL DEFAULT '',
                    inverse_json TEXT NOT NULL DEFAULT '',
                    UNIQUE (operation_id, item_sequence),
                    FOREIGN KEY (operation_id)
                        REFERENCES protection_operations(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_protection_operations_updated
                    ON protection_operations(updated_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_protection_operations_status
                    ON protection_operations(status, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_protection_items_operation
                    ON protection_operation_items(
                        operation_id,
                        item_sequence
                    );

                CREATE INDEX IF NOT EXISTS idx_books_author
                    ON books(author);

                CREATE INDEX IF NOT EXISTS idx_books_series
                    ON books(series, series_number);

                CREATE INDEX IF NOT EXISTS idx_books_series_group
                    ON books(series_group, series, series_number);

                CREATE INDEX IF NOT EXISTS idx_books_discovered_at
                    ON books(discovered_at);

                CREATE INDEX IF NOT EXISTS idx_books_file_modified_at
                    ON books(file_modified_at);

                CREATE INDEX IF NOT EXISTS idx_books_file_format
                    ON books(file_format);

                CREATE TABLE IF NOT EXISTS duplicate_exceptions (
                    group_key TEXT PRIMARY KEY,
                    reason TEXT NOT NULL DEFAULT 'intentional editions',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS quarantine_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    original_path TEXT NOT NULL,
                    quarantine_path TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    restored_at TEXT,
                    FOREIGN KEY (book_id)
                        REFERENCES books(id)
                        ON DELETE CASCADE
                );
                """
            )
            self._add_column_if_missing(
                connection,
                "scan_history",
                "protection_operation_id",
                (
                    "INTEGER REFERENCES protection_operations(id) "
                    "ON DELETE SET NULL"
                ),
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_scan_history_protection_operation
                ON scan_history(protection_operation_id)
                """
            )

    def create_protection_operation(
        self,
        operation: Mapping[str, object],
        items: Sequence[Mapping[str, object]],
    ) -> int:
        """Persist one detached plan and all items atomically."""
        with self.connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO protection_operations (
                    operation_token,
                    plan_token,
                    operation_type,
                    title,
                    summary,
                    initiator,
                    component,
                    created_at,
                    updated_at,
                    started_at,
                    finished_at,
                    status,
                    risk,
                    reversibility,
                    confirmation_requirement,
                    affected_book_count,
                    database_change_count,
                    file_change_count,
                    warnings_json,
                    plan_json,
                    confirmation_json,
                    backup_identity,
                    error_summary,
                    rollback_outcome,
                    source_operation_id
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    operation["operation_token"],
                    operation["plan_token"],
                    operation["operation_type"],
                    operation["title"],
                    operation["summary"],
                    operation["initiator"],
                    operation["component"],
                    operation["created_at"],
                    operation["updated_at"],
                    operation.get("started_at", ""),
                    operation.get("finished_at", ""),
                    operation["status"],
                    operation["risk"],
                    operation["reversibility"],
                    operation["confirmation_requirement"],
                    operation["affected_book_count"],
                    operation["database_change_count"],
                    operation["file_change_count"],
                    operation["warnings_json"],
                    operation["plan_json"],
                    operation.get("confirmation_json", ""),
                    operation.get("backup_identity", ""),
                    operation.get("error_summary", ""),
                    operation.get("rollback_outcome", ""),
                    operation.get("source_operation_id"),
                ),
            )
            operation_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO protection_operation_items (
                    operation_id,
                    item_sequence,
                    target,
                    action,
                    description,
                    book_id,
                    book_title,
                    before_summary,
                    after_summary,
                    reversible,
                    status,
                    error_summary,
                    inverse_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        operation_id,
                        item["item_sequence"],
                        item["target"],
                        item["action"],
                        item["description"],
                        item.get("book_id"),
                        item.get("book_title", ""),
                        item.get("before_summary", ""),
                        item.get("after_summary", ""),
                        int(bool(item.get("reversible", False))),
                        item.get("status", "planned"),
                        item.get("error_summary", ""),
                        item.get("inverse_json", ""),
                    )
                    for item in items
                ],
            )
        return operation_id

    def transition_protection_operation(
        self,
        operation_id: int,
        *,
        expected_statuses: Sequence[str],
        new_status: str,
        updated_at: str,
        started_at: str | None = None,
        finished_at: str | None = None,
        confirmation_json: str | None = None,
        backup_identity: str | None = None,
        error_summary: str | None = None,
        rollback_outcome: str | None = None,
        item_status: str | None = None,
    ) -> None:
        """Apply one validated audit transition with optimistic status."""
        expected = tuple(str(status) for status in expected_statuses)
        if not expected:
            raise ValueError("Expected operation statuses cannot be empty.")
        with self.connection() as connection:
            current = connection.execute(
                """
                SELECT
                    status,
                    started_at,
                    finished_at,
                    confirmation_json,
                    backup_identity,
                    error_summary,
                    rollback_outcome
                FROM protection_operations
                WHERE id = ?
                """,
                (int(operation_id),),
            ).fetchone()
            if current is None:
                raise KeyError(
                    f"Protection operation not found: {operation_id}"
                )
            if str(current["status"]) not in expected:
                raise ValueError(
                    "Operation status changed before this transition."
                )
            connection.execute(
                """
                UPDATE protection_operations
                SET
                    status = ?,
                    updated_at = ?,
                    started_at = ?,
                    finished_at = ?,
                    confirmation_json = ?,
                    backup_identity = ?,
                    error_summary = ?,
                    rollback_outcome = ?
                WHERE id = ?
                """,
                (
                    new_status,
                    updated_at,
                    (
                        str(current["started_at"])
                        if started_at is None
                        else started_at
                    ),
                    (
                        str(current["finished_at"])
                        if finished_at is None
                        else finished_at
                    ),
                    (
                        str(current["confirmation_json"])
                        if confirmation_json is None
                        else confirmation_json
                    ),
                    (
                        str(current["backup_identity"])
                        if backup_identity is None
                        else backup_identity
                    ),
                    (
                        str(current["error_summary"])
                        if error_summary is None
                        else error_summary
                    ),
                    (
                        str(current["rollback_outcome"])
                        if rollback_outcome is None
                        else rollback_outcome
                    ),
                    int(operation_id),
                ),
            )
            if item_status is not None:
                connection.execute(
                    """
                    UPDATE protection_operation_items
                    SET status = ?, error_summary = ?
                    WHERE operation_id = ?
                    """,
                    (
                        item_status,
                        error_summary or "",
                        int(operation_id),
                    ),
                )

    def apply_collection_create_operation(
        self,
        operation_id: int,
        *,
        collection_name: str,
        backup_identity: str,
        updated_at: str,
    ) -> int:
        """Create one collection and persist its inverse in one transaction."""
        cleaned_name = " ".join(str(collection_name).split())
        if not cleaned_name:
            raise ValueError("Collection name cannot be empty.")
        with self.connection() as connection:
            operation = connection.execute(
                """
                SELECT status, operation_type
                FROM protection_operations
                WHERE id = ?
                """,
                (int(operation_id),),
            ).fetchone()
            if operation is None:
                raise KeyError(
                    f"Protection operation not found: {operation_id}"
                )
            if (
                str(operation["status"]) != "approved"
                or str(operation["operation_type"]) != "collection_create"
            ):
                raise ValueError(
                    "Only an approved collection-create operation can run."
                )
            existing = connection.execute(
                """
                SELECT id
                FROM collections
                WHERE name = ? COLLATE NOCASE
                """,
                (cleaned_name,),
            ).fetchone()
            if existing is not None:
                raise ValueError(
                    "The collection changed after preview; create a fresh "
                    "plan."
                )

            connection.execute(
                """
                UPDATE protection_operations
                SET status = 'applying', updated_at = ?, started_at = ?,
                    backup_identity = ?, error_summary = '',
                    rollback_outcome = ''
                WHERE id = ?
                """,
                (
                    updated_at,
                    updated_at,
                    backup_identity,
                    int(operation_id),
                ),
            )
            cursor = connection.execute(
                """
                INSERT INTO collections (name, created_at)
                VALUES (?, ?)
                """,
                (cleaned_name, updated_at),
            )
            collection_id = int(cursor.lastrowid)
            inverse_json = json.dumps(
                {
                    "schema_version": 1,
                    "action": "delete_collection",
                    "collection_id": collection_id,
                    "collection_name": cleaned_name,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            item_cursor = connection.execute(
                """
                UPDATE protection_operation_items
                SET status = 'applied', error_summary = '',
                    inverse_json = ?
                WHERE operation_id = ?
                  AND target = 'database'
                  AND action = 'create_collection'
                  AND reversible = 1
                """,
                (inverse_json, int(operation_id)),
            )
            if item_cursor.rowcount != 1:
                raise RuntimeError(
                    "The executable collection plan was not exact."
                )
            connection.execute(
                """
                UPDATE protection_operations
                SET status = 'applied', updated_at = ?, finished_at = ?,
                    rollback_outcome = ?
                WHERE id = ?
                """,
                (
                    updated_at,
                    updated_at,
                    (
                        "Not required; the protected transaction committed "
                        "atomically."
                    ),
                    int(operation_id),
                ),
            )
        return collection_id

    def apply_metadata_update_operation(
        self,
        operation_id: int,
        *,
        book_id: int,
        values: Mapping[str, object],
        source_path: str | None = None,
        destination_path: str | None = None,
        organized_root: str | None = None,
        metadata_workflow_complete: bool = False,
        backup_identity: str,
        updated_at: str,
    ) -> None:
        """Apply one reviewed metadata record and audit it atomically."""
        allowed_fields = (
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
        unknown = set(values) - set(allowed_fields)
        if unknown:
            raise ValueError(
                "Unsupported metadata fields: " + ", ".join(sorted(unknown))
            )
        if bool(source_path) != bool(destination_path):
            raise ValueError("The organised file move is incomplete.")
        if not values and not destination_path:
            raise ValueError("No reviewed metadata or file move was selected.")

        with self.connection() as connection:
            operation = connection.execute(
                """
                SELECT status, operation_type
                FROM protection_operations
                WHERE id = ?
                """,
                (int(operation_id),),
            ).fetchone()
            if operation is None:
                raise KeyError(
                    f"Protection operation not found: {operation_id}"
                )
            if (
                str(operation["status"]) != "approved"
                or str(operation["operation_type"]) != "metadata_update"
            ):
                raise ValueError(
                    "Only an approved metadata update can run."
                )

            book = connection.execute(
                """
                SELECT
                    id, title, author, isbn, publisher, language,
                    published_date, series, series_number,
                    series_group, series_group_number, description,
                    cover_path, provider_rating, rating_count, rating_source,
                    metadata_status, review_required,
                    metadata_workflow_complete,
                    file_path, file_name, library_id
                FROM books
                WHERE id = ?
                """,
                (int(book_id),),
            ).fetchone()
            if book is None:
                raise ValueError(f"Unknown book ID: {book_id}")
            inverse = {
                "schema_version": 1,
                "action": "restore_book_metadata",
                "book_id": int(book_id),
                "values": {
                    field: book[field]
                    for field in allowed_fields
                    if field in values
                },
                "file_path": str(book["file_path"]),
                "file_name": str(book["file_name"]),
            }

            connection.execute(
                """
                UPDATE protection_operations
                SET status = 'applying', updated_at = ?, started_at = ?,
                    backup_identity = ?, error_summary = '',
                    rollback_outcome = ''
                WHERE id = ?
                """,
                (
                    updated_at,
                    updated_at,
                    backup_identity,
                    int(operation_id),
                ),
            )
            update_values = dict(values)
            if destination_path:
                update_values["file_path"] = destination_path
                update_values["file_name"] = Path(destination_path).name
            if organized_root:
                # The book's watched-source link must follow it whenever an
                # organise/delete move takes it outside the folder that
                # link currently points to. Otherwise a future scan of the
                # original folder would find the file gone and wrongly
                # report it missing.
                resolved_root = str(Path(organized_root).resolve())
                current_library = connection.execute(
                    """
                    SELECT folder_path FROM libraries WHERE id = ?
                    """,
                    (int(book["library_id"]),),
                ).fetchone()
                current_root = (
                    str(current_library["folder_path"])
                    if current_library is not None
                    else ""
                )
                if os.path.normcase(current_root) != os.path.normcase(
                    resolved_root
                ):
                    timestamp = self._utc_timestamp()
                    library_row = connection.execute(
                        """
                        SELECT id FROM libraries
                        WHERE folder_path = ? COLLATE NOCASE
                        """,
                        (resolved_root,),
                    ).fetchone()
                    if library_row is None:
                        library_cursor = connection.execute(
                            """
                            INSERT INTO libraries (
                                folder_path, created_at, last_scanned_at
                            )
                            VALUES (?, ?, ?)
                            """,
                            (resolved_root, timestamp, timestamp),
                        )
                        update_values["library_id"] = int(
                            library_cursor.lastrowid
                        )
                    else:
                        update_values["library_id"] = int(
                            library_row["id"]
                        )
            assignments = ", ".join(
                f"{field} = ?" for field in update_values
            )
            parameters = [update_values[field] for field in update_values]
            parameters.extend(
                [
                    "external",
                    0,
                    int(bool(metadata_workflow_complete)),
                    int(book_id),
                ]
            )
            connection.execute(
                f"""
                UPDATE books
                SET {assignments},
                    metadata_status = ?,
                    review_required = ?,
                    metadata_workflow_complete = ?
                WHERE id = ?
                """,
                parameters,
            )
            item_cursor = connection.execute(
                """
                UPDATE protection_operation_items
                SET status = 'applied', error_summary = '',
                    inverse_json = ?
                WHERE operation_id = ?
                  AND target = 'database'
                  AND action = 'update_book_metadata'
                """,
                (
                    json.dumps(
                        inverse,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    int(operation_id),
                ),
            )
            if item_cursor.rowcount != 1:
                raise RuntimeError(
                    "The executable metadata plan was not exact."
                )
            if destination_path:
                file_inverse = {
                    "schema_version": 1,
                    "action": "move_book_file",
                    "book_id": int(book_id),
                    "from": destination_path,
                    "to": source_path,
                }
                file_cursor = connection.execute(
                    """
                    UPDATE protection_operation_items
                    SET status = 'applied', error_summary = '',
                        inverse_json = ?
                    WHERE operation_id = ?
                      AND target = 'file'
                      AND action = 'move_book_file'
                    """,
                    (
                        json.dumps(
                            file_inverse,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        int(operation_id),
                    ),
                )
                if file_cursor.rowcount != 1:
                    raise RuntimeError(
                        "The executable ebook move was not exact."
                    )
            connection.execute(
                """
                UPDATE protection_operations
                SET status = 'applied', updated_at = ?, finished_at = ?,
                    rollback_outcome = ?
                WHERE id = ?
                """,
                (
                    updated_at,
                    updated_at,
                    (
                        "Not required; the protected metadata transaction "
                        "committed atomically. The verified backup remains "
                        "available for Restore."
                    ),
                    int(operation_id),
                ),
            )

    def apply_collection_undo_operation(
        self,
        operation_id: int,
        *,
        source_operation_id: int,
        collection_id: int,
        collection_name: str,
        backup_identity: str,
        updated_at: str,
    ) -> None:
        """Remove one exact empty collection and audit Undo atomically."""
        with self.connection() as connection:
            undo = connection.execute(
                """
                SELECT status, operation_type, source_operation_id
                FROM protection_operations
                WHERE id = ?
                """,
                (int(operation_id),),
            ).fetchone()
            if undo is None:
                raise KeyError(
                    f"Protection operation not found: {operation_id}"
                )
            if (
                str(undo["status"]) != "approved"
                or str(undo["operation_type"])
                != "undo_collection_create"
                or int(undo["source_operation_id"] or 0)
                != int(source_operation_id)
            ):
                raise ValueError(
                    "Only the approved Undo for this source operation can "
                    "run."
                )
            source = connection.execute(
                """
                SELECT status, operation_type
                FROM protection_operations
                WHERE id = ?
                """,
                (int(source_operation_id),),
            ).fetchone()
            if (
                source is None
                or str(source["status"]) != "applied"
                or str(source["operation_type"]) != "collection_create"
            ):
                raise ValueError(
                    "The source operation is no longer available for Undo."
                )
            competing = connection.execute(
                """
                SELECT id
                FROM protection_operations
                WHERE source_operation_id = ?
                  AND id != ?
                  AND status IN ('planned', 'approved', 'applying', 'applied')
                LIMIT 1
                """,
                (int(source_operation_id), int(operation_id)),
            ).fetchone()
            if competing is not None:
                raise ValueError(
                    "Another active Undo already targets this operation."
                )
            collection = connection.execute(
                """
                SELECT id, name
                FROM collections
                WHERE id = ? AND name = ?
                """,
                (int(collection_id), str(collection_name)),
            ).fetchone()
            if collection is None:
                raise ValueError(
                    "The collection changed after Undo preview."
                )
            member = connection.execute(
                """
                SELECT 1
                FROM book_collections
                WHERE collection_id = ?
                LIMIT 1
                """,
                (int(collection_id),),
            ).fetchone()
            if member is not None:
                raise ValueError(
                    "Undo cannot remove a collection that now contains books."
                )

            connection.execute(
                """
                UPDATE protection_operations
                SET status = 'applying', updated_at = ?, started_at = ?,
                    backup_identity = ?, error_summary = '',
                    rollback_outcome = ''
                WHERE id = ?
                """,
                (
                    updated_at,
                    updated_at,
                    backup_identity,
                    int(operation_id),
                ),
            )
            deleted = connection.execute(
                """
                DELETE FROM collections
                WHERE id = ? AND name = ?
                """,
                (int(collection_id), str(collection_name)),
            )
            if deleted.rowcount != 1:
                raise RuntimeError("The Undo collection could not be removed.")
            item_cursor = connection.execute(
                """
                UPDATE protection_operation_items
                SET status = 'applied', error_summary = ''
                WHERE operation_id = ?
                  AND target = 'database'
                  AND action = 'delete_collection'
                """,
                (int(operation_id),),
            )
            if item_cursor.rowcount != 1:
                raise RuntimeError("The executable Undo plan was not exact.")
            connection.execute(
                """
                UPDATE protection_operation_items
                SET status = 'undone'
                WHERE operation_id = ?
                """,
                (int(source_operation_id),),
            )
            connection.execute(
                """
                UPDATE protection_operations
                SET status = 'undone', updated_at = ?
                WHERE id = ?
                """,
                (updated_at, int(source_operation_id)),
            )
            connection.execute(
                """
                UPDATE protection_operations
                SET status = 'applied', updated_at = ?, finished_at = ?,
                    rollback_outcome = ?
                WHERE id = ?
                """,
                (
                    updated_at,
                    updated_at,
                    (
                        "Not required; Undo committed atomically and the "
                        "source operation remains in history."
                    ),
                    int(operation_id),
                ),
            )

    def get_collection_by_name(self, name: str) -> sqlite3.Row | None:
        """Return one collection and membership count by casefolded name."""
        cleaned_name = " ".join(str(name).split())
        with self.connection() as connection:
            return connection.execute(
                """
                SELECT
                    collections.id,
                    collections.name,
                    COUNT(book_collections.book_id) AS book_count
                FROM collections
                LEFT JOIN book_collections
                    ON book_collections.collection_id = collections.id
                WHERE collections.name = ? COLLATE NOCASE
                GROUP BY collections.id, collections.name
                """,
                (cleaned_name,),
            ).fetchone()

    def get_collection_by_id(
        self,
        collection_id: int,
    ) -> sqlite3.Row | None:
        """Return one collection and membership count by persistent ID."""
        with self.connection() as connection:
            return connection.execute(
                """
                SELECT
                    collections.id,
                    collections.name,
                    COUNT(book_collections.book_id) AS book_count
                FROM collections
                LEFT JOIN book_collections
                    ON book_collections.collection_id = collections.id
                WHERE collections.id = ?
                GROUP BY collections.id, collections.name
                """,
                (int(collection_id),),
            ).fetchone()

    def get_active_undo_operation(
        self,
        source_operation_id: int,
    ) -> sqlite3.Row | None:
        """Return an Undo that still reserves one applied source operation."""
        with self.connection() as connection:
            return connection.execute(
                """
                SELECT *
                FROM protection_operations
                WHERE source_operation_id = ?
                  AND status IN ('planned', 'approved', 'applying', 'applied')
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(source_operation_id),),
            ).fetchone()

    def complete_embedded_backup_operation(
        self,
        backup_identity: str | Path,
        *,
        updated_at: str,
    ) -> int | None:
        """Finish the backup audit row embedded inside its own snapshot.

        Online backup captures the creation audit while it is still Applying.
        If that snapshot later becomes the live catalogue through Restore, the
        row is reconciled to the truthful completed outcome.
        """
        identity = str(Path(backup_identity))
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT protection_operations.id
                FROM protection_operations
                JOIN protection_operation_items
                  ON protection_operation_items.operation_id =
                     protection_operations.id
                WHERE protection_operations.operation_type =
                      'database_backup'
                  AND protection_operations.status = 'applying'
                  AND protection_operation_items.action =
                      'create_verified_backup'
                  AND protection_operation_items.after_summary = ?
                ORDER BY protection_operations.id DESC
                LIMIT 1
                """,
                (identity,),
            ).fetchone()
            if row is None:
                return None
            operation_id = int(row["id"])
            connection.execute(
                """
                UPDATE protection_operations
                SET status = 'applied', updated_at = ?, finished_at = ?,
                    backup_identity = ?, error_summary = '',
                    rollback_outcome = ?
                WHERE id = ? AND status = 'applying'
                """,
                (
                    updated_at,
                    updated_at,
                    identity,
                    (
                        "Not required; the verified backup was completed "
                        "before this snapshot was restored."
                    ),
                    operation_id,
                ),
            )
            connection.execute(
                """
                UPDATE protection_operation_items
                SET status = 'applied', error_summary = ''
                WHERE operation_id = ?
                """,
                (operation_id,),
            )
        return operation_id

    def list_protection_operations(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        """Return recent persistent operation headers."""
        if not 1 <= int(limit) <= 1000:
            raise ValueError("History limit must be between 1 and 1000.")
        if int(offset) < 0:
            raise ValueError("History offset cannot be negative.")
        with self.connection() as connection:
            return connection.execute(
                """
                SELECT *
                FROM protection_operations
                ORDER BY updated_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (int(limit), int(offset)),
            ).fetchall()

    def get_protection_operation(
        self,
        operation_id: int,
    ) -> tuple[sqlite3.Row, list[sqlite3.Row]] | None:
        """Return one operation and its ordered item evidence."""
        with self.connection() as connection:
            operation = connection.execute(
                """
                SELECT *
                FROM protection_operations
                WHERE id = ?
                """,
                (int(operation_id),),
            ).fetchone()
            if operation is None:
                return None
            items = connection.execute(
                """
                SELECT *
                FROM protection_operation_items
                WHERE operation_id = ?
                ORDER BY item_sequence, id
                """,
                (int(operation_id),),
            ).fetchall()
        return operation, items

    def get_protection_operation_by_plan_token(
        self,
        plan_token: str,
    ) -> tuple[sqlite3.Row, list[sqlite3.Row]] | None:
        """Return one persistent operation using its immutable plan token."""
        with self.connection() as connection:
            operation = connection.execute(
                """
                SELECT *
                FROM protection_operations
                WHERE plan_token = ?
                """,
                (str(plan_token),),
            ).fetchone()
            if operation is None:
                return None
            items = connection.execute(
                """
                SELECT *
                FROM protection_operation_items
                WHERE operation_id = ?
                ORDER BY item_sequence, id
                """,
                (int(operation["id"]),),
            ).fetchall()
        return operation, items

    @staticmethod
    def _add_column_if_missing(
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_type: str,
    ) -> None:
        """Add a column when upgrading an existing database."""
        columns = connection.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()

        existing_names = {
            str(column["name"])
            for column in columns
        }

        if column_name not in existing_names:
            connection.execute(
                f"""
                ALTER TABLE {table_name}
                ADD COLUMN {column_name} {column_type}
                """
            )

    def update_book_metadata(
        self,
        file_path: str | Path,
        *,
        title: str | None,
        author: str | None,
        isbn: str | None,
        publisher: str | None,
        language: str | None,
        published_date: str | None,
        metadata_status: str,
    ) -> None:
        """Save extracted metadata for a book."""
        resolved_path = str(Path(file_path).resolve())

        with self.connection() as connection:
            connection.execute(
                """
                UPDATE books
                SET
                    title = COALESCE(?, title),
                    author = COALESCE(?, author),
                    isbn = COALESCE(?, isbn),
                    publisher = COALESCE(?, publisher),
                    language = COALESCE(?, language),
                    published_date = COALESCE(?, published_date),
                    metadata_status = ?,
                    metadata_workflow_complete = -1
                WHERE file_path = ?
                """,
                (
                    title,
                    author,
                    isbn,
                    publisher,
                    language,
                    published_date,
                    metadata_status,
                    resolved_path,
                ),
            )

    def get_or_create_library(self, folder_path: str | Path) -> int:
        """Return the database ID for a library folder."""
        resolved_path = str(Path(folder_path).resolve())
        timestamp = self._utc_timestamp()

        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT id
                FROM libraries
                WHERE folder_path = ? COLLATE NOCASE
                """,
                (resolved_path,),
            ).fetchone()
            if row is None:
                cursor = connection.execute(
                    """
                    INSERT INTO libraries (
                        folder_path,
                        created_at,
                        last_scanned_at
                    )
                    VALUES (?, ?, ?)
                    """,
                    (resolved_path, timestamp, timestamp),
                )
                library_id = int(cursor.lastrowid)
            else:
                library_id = int(row["id"])
                connection.execute(
                    """
                    UPDATE libraries
                    SET
                        last_scanned_at = ?,
                        is_enabled = 1,
                        archived_at = NULL
                    WHERE id = ?
                    """,
                    (timestamp, library_id),
                )

        return library_id

    def relink_missing_book(
        self,
        book_id: int,
        *,
        file_path: str | Path,
        library_folder: str | Path,
    ) -> None:
        """Point a missing book at a file the user relocated outside Twano.

        Twano cannot detect a manual file move on its own; this is used
        only after independently finding a file that matches a book
        already flagged missing, so it also clears that flag.
        """
        library_id = self.get_or_create_library(library_folder)
        resolved_path = str(Path(file_path).resolve())
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE books
                SET file_path = ?, file_name = ?, library_id = ?,
                    is_missing = 0
                WHERE id = ?
                """,
                (
                    resolved_path,
                    Path(resolved_path).name,
                    library_id,
                    int(book_id),
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Unknown book ID: {book_id}")

    def save_library_source(
        self,
        folder_path: str | Path,
        *,
        display_name: str,
        include_subfolders: bool,
        include_patterns: str,
        exclude_patterns: str,
    ) -> sqlite3.Row:
        """Create or restore one watched source without touching its books."""
        resolved_path = str(Path(folder_path).resolve())
        timestamp = self._utc_timestamp()

        with self.connection() as connection:
            existing = connection.execute(
                """
                SELECT id
                FROM libraries
                WHERE folder_path = ? COLLATE NOCASE
                """,
                (resolved_path,),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO libraries (
                        folder_path,
                        display_name,
                        created_at,
                        is_enabled,
                        include_subfolders,
                        include_patterns,
                        exclude_patterns,
                        archived_at,
                        connection_status,
                        connection_message,
                        connection_tested_at
                    )
                    VALUES (?, ?, ?, 1, ?, ?, ?, NULL, 'not_tested', '', NULL)
                    """,
                    (
                        resolved_path,
                        display_name,
                        timestamp,
                        int(include_subfolders),
                        include_patterns,
                        exclude_patterns,
                    ),
                )
                source_id = int(cursor.lastrowid)
            else:
                source_id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE libraries
                    SET
                        display_name = ?,
                        is_enabled = 1,
                        include_subfolders = ?,
                        include_patterns = ?,
                        exclude_patterns = ?,
                        archived_at = NULL,
                        connection_status = 'not_tested',
                        connection_message = '',
                        connection_tested_at = NULL
                    WHERE id = ?
                    """,
                    (
                        display_name,
                        int(include_subfolders),
                        include_patterns,
                        exclude_patterns,
                        source_id,
                    ),
                )
            row = connection.execute(
                """
                SELECT *
                FROM libraries
                WHERE id = ?
                """,
                (source_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("The watched source could not be saved.")
        return row

    def list_library_sources(
        self,
        *,
        include_archived: bool = False,
    ) -> list[sqlite3.Row]:
        """Return detached watched-source rows."""
        query = """
            SELECT *
            FROM libraries
        """
        if not include_archived:
            query += " WHERE archived_at IS NULL"
        query += """
            ORDER BY
                COALESCE(NULLIF(display_name, ''), folder_path) COLLATE NOCASE,
                id
        """
        with self.connection() as connection:
            return list(connection.execute(query).fetchall())

    def get_library_source(
        self,
        source_id: int,
        *,
        include_archived: bool = False,
    ) -> sqlite3.Row | None:
        """Return one detached source row."""
        query = "SELECT * FROM libraries WHERE id = ?"
        if not include_archived:
            query += " AND archived_at IS NULL"
        with self.connection() as connection:
            return connection.execute(query, (source_id,)).fetchone()

    def update_library_source(
        self,
        source_id: int,
        *,
        display_name: str,
        include_subfolders: bool,
        include_patterns: str,
        exclude_patterns: str,
    ) -> sqlite3.Row:
        """Update editable source settings without relocating its books."""
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE libraries
                SET
                    display_name = ?,
                    include_subfolders = ?,
                    include_patterns = ?,
                    exclude_patterns = ?
                WHERE id = ?
                  AND archived_at IS NULL
                """,
                (
                    display_name,
                    int(include_subfolders),
                    include_patterns,
                    exclude_patterns,
                    source_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("The watched source is no longer available.")
            row = connection.execute(
                "SELECT * FROM libraries WHERE id = ?",
                (source_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("The watched source could not be updated.")
        return row

    def set_library_source_enabled(
        self,
        source_id: int,
        enabled: bool,
    ) -> sqlite3.Row:
        """Enable or disable watching without changing catalogue books."""
        connection_status = "not_tested" if enabled else "disabled"
        connection_message = (
            "" if enabled else "Watching is disabled for this source."
        )
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE libraries
                SET
                    is_enabled = ?,
                    connection_status = ?,
                    connection_message = ?,
                    connection_tested_at = NULL
                WHERE id = ?
                  AND archived_at IS NULL
                """,
                (
                    int(enabled),
                    connection_status,
                    connection_message,
                    source_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("The watched source is no longer available.")
            row = connection.execute(
                "SELECT * FROM libraries WHERE id = ?",
                (source_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("The watched source could not be updated.")
        return row

    def archive_library_source(self, source_id: int) -> None:
        """Remove a watch while deliberately retaining related book rows."""
        timestamp = self._utc_timestamp()
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE libraries
                SET
                    archived_at = ?,
                    is_enabled = 0,
                    connection_status = 'disabled',
                    connection_message = 'This source is no longer watched.',
                    connection_tested_at = NULL
                WHERE id = ?
                  AND archived_at IS NULL
                """,
                (timestamp, source_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("The watched source is no longer available.")

    def remove_library_source_and_books(self, source_id: int) -> int:
        """Atomically archive one watch and remove only its catalogue books."""
        with self.connection() as connection:
            source = connection.execute(
                """
                SELECT id
                FROM libraries
                WHERE id = ? AND archived_at IS NULL
                """,
                (int(source_id),),
            ).fetchone()
            if source is None:
                raise ValueError("The watched source is no longer available.")

            active_quarantine = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM quarantine_items
                INNER JOIN books
                    ON books.id = quarantine_items.book_id
                WHERE books.library_id = ?
                  AND quarantine_items.restored_at IS NULL
                """,
                (int(source_id),),
            ).fetchone()
            if active_quarantine and int(active_quarantine["total"]) > 0:
                raise ValueError(
                    "Restore this source's quarantined books before removing "
                    "the watched folder."
                )

            count_row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM books
                WHERE library_id = ?
                """,
                (int(source_id),),
            ).fetchone()
            book_count = int(count_row["total"]) if count_row else 0
            connection.execute(
                "DELETE FROM books WHERE library_id = ?",
                (int(source_id),),
            )
            cursor = connection.execute(
                """
                UPDATE libraries
                SET
                    archived_at = ?,
                    is_enabled = 0,
                    connection_status = 'disabled',
                    connection_message = 'This source is no longer watched.',
                    connection_tested_at = NULL
                WHERE id = ? AND archived_at IS NULL
                """,
                (self._utc_timestamp(), int(source_id)),
            )
            if cursor.rowcount != 1:
                raise ValueError("The watched source is no longer available.")
        return book_count

    def record_library_source_connection(
        self,
        source_id: int,
        *,
        status: str,
        message: str,
    ) -> sqlite3.Row:
        """Persist the latest read-only source connection-test result."""
        timestamp = self._utc_timestamp()
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE libraries
                SET
                    connection_status = ?,
                    connection_message = ?,
                    connection_tested_at = ?
                WHERE id = ?
                  AND archived_at IS NULL
                """,
                (status, message, timestamp, source_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("The watched source is no longer available.")
            row = connection.execute(
                "SELECT * FROM libraries WHERE id = ?",
                (source_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("The connection result could not be saved.")
        return row

    def count_library_source_books(self, source_id: int) -> int:
        """Return all catalogue books retained for one source."""
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM books
                WHERE library_id = ?
                """,
                (source_id,),
            ).fetchone()
        return int(row["total"]) if row else 0

    def get_library_source_book_snapshot(
        self,
        source_id: int,
    ) -> list[sqlite3.Row]:
        """Return detached file facts for non-mutating scan comparison."""
        with self.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT
                        id,
                        file_path,
                        file_name,
                        title,
                        file_format,
                        file_size,
                        file_modified_at,
                        file_fingerprint,
                        is_missing
                    FROM books
                    WHERE library_id = ?
                    ORDER BY file_path COLLATE NOCASE
                    """,
                    (source_id,),
                ).fetchall()
            )

    def apply_scan_preview(
        self,
        *,
        source_id: int,
        scan_token: str,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        preview_counts: Mapping[str, int],
        changes: Sequence[Mapping[str, object]],
        safely_skipped_count: int,
        error_summary: str = "",
        protection_operation_id: int | None = None,
        protection_basis_token: str = "",
        backup_identity: str = "",
    ) -> dict[str, int]:
        """Apply preview, scan history, and linked protection audit atomically."""
        applied = {
            "new": 0,
            "changed": 0,
            "missing": 0,
            "refreshed": 0,
            "safely_skipped": max(0, int(safely_skipped_count)),
        }
        timestamp = finished_at or self._utc_timestamp()

        with self.connection() as connection:
            duplicate = connection.execute(
                """
                SELECT id
                FROM scan_history
                WHERE scan_token = ?
                """,
                (scan_token,),
            ).fetchone()
            if duplicate is not None:
                raise ValueError(
                    "This preview has already been handled. Run Preview "
                    "Scan again before applying."
                )

            source = connection.execute(
                """
                SELECT id
                FROM libraries
                WHERE id = ?
                  AND archived_at IS NULL
                  AND is_enabled = 1
                """,
                (source_id,),
            ).fetchone()
            if source is None:
                raise ValueError(
                    "The watched source is no longer enabled or available."
                )
            if protection_operation_id is not None:
                self._validate_scan_protection_operation(
                    connection,
                    protection_operation_id,
                    protection_basis_token=protection_basis_token,
                )
                connection.execute(
                    """
                    UPDATE protection_operations
                    SET status = 'applying', updated_at = ?, started_at = ?,
                        backup_identity = ?, error_summary = '',
                        rollback_outcome = ''
                    WHERE id = ?
                    """,
                    (
                        timestamp,
                        timestamp,
                        backup_identity,
                        int(protection_operation_id),
                    ),
                )

            for change in changes:
                status = str(change["status"])
                if status == "new":
                    cursor = connection.execute(
                        """
                        INSERT INTO books (
                            library_id,
                            file_path,
                            file_name,
                            title,
                            author,
                            isbn,
                            publisher,
                            language,
                            published_date,
                            file_format,
                            file_size,
                            file_modified_at,
                            file_fingerprint,
                            discovered_at,
                            last_seen_at,
                            metadata_status,
                            is_missing
                        )
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0
                        )
                        ON CONFLICT(file_path) DO NOTHING
                        """,
                        (
                            source_id,
                            change["file_path"],
                            change["file_name"],
                            change["title"],
                            change.get("author"),
                            change.get("isbn"),
                            change.get("publisher"),
                            change.get("language"),
                            change.get("published_date"),
                            change["file_format"],
                            change["file_size"],
                            change["file_modified_at"],
                            change["file_fingerprint"],
                            timestamp,
                            timestamp,
                            change["metadata_status"],
                        ),
                    )
                    key = "new" if cursor.rowcount == 1 else "safely_skipped"
                    applied[key] += 1
                    continue

                if status == "changed":
                    metadata_status = change.get("metadata_status")
                    cursor = connection.execute(
                        """
                        UPDATE books
                        SET
                            file_name = ?,
                            title = COALESCE(?, title),
                            author = COALESCE(?, author),
                            isbn = COALESCE(?, isbn),
                            publisher = COALESCE(?, publisher),
                            language = COALESCE(?, language),
                            published_date = COALESCE(?, published_date),
                            file_format = ?,
                            file_size = ?,
                            file_modified_at = ?,
                            file_fingerprint = ?,
                            last_seen_at = ?,
                            metadata_status = CASE
                                WHEN ? IS NULL OR ? = 'unavailable'
                                THEN metadata_status
                                ELSE ?
                            END,
                            metadata_workflow_complete = -1,
                            is_missing = 0
                        WHERE id = ?
                          AND library_id = ?
                          AND file_path = ? COLLATE NOCASE
                          AND file_size = ?
                          AND COALESCE(file_modified_at, '') = ?
                          AND COALESCE(file_fingerprint, '') = ?
                          AND is_missing = ?
                        """,
                        (
                            change["file_name"],
                            change.get("title"),
                            change.get("author"),
                            change.get("isbn"),
                            change.get("publisher"),
                            change.get("language"),
                            change.get("published_date"),
                            change["file_format"],
                            change["file_size"],
                            change["file_modified_at"],
                            change["file_fingerprint"],
                            timestamp,
                            metadata_status,
                            metadata_status,
                            metadata_status,
                            change["existing_book_id"],
                            source_id,
                            change["file_path"],
                            change["expected_file_size"],
                            change["expected_modified_at"],
                            change["expected_fingerprint"],
                            int(bool(change["expected_is_missing"])),
                        ),
                    )
                    key = (
                        "changed"
                        if cursor.rowcount == 1
                        else "safely_skipped"
                    )
                    applied[key] += 1
                    continue

                if status == "missing":
                    cursor = connection.execute(
                        """
                        UPDATE books
                        SET is_missing = 1
                        WHERE id = ?
                          AND library_id = ?
                          AND file_path = ? COLLATE NOCASE
                          AND file_size = ?
                          AND COALESCE(file_modified_at, '') = ?
                          AND COALESCE(file_fingerprint, '') = ?
                          AND is_missing = 0
                        """,
                        (
                            change["existing_book_id"],
                            source_id,
                            change["file_path"],
                            change["expected_file_size"],
                            change["expected_modified_at"],
                            change["expected_fingerprint"],
                        ),
                    )
                    key = (
                        "missing"
                        if cursor.rowcount == 1
                        else "safely_skipped"
                    )
                    applied[key] += 1
                    continue

                if status == "unchanged":
                    cursor = connection.execute(
                        """
                        UPDATE books
                        SET
                            last_seen_at = ?,
                            file_fingerprint = ?
                        WHERE id = ?
                          AND library_id = ?
                          AND file_path = ? COLLATE NOCASE
                          AND file_size = ?
                          AND COALESCE(file_modified_at, '') = ?
                          AND COALESCE(file_fingerprint, '') = ?
                          AND is_missing = ?
                        """,
                        (
                            timestamp,
                            change["file_fingerprint"],
                            change["existing_book_id"],
                            source_id,
                            change["file_path"],
                            change["expected_file_size"],
                            change["expected_modified_at"],
                            change["expected_fingerprint"],
                            int(bool(change["expected_is_missing"])),
                        ),
                    )
                    key = (
                        "refreshed"
                        if cursor.rowcount == 1
                        else "safely_skipped"
                    )
                    applied[key] += 1

            connection.execute(
                """
                INSERT INTO scan_history (
                    library_id,
                    protection_operation_id,
                    scan_token,
                    started_at,
                    finished_at,
                    status,
                    duration_ms,
                    discovered_count,
                    new_count,
                    changed_count,
                    missing_count,
                    unchanged_count,
                    unreadable_count,
                    skipped_count,
                    applied_new_count,
                    applied_changed_count,
                    applied_missing_count,
                    refreshed_count,
                    safely_skipped_count,
                    error_summary
                )
                VALUES (
                    ?, ?, ?, ?, ?, 'applied', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    source_id,
                    protection_operation_id,
                    scan_token,
                    started_at,
                    timestamp,
                    max(0, int(duration_ms)),
                    int(preview_counts.get("discovered", 0)),
                    int(preview_counts.get("new", 0)),
                    int(preview_counts.get("changed", 0)),
                    int(preview_counts.get("missing", 0)),
                    int(preview_counts.get("unchanged", 0)),
                    int(preview_counts.get("unreadable", 0)),
                    int(preview_counts.get("skipped", 0)),
                    applied["new"],
                    applied["changed"],
                    applied["missing"],
                    applied["refreshed"],
                    applied["safely_skipped"],
                    error_summary,
                ),
            )
            connection.execute(
                """
                UPDATE libraries
                SET
                    last_scanned_at = ?,
                    last_scan_status = 'applied',
                    last_scan_duration_ms = ?,
                    last_scan_discovered_count = ?,
                    last_scan_new_count = ?,
                    last_scan_changed_count = ?,
                    last_scan_missing_count = ?,
                    last_scan_unreadable_count = ?,
                    last_scan_skipped_count = ?,
                    last_scan_error = ?
                WHERE id = ?
                """,
                (
                    timestamp,
                    max(0, int(duration_ms)),
                    int(preview_counts.get("discovered", 0)),
                    applied["new"],
                    applied["changed"],
                    applied["missing"],
                    int(preview_counts.get("unreadable", 0)),
                    (
                        int(preview_counts.get("skipped", 0))
                        + applied["safely_skipped"]
                    ),
                    error_summary,
                    source_id,
                ),
            )
            if protection_operation_id is not None:
                connection.execute(
                    """
                    UPDATE protection_operation_items
                    SET status = 'applied', error_summary = ''
                    WHERE operation_id = ?
                    """,
                    (int(protection_operation_id),),
                )
                connection.execute(
                    """
                    UPDATE protection_operations
                    SET status = 'applied', updated_at = ?, finished_at = ?,
                        rollback_outcome = ?
                    WHERE id = ?
                    """,
                    (
                        timestamp,
                        timestamp,
                        (
                            "Not required; catalogue, scan history, and "
                            "operation evidence committed atomically."
                        ),
                        int(protection_operation_id),
                    ),
                )

        return applied

    def record_scan_attempt(
        self,
        *,
        source_id: int,
        scan_token: str,
        started_at: str,
        finished_at: str,
        status: str,
        duration_ms: int,
        preview_counts: Mapping[str, int],
        safely_skipped_count: int = 0,
        error_summary: str = "",
        protection_operation_id: int | None = None,
        protection_basis_token: str = "",
        backup_identity: str = "",
    ) -> None:
        """Record a non-applied attempt and linked protection outcome."""
        if status not in {"cancelled", "failed"}:
            raise ValueError("Unsupported scan-attempt status.")
        with self.connection() as connection:
            if protection_operation_id is not None:
                self._validate_scan_protection_operation(
                    connection,
                    protection_operation_id,
                    protection_basis_token=protection_basis_token,
                )
            connection.execute(
                """
                INSERT INTO scan_history (
                    library_id,
                    protection_operation_id,
                    scan_token,
                    started_at,
                    finished_at,
                    status,
                    duration_ms,
                    discovered_count,
                    new_count,
                    changed_count,
                    missing_count,
                    unchanged_count,
                    unreadable_count,
                    skipped_count,
                    safely_skipped_count,
                    error_summary
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    protection_operation_id,
                    scan_token,
                    started_at,
                    finished_at,
                    status,
                    max(0, int(duration_ms)),
                    int(preview_counts.get("discovered", 0)),
                    int(preview_counts.get("new", 0)),
                    int(preview_counts.get("changed", 0)),
                    int(preview_counts.get("missing", 0)),
                    int(preview_counts.get("unchanged", 0)),
                    int(preview_counts.get("unreadable", 0)),
                    int(preview_counts.get("skipped", 0)),
                    max(0, int(safely_skipped_count)),
                    error_summary,
                ),
            )
            connection.execute(
                """
                UPDATE libraries
                SET
                    last_scan_status = ?,
                    last_scan_duration_ms = ?,
                    last_scan_discovered_count = ?,
                    last_scan_new_count = 0,
                    last_scan_changed_count = 0,
                    last_scan_missing_count = 0,
                    last_scan_unreadable_count = ?,
                    last_scan_skipped_count = ?,
                    last_scan_error = ?
                WHERE id = ?
                """,
                (
                    status,
                    max(0, int(duration_ms)),
                    int(preview_counts.get("discovered", 0)),
                    int(preview_counts.get("unreadable", 0)),
                    (
                        int(preview_counts.get("skipped", 0))
                        + max(0, int(safely_skipped_count))
                    ),
                    error_summary,
                    source_id,
                ),
            )
            if protection_operation_id is not None:
                connection.execute(
                    """
                    UPDATE protection_operation_items
                    SET status = ?, error_summary = ?
                    WHERE operation_id = ?
                    """,
                    (
                        status,
                        error_summary,
                        int(protection_operation_id),
                    ),
                )
                connection.execute(
                    """
                    UPDATE protection_operations
                    SET status = ?, updated_at = ?, finished_at = ?,
                        backup_identity = ?, error_summary = ?,
                        rollback_outcome = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        finished_at,
                        finished_at,
                        backup_identity,
                        error_summary,
                        (
                            "No catalogue mutation started."
                            if status == "cancelled"
                            else (
                                "The catalogue transaction did not commit; "
                                "no partial scan update remains."
                            )
                        ),
                        int(protection_operation_id),
                    ),
                )

    def scan_token_handled(self, scan_token: str) -> bool:
        """Return whether an immutable preview already has a terminal result."""
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM scan_history
                WHERE scan_token = ?
                LIMIT 1
                """,
                (str(scan_token),),
            ).fetchone()
        return row is not None

    @staticmethod
    def _validate_scan_protection_operation(
        connection: sqlite3.Connection,
        operation_id: int,
        *,
        protection_basis_token: str,
    ) -> None:
        operation = connection.execute(
            """
            SELECT status, operation_type, plan_json
            FROM protection_operations
            WHERE id = ?
            """,
            (int(operation_id),),
        ).fetchone()
        if operation is None:
            raise ValueError("The linked protection operation was not found.")
        if (
            str(operation["status"]) != "approved"
            or str(operation["operation_type"]) != "scan_apply"
        ):
            raise ValueError(
                "Only an approved Scan Apply operation can update the "
                "catalogue."
            )
        try:
            plan = json.loads(str(operation["plan_json"]))
        except (TypeError, ValueError) as error:
            raise ValueError(
                "The linked Scan Apply safety record is invalid."
            ) from error
        if (
            not protection_basis_token
            or str(plan.get("basis_token", ""))
            != str(protection_basis_token)
        ):
            raise ValueError(
                "The Scan Apply safety record no longer matches this preview."
            )

    def list_scan_history(
        self,
        source_id: int,
        *,
        limit: int = 20,
    ) -> list[sqlite3.Row]:
        """Return recent detached history for one watched source."""
        safe_limit = max(1, min(int(limit), 200))
        with self.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT *
                    FROM scan_history
                    WHERE library_id = ?
                    ORDER BY finished_at DESC, id DESC
                    LIMIT ?
                    """,
                    (source_id, safe_limit),
                ).fetchall()
            )

    def save_scan_results(
        self,
        library_folder: str | Path,
        books: list[BookFile],
    ) -> int:
        """Insert or update books discovered during a scan."""
        library_id = self.get_or_create_library(library_folder)
        timestamp = self._utc_timestamp()
        discovered_paths: set[str] = set()

        with self.connection() as connection:
            for book in books:
                file_path = str(book.path.resolve())
                discovered_paths.add(file_path)

                try:
                    modified_at = datetime.fromtimestamp(
                        book.path.stat().st_mtime,
                        tz=timezone.utc,
                    ).isoformat()
                except OSError:
                    modified_at = None

                connection.execute(
                    """
                    INSERT INTO books (
                        library_id,
                        file_path,
                        file_name,
                        title,
                        file_format,
                        file_size,
                        file_modified_at,
                        discovered_at,
                        last_seen_at,
                        metadata_status,
                        metadata_workflow_complete,
                        is_missing
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, 0)
                    ON CONFLICT(file_path) DO UPDATE SET
                        library_id = excluded.library_id,
                        file_name = excluded.file_name,
                        file_format = excluded.file_format,
                        file_size = excluded.file_size,
                        file_modified_at = excluded.file_modified_at,
                        last_seen_at = excluded.last_seen_at,
                        metadata_workflow_complete = CASE
                            WHEN books.file_size != excluded.file_size
                              OR COALESCE(books.file_modified_at, '')
                                 != COALESCE(excluded.file_modified_at, '')
                            THEN CASE
                                WHEN books.metadata_workflow_complete = 1
                                THEN -1
                                ELSE books.metadata_workflow_complete
                            END
                            ELSE books.metadata_workflow_complete
                        END,
                        is_missing = 0
                    """,
                    (
                        library_id,
                        file_path,
                        book.path.name,
                        book.name,
                        book.extension,
                        book.size_bytes,
                        modified_at,
                        timestamp,
                        timestamp,
                    ),
                )

            existing_rows = connection.execute(
                """
                SELECT id, file_path
                FROM books
                WHERE library_id = ?
                """,
                (library_id,),
            ).fetchall()

            missing_ids = [
                int(row["id"])
                for row in existing_rows
                if row["file_path"] not in discovered_paths
            ]

            if missing_ids:
                connection.executemany(
                    """
                    UPDATE books
                    SET is_missing = 1
                    WHERE id = ?
                    """,
                    [(book_id,) for book_id in missing_ids],
                )

            connection.execute(
                """
                UPDATE libraries
                SET last_scanned_at = ?
                WHERE id = ?
                """,
                (timestamp, library_id),
            )

        return len(books)

    def count_books(self, include_missing: bool = False) -> int:
        """Return the number of stored books."""
        query = "SELECT COUNT(*) AS total FROM books"

        if not include_missing:
            query += " WHERE is_missing = 0"

        with self.connection() as connection:
            row = connection.execute(query).fetchone()

        return int(row["total"]) if row else 0

    def get_book_by_id(self, book_id: int) -> sqlite3.Row | None:
        """Return one complete detached catalogue row by stable identity."""
        with self.connection() as connection:
            return connection.execute(
                """
                SELECT
                    books.*,
                    libraries.folder_path AS library_folder
                FROM books
                INNER JOIN libraries
                    ON libraries.id = books.library_id
                WHERE books.id = ?
                """,
                (int(book_id),),
            ).fetchone()

    def get_book_by_file_path(
        self,
        file_path: str | Path,
    ) -> sqlite3.Row | None:
        """Return one complete catalogue row for an exact resolved path."""
        resolved_path = str(Path(file_path).resolve())
        with self.connection() as connection:
            return connection.execute(
                """
                SELECT
                    books.*,
                    libraries.folder_path AS library_folder
                FROM books
                INNER JOIN libraries
                    ON libraries.id = books.library_id
                WHERE books.file_path = ? COLLATE NOCASE
                """,
                (resolved_path,),
            ).fetchone()

    def set_metadata_workflow_complete(
        self,
        book_id: int,
        complete: bool,
    ) -> None:
        """Persist whether a book finished the reviewed metadata workflow."""
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE books
                SET metadata_workflow_complete = ?
                WHERE id = ? AND is_missing = 0
                """,
                (int(bool(complete)), int(book_id)),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "The selected book is no longer in the active catalogue."
                )

    def remove_book_from_catalogue(self, book_id: int) -> None:
        """Remove one book row after its file has left the watched library."""
        with self.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM books WHERE id = ?",
                (int(book_id),),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "The selected book is no longer in the Twano catalogue."
                )

    def set_duplicate_exception(
        self,
        group_key: str,
        *,
        intentional: bool,
    ) -> None:
        """Persist or clear a user-reviewed intentional-edition decision."""
        cleaned_key = str(group_key).strip()
        if not cleaned_key:
            raise ValueError("Duplicate group key cannot be empty.")
        with self.connection() as connection:
            if intentional:
                connection.execute(
                    """
                    INSERT INTO duplicate_exceptions (
                        group_key, reason, created_at
                    )
                    VALUES (?, 'intentional editions', ?)
                    ON CONFLICT(group_key) DO UPDATE SET
                        reason = excluded.reason,
                        created_at = excluded.created_at
                    """,
                    (cleaned_key, self._utc_timestamp()),
                )
            else:
                connection.execute(
                    "DELETE FROM duplicate_exceptions WHERE group_key = ?",
                    (cleaned_key,),
                )

    def list_duplicate_exception_keys(self) -> tuple[str, ...]:
        """Return stable duplicate groups hidden by the user."""
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT group_key
                FROM duplicate_exceptions
                ORDER BY group_key
                """
            ).fetchall()
        return tuple(str(row["group_key"]) for row in rows)

    def record_quarantine_item(
        self,
        *,
        book_id: int,
        original_path: str,
        quarantine_path: str,
    ) -> int:
        """Record one recoverable file move and mark its record unavailable."""
        with self.connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO quarantine_items (
                    book_id, original_path, quarantine_path, created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    int(book_id),
                    str(original_path),
                    str(quarantine_path),
                    self._utc_timestamp(),
                ),
            )
            connection.execute(
                """
                UPDATE books
                SET is_missing = 1, review_required = 1
                WHERE id = ?
                """,
                (int(book_id),),
            )
            return int(cursor.lastrowid)

    def list_quarantine_items(self) -> list[sqlite3.Row]:
        """Return active quarantine moves newest first."""
        with self.connection() as connection:
            return connection.execute(
                """
                SELECT quarantine_items.*, books.title, books.file_name
                FROM quarantine_items
                INNER JOIN books ON books.id = quarantine_items.book_id
                WHERE quarantine_items.restored_at IS NULL
                ORDER BY quarantine_items.created_at DESC,
                    quarantine_items.id DESC
                """
            ).fetchall()

    def mark_quarantine_restored(
        self,
        quarantine_id: int,
        *,
        book_id: int,
    ) -> None:
        """Mark a successfully restored file available again atomically."""
        with self.connection() as connection:
            changed = connection.execute(
                """
                UPDATE quarantine_items
                SET restored_at = ?
                WHERE id = ? AND book_id = ? AND restored_at IS NULL
                """,
                (
                    self._utc_timestamp(),
                    int(quarantine_id),
                    int(book_id),
                ),
            )
            if changed.rowcount != 1:
                raise ValueError("That quarantine item is no longer active.")
            connection.execute(
                """
                UPDATE books
                SET is_missing = 0, review_required = 0,
                    last_seen_at = ?
                WHERE id = ?
                """,
                (self._utc_timestamp(), int(book_id)),
            )

    def get_books(self, include_missing: bool = False) -> list[sqlite3.Row]:
        """Return stored book records."""
        query = """
            SELECT
                books.id,
                books.file_name,
                books.title,
                books.author,
                books.isbn,
                books.publisher,
                books.language,
                books.published_date,
                books.series,
                books.series_number,
                books.series_group,
                books.series_group_number,
                books.provider_rating,
                books.rating_count,
                books.rating_source,
                books.description,
                books.cover_path,
                books.file_format,
                books.file_size,
                books.file_path,
                books.file_modified_at,
                books.discovered_at,
                books.metadata_status,
                books.metadata_workflow_complete,
                books.review_required,
                books.is_missing,
                libraries.folder_path AS library_folder,
                (
                    SELECT GROUP_CONCAT(collection_name, char(31))
                    FROM (
                        SELECT collections.name AS collection_name
                        FROM book_collections
                        INNER JOIN collections
                            ON collections.id =
                                book_collections.collection_id
                        WHERE book_collections.book_id = books.id
                        ORDER BY collections.name COLLATE NOCASE
                    )
                ) AS collections
            FROM books
            INNER JOIN libraries
                ON libraries.id = books.library_id
        """

        if not include_missing:
            query += " WHERE books.is_missing = 0"

        query += " ORDER BY COALESCE(books.title, books.file_name) COLLATE NOCASE"

        with self.connection() as connection:
            return connection.execute(query).fetchall()

    def get_distinct_series_names(self) -> tuple[str, ...]:
        """Return every distinct, non-empty series name already catalogued.

        Used to snap a freshly resolved series name back onto whatever
        wording/casing this user's own library already established, instead
        of trusting a provider's or web search's phrasing on any given run.
        """
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT series FROM books
                WHERE series IS NOT NULL AND TRIM(series) != ''
                """
            ).fetchall()
        return tuple(str(row["series"]) for row in rows)

    def search_books(
        self,
        search_text: str = "",
        file_format: str = "",
        file_formats: tuple[str, ...] | list[str] = (),
        provider_ratings: tuple[int, ...] | list[int] = (),
        metadata_status: str = "",
        author: str = "",
        series: str = "",
        collection: str = "",
        library_location: str = "",
        metadata_attention: bool = False,
        sort_field: str = "",
        sort_direction: str = "ascending",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        """Search and filter active books in the library."""
        conditions, parameters, cleaned_search = (
            self._library_search_conditions(
                search_text=search_text,
                file_format=file_format,
                file_formats=file_formats,
                provider_ratings=provider_ratings,
                metadata_status=metadata_status,
                author=author,
                series=series,
                collection=collection,
                library_location=library_location,
                metadata_attention=metadata_attention,
            )
        )

        query = """
            SELECT
                books.id,
                books.file_name,
                books.title,
                books.author,
                books.isbn,
                books.publisher,
                books.language,
                books.published_date,
                books.series,
                books.series_number,
                books.series_group,
                books.series_group_number,
                books.provider_rating,
                books.rating_count,
                books.rating_source,
                books.description,
                books.cover_path,
                books.file_format,
                books.file_size,
                books.file_path,
                books.file_modified_at,
                books.discovered_at,
                books.metadata_status,
                books.metadata_workflow_complete,
                books.review_required,
                books.is_missing,
                libraries.folder_path AS library_folder,
                (
                    SELECT GROUP_CONCAT(collection_name, char(31))
                    FROM (
                        SELECT collections.name AS collection_name
                        FROM book_collections
                        INNER JOIN collections
                            ON collections.id =
                                book_collections.collection_id
                        WHERE book_collections.book_id = books.id
                        ORDER BY collections.name COLLATE NOCASE
                    )
                ) AS collections
            FROM books
            INNER JOIN libraries
                ON libraries.id = books.library_id
        """

        query += " WHERE " + " AND ".join(conditions)
        if cleaned_search and not sort_field:
            query += """
                ORDER BY
                    CASE
                        WHEN LOWER(
                            COALESCE(NULLIF(books.title, ''), books.file_name)
                        ) = LOWER(?) THEN 0
                        WHEN LOWER(
                            COALESCE(NULLIF(books.title, ''), books.file_name)
                        ) LIKE LOWER(?) THEN 1
                        WHEN LOWER(COALESCE(books.author, ''))
                            LIKE LOWER(?) THEN 2
                        ELSE 3
                    END,
                    COALESCE(books.title, books.file_name) COLLATE NOCASE
            """
            parameters.extend(
                [
                    cleaned_search,
                    f"{cleaned_search}%",
                    f"%{cleaned_search}%",
                ]
            )
        else:
            query += self._library_order_clause(
                sort_field or "title",
                sort_direction,
            )

        if limit is not None:
            if limit <= 0:
                raise ValueError("limit must be greater than zero")
            if offset < 0:
                raise ValueError("offset cannot be negative")
            query += " LIMIT ? OFFSET ?"
            parameters.extend([limit, offset])
        elif offset:
            raise ValueError("offset requires a limit")

        with self.connection() as connection:
            return connection.execute(
                query,
                parameters,
            ).fetchall()

    def count_search_books(
        self,
        search_text: str = "",
        file_format: str = "",
        file_formats: tuple[str, ...] | list[str] = (),
        provider_ratings: tuple[int, ...] | list[int] = (),
        metadata_status: str = "",
        author: str = "",
        series: str = "",
        collection: str = "",
        library_location: str = "",
        metadata_attention: bool = False,
    ) -> int:
        """Return the number of active books matching library filters."""
        conditions, parameters, _ = self._library_search_conditions(
            search_text=search_text,
            file_format=file_format,
            file_formats=file_formats,
            provider_ratings=provider_ratings,
            metadata_status=metadata_status,
            author=author,
            series=series,
            collection=collection,
            library_location=library_location,
            metadata_attention=metadata_attention,
        )
        query = """
            SELECT COUNT(*) AS total
            FROM books
            INNER JOIN libraries
                ON libraries.id = books.library_id
            WHERE
        """
        query += " AND ".join(conditions)

        with self.connection() as connection:
            row = connection.execute(query, parameters).fetchone()
        return int(row["total"]) if row else 0

    @staticmethod
    def _library_search_conditions(
        *,
        search_text: str,
        file_format: str,
        file_formats: tuple[str, ...] | list[str],
        provider_ratings: tuple[int, ...] | list[int],
        metadata_status: str,
        author: str,
        series: str,
        collection: str,
        library_location: str,
        metadata_attention: bool,
    ) -> tuple[list[str], list[object], str]:
        """Build parameterised conditions shared by search and count."""
        conditions = ["books.is_missing = 0"]
        parameters: list[object] = []
        cleaned_search = search_text.strip()

        if cleaned_search:
            conditions.append(
                """
                (
                    COALESCE(books.title, '') LIKE ?
                    OR COALESCE(books.author, '') LIKE ?
                    OR COALESCE(books.isbn, '') LIKE ?
                    OR COALESCE(books.publisher, '') LIKE ?
                    OR COALESCE(books.series, '') LIKE ?
                    OR COALESCE(books.series_group, '') LIKE ?
                    OR books.file_name LIKE ?
                    OR books.file_path LIKE ?
                )
                """
            )
            search_pattern = f"%{cleaned_search}%"
            parameters.extend([search_pattern] * 8)

        cleaned_formats = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in file_formats
                if str(value).strip()
            )
        )
        if cleaned_formats:
            placeholders = ", ".join("?" for _ in cleaned_formats)
            conditions.append(f"books.file_format IN ({placeholders})")
            parameters.extend(cleaned_formats)
        elif file_format:
            conditions.append("books.file_format = ?")
            parameters.append(file_format)

        cleaned_ratings = tuple(
            dict.fromkeys(int(value) for value in provider_ratings)
        )
        if any(value < 0 or value > 5 for value in cleaned_ratings):
            raise ValueError("Website rating bands must be between 0 and 5.")
        if cleaned_ratings:
            placeholders = ", ".join("?" for _ in cleaned_ratings)
            conditions.append(
                "CAST(COALESCE(books.provider_rating, 0) + 0.5 AS INTEGER) "
                f"IN ({placeholders})"
            )
            parameters.extend(cleaned_ratings)

        if metadata_status:
            conditions.append("books.metadata_status = ?")
            parameters.append(metadata_status)

        cleaned_author = author.strip()
        if cleaned_author:
            conditions.append("COALESCE(books.author, '') LIKE ?")
            parameters.append(f"%{cleaned_author}%")

        cleaned_series = series.strip()
        if cleaned_series:
            conditions.append(
                "(COALESCE(books.series, '') LIKE ? OR "
                "COALESCE(books.series_group, '') LIKE ?)"
            )
            parameters.extend(
                [f"%{cleaned_series}%", f"%{cleaned_series}%"]
            )

        cleaned_collection = collection.strip()
        if cleaned_collection:
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM book_collections
                    INNER JOIN collections
                        ON collections.id =
                            book_collections.collection_id
                    WHERE book_collections.book_id = books.id
                        AND collections.name = ? COLLATE NOCASE
                )
                """
            )
            parameters.append(cleaned_collection)

        cleaned_location = library_location.strip()
        if cleaned_location:
            conditions.append(
                """
                (
                    books.file_path LIKE ?
                    OR libraries.folder_path LIKE ?
                )
                """
            )
            location_pattern = f"%{cleaned_location}%"
            parameters.extend([location_pattern, location_pattern])

        if metadata_attention:
            conditions.append(
                """
                (
                    books.metadata_status != 'embedded'
                    OR books.review_required = 1
                )
                """
            )

        return conditions, parameters, cleaned_search

    @staticmethod
    def _library_order_clause(
        sort_field: str,
        sort_direction: str,
    ) -> str:
        """Return an allowlisted ORDER BY clause."""
        sort_expressions = {
            "title": (
                "COALESCE(books.title, books.file_name) "
                "COLLATE NOCASE {direction}"
            ),
            "author": (
                "COALESCE(books.author, '') COLLATE NOCASE {direction}"
            ),
            "series": (
                "COALESCE(books.series_group, books.series, '') "
                "COLLATE NOCASE {direction}, "
                "COALESCE(books.series_group_number, 1.0e308) {direction}, "
                "COALESCE(books.series, '') COLLATE NOCASE {direction}, "
                "COALESCE(books.series_number, 1.0e308) {direction}"
            ),
            "date_added": "books.discovered_at {direction}",
            "file_modified": (
                "COALESCE(books.file_modified_at, '') {direction}"
            ),
            "format": "books.file_format COLLATE NOCASE {direction}",
            "metadata_quality": (
                "CASE "
                "WHEN books.metadata_status = 'embedded' "
                "AND books.review_required = 0 THEN 0 "
                "WHEN books.metadata_status = 'external' "
                "AND books.review_required = 0 THEN 1 "
                "ELSE 2 END {direction}"
            ),
        }
        expression_template = sort_expressions.get(sort_field)
        if expression_template is None:
            raise ValueError(f"Unsupported library sort field: {sort_field}")

        cleaned_direction = sort_direction.strip().casefold()
        if cleaned_direction not in {"ascending", "descending"}:
            raise ValueError(
                f"Unsupported library sort direction: {sort_direction}"
            )
        direction = "ASC" if cleaned_direction == "ascending" else "DESC"
        expression = expression_template.format(direction=direction)
        return (
            f" ORDER BY {expression}, "
            "COALESCE(books.title, books.file_name) COLLATE NOCASE ASC, "
            "books.id ASC"
        )

    def get_library_filter_options(
        self,
    ) -> tuple[list[str], list[str]]:
        """Return available formats and metadata statuses."""
        with self.connection() as connection:
            format_rows = connection.execute(
                """
                SELECT DISTINCT file_format
                FROM books
                WHERE is_missing = 0
                ORDER BY file_format COLLATE NOCASE
                """
            ).fetchall()

            status_rows = connection.execute(
                """
                SELECT DISTINCT metadata_status
                FROM books
                WHERE is_missing = 0
                ORDER BY metadata_status COLLATE NOCASE
                """
            ).fetchall()

        formats = [
            str(row["file_format"])
            for row in format_rows
            if row["file_format"]
        ]

        statuses = [
            str(row["metadata_status"])
            for row in status_rows
            if row["metadata_status"]
        ]

        return formats, statuses

    def get_library_browser_filter_options(
        self,
    ) -> dict[str, list[str]]:
        """Return all filter choices used by the RC6.5 Library browser."""
        columns = {
            "formats": ("books", "file_format"),
            "metadata_statuses": ("books", "metadata_status"),
            "authors": ("books", "author"),
            "series": ("books", "series"),
            "locations": ("libraries", "folder_path"),
            "collections": ("collections", "name"),
        }
        options: dict[str, list[str]] = {}

        with self.connection() as connection:
            for key, (table, column) in columns.items():
                if table == "books":
                    query = f"""
                        SELECT DISTINCT {column} AS value
                        FROM books
                        WHERE is_missing = 0
                            AND COALESCE({column}, '') != ''
                        ORDER BY value COLLATE NOCASE
                    """
                elif table == "libraries":
                    query = """
                        SELECT DISTINCT libraries.folder_path AS value
                        FROM libraries
                        INNER JOIN books
                            ON books.library_id = libraries.id
                        WHERE books.is_missing = 0
                        ORDER BY value COLLATE NOCASE
                    """
                else:
                    query = """
                        SELECT name AS value
                        FROM collections
                        ORDER BY name COLLATE NOCASE
                    """
                rows = connection.execute(query).fetchall()
                options[key] = [
                    str(row["value"])
                    for row in rows
                    if row["value"]
                ]

        return options

    def create_collection(self, name: str) -> int:
        """Create a named collection or return its existing ID."""
        cleaned_name = " ".join(name.split())
        if not cleaned_name:
            raise ValueError("Collection name cannot be empty.")
        timestamp = self._utc_timestamp()

        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO collections (name, created_at)
                VALUES (?, ?)
                ON CONFLICT(name) DO NOTHING
                """,
                (cleaned_name, timestamp),
            )
            row = connection.execute(
                """
                SELECT id
                FROM collections
                WHERE name = ? COLLATE NOCASE
                """,
                (cleaned_name,),
            ).fetchone()

        if row is None:
            raise RuntimeError("The collection could not be created.")
        return int(row["id"])

    def list_collections(self) -> list[sqlite3.Row]:
        """Return collections with their active book counts."""
        with self.connection() as connection:
            return connection.execute(
                """
                SELECT
                    collections.id,
                    collections.name,
                    COUNT(
                        CASE WHEN books.is_missing = 0 THEN 1 END
                    ) AS book_count
                FROM collections
                LEFT JOIN book_collections
                    ON book_collections.collection_id = collections.id
                LEFT JOIN books
                    ON books.id = book_collections.book_id
                GROUP BY collections.id, collections.name
                ORDER BY collections.name COLLATE NOCASE
                """
            ).fetchall()

    def get_book_collection_ids(self, book_id: int) -> list[int]:
        """Return collection IDs currently assigned to one book."""
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT collection_id
                FROM book_collections
                WHERE book_id = ?
                ORDER BY collection_id
                """,
                (book_id,),
            ).fetchall()
        return [int(row["collection_id"]) for row in rows]

    def set_book_collections(
        self,
        book_id: int,
        collection_ids: list[int] | tuple[int, ...],
    ) -> None:
        """Atomically replace one book's collection memberships."""
        unique_ids = tuple(dict.fromkeys(int(value) for value in collection_ids))
        timestamp = self._utc_timestamp()

        with self.connection() as connection:
            book = connection.execute(
                "SELECT id FROM books WHERE id = ?",
                (book_id,),
            ).fetchone()
            if book is None:
                raise ValueError(f"Unknown book ID: {book_id}")

            if unique_ids:
                placeholders = ", ".join("?" for _ in unique_ids)
                rows = connection.execute(
                    f"""
                    SELECT id
                    FROM collections
                    WHERE id IN ({placeholders})
                    """,
                    unique_ids,
                ).fetchall()
                found_ids = {int(row["id"]) for row in rows}
                if found_ids != set(unique_ids):
                    raise ValueError("One or more collection IDs are invalid.")

            connection.execute(
                "DELETE FROM book_collections WHERE book_id = ?",
                (book_id,),
            )
            connection.executemany(
                """
                INSERT INTO book_collections (
                    book_id,
                    collection_id,
                    created_at
                )
                VALUES (?, ?, ?)
                """,
                [
                    (book_id, collection_id, timestamp)
                    for collection_id in unique_ids
                ],
            )

    def get_dashboard_statistics(self) -> dict[str, object]:
        """Return summary statistics for the application dashboard."""
        with self.connection() as connection:
            totals = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_books,
                    SUM(
                        CASE
                            WHEN metadata_status = 'embedded'
                            THEN 1 ELSE 0
                        END
                    ) AS embedded_metadata,
                    SUM(
                        CASE
                            WHEN metadata_status != 'embedded'
                            THEN 1 ELSE 0
                        END
                    ) AS needs_metadata,
                    SUM(
                        CASE
                            WHEN is_missing = 1
                            THEN 1 ELSE 0
                        END
                    ) AS missing_books,
                    SUM(file_size) AS total_size
                FROM books
                """
            ).fetchone()

            format_rows = connection.execute(
                """
                SELECT
                    file_format,
                    COUNT(*) AS total
                FROM books
                WHERE is_missing = 0
                GROUP BY file_format
                ORDER BY total DESC, file_format COLLATE NOCASE
                """
            ).fetchall()

            library_count_row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM libraries
                WHERE archived_at IS NULL
                """
            ).fetchone()

            recent_rows = connection.execute(
                """
                SELECT title, author, file_name, file_format, discovered_at
                FROM books
                WHERE is_missing = 0
                ORDER BY discovered_at DESC, id DESC
                LIMIT 5
                """
            ).fetchall()

            attention_rows = connection.execute(
                """
                SELECT title, author, file_name
                FROM books
                WHERE is_missing = 0
                  AND metadata_status != 'embedded'
                ORDER BY review_required DESC, discovered_at DESC, id DESC
                LIMIT 3
                """
            ).fetchall()

            location_rows = connection.execute(
                """
                SELECT folder_path
                FROM libraries
                WHERE archived_at IS NULL
                ORDER BY COALESCE(last_scanned_at, created_at) DESC, id DESC
                LIMIT 3
                """
            ).fetchall()

            books_this_week_row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM books
                WHERE is_missing = 0
                  AND datetime(discovered_at) >= datetime('now', '-7 days')
                """
            ).fetchone()

            last_scan_row = connection.execute(
                """
                SELECT MAX(last_scanned_at) AS last_scanned_at
                FROM libraries
                WHERE archived_at IS NULL
                """
            ).fetchone()

        total_books = int(totals["total_books"] or 0)
        embedded_metadata = int(totals["embedded_metadata"] or 0)
        needs_metadata = int(totals["needs_metadata"] or 0)
        missing_books = int(totals["missing_books"] or 0)
        total_size = int(totals["total_size"] or 0)

        active_books = max(0, total_books - missing_books)

        if active_books:
            metadata_health = round(
                embedded_metadata / active_books * 100
            )
        else:
            metadata_health = 0

        formats = {
            str(row["file_format"]): int(row["total"])
            for row in format_rows
        }

        return {
            "total_books": active_books,
            "embedded_metadata": embedded_metadata,
            "needs_metadata": needs_metadata,
            "missing_books": missing_books,
            "total_size": total_size,
            "library_count": int(
                library_count_row["total"]
                if library_count_row
                else 0
            ),
            "metadata_health": metadata_health,
            "formats": formats,
            "books_this_week": int(
                books_this_week_row["total"] if books_this_week_row else 0
            ),
            "last_scanned_at": (
                str(last_scan_row["last_scanned_at"])
                if last_scan_row and last_scan_row["last_scanned_at"]
                else None
            ),
            "recent_books": [
                {
                    "title": str(row["title"] or row["file_name"]),
                    "author": str(row["author"] or "Unknown author"),
                    "file_format": str(row["file_format"] or ""),
                    "discovered_at": str(row["discovered_at"] or ""),
                }
                for row in recent_rows
            ],
            "attention_books": [
                {
                    "title": str(row["title"] or row["file_name"]),
                    "author": str(row["author"] or "Unknown author"),
                }
                for row in attention_rows
            ],
            "library_locations": [str(row["folder_path"]) for row in location_rows],
        }

    @staticmethod
    def _utc_timestamp() -> str:
        """Return the current UTC timestamp."""
        return datetime.now(timezone.utc).isoformat()

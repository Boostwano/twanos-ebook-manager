# Database

## Modules and Responsibilities

`src/database/database.py` contains the SQLite implementation. `DatabaseManager` owns initialization, connections, transactions, watched-source settings, scan persistence, metadata updates, Library queries, and dashboard statistics.

`LibraryService` owns Library read orchestration, `DashboardService` prepares dashboard data, and `ScanService` coordinates scan and metadata persistence. UI modules contain no SQL.

The default database is `%LOCALAPPDATA%\Twano\library.db`; tests pass explicit
temporary paths. The earlier `~/.twanos_ebook_manager/library.db` development
catalogue is preserved separately.

## Connection and Transaction Lifecycle

`DatabaseManager.connection()` opens a connection for each context, configures `sqlite3.Row` results and foreign keys, commits successful work, rolls back on exceptions, and closes in `finally`. The manager does not retain a live connection.

Operations that require one transaction use one connection context.
`apply_scan_preview()` owns the RC6.6 approved Apply transaction: revalidated
book inserts/updates, source result fields, and the matching history row commit
together or roll back together. The retained legacy `get_or_create_library()`
and subsequent immediate-scan upserts remain separate committed operations.

## Thread Ownership

The thread entering `connection()` owns that connection until it closes. Connections must never pass between GUI and worker threads. `ScanWorker` creates `ScanService` through its factory inside `run`, so scan connections open and close in the worker thread.

## Confirmed Schema

### `libraries`

- `id`: integer primary key
- `folder_path`: unique, required text
- `display_name`: nullable user-facing source name
- `created_at`: required text timestamp
- `last_scanned_at`: nullable text timestamp
- `is_enabled`: required watch flag, default `1`
- `include_subfolders`: required recursion flag, default `1`
- `include_patterns`, `exclude_patterns`: required JSON text arrays
- `archived_at`: nullable timestamp after a watch is removed
- `connection_status`, `connection_message`: latest read-only test evidence
- `connection_tested_at`: nullable connection-test timestamp
- `last_scan_status`, `last_scan_duration_ms`: latest approved Apply outcome
- `last_scan_discovered_count`, `last_scan_new_count`,
  `last_scan_changed_count`, `last_scan_missing_count`,
  `last_scan_unreadable_count`, `last_scan_skipped_count`: source result
  evidence
- `last_scan_error`: concise latest Apply error or safe-skip summary

Disabled source rows remain referenced by their books. Remove Watch runs one
database transaction that deletes only books with the selected `library_id`
and then archives that source configuration. Ebook files are never touched,
other sources are unaffected, and an active quarantine record blocks removal
until it is restored.

### `books`

- `id`: integer primary key
- `library_id`: required foreign key to `libraries.id`, cascading on delete
- `file_path`: unique, required text
- `file_name`: required text
- `title`, `author`, `isbn`, `publisher`, `language`, `published_date`: nullable metadata text
- `series`, `description`, `cover_path`: nullable presentation metadata text
- `series_number`: nullable real sequence within a series
- `file_format`: required text
- `file_size`: required integer
- `file_modified_at`: nullable text timestamp
- `file_fingerprint`: nullable fast size/mtime signature used by RC6.6 preview
- `discovered_at`, `last_seen_at`: required text timestamps
- `metadata_status`: required text, default `pending`
- `review_required`: required integer flag, default `0`
- `is_missing`: required integer flag, default `0`

### `collections`

- `id`: integer primary key
- `name`: required, unique case-insensitive text
- `created_at`: required text timestamp

### `book_collections`

- `book_id`: required cascading foreign key to `books.id`
- `collection_id`: required cascading foreign key to `collections.id`
- `created_at`: required text timestamp
- composite primary key on `(book_id, collection_id)`

### `scan_history`

- `id`: integer primary key
- `library_id`: required foreign key to the preserved source identity
- `scan_token`: required unique preview token preventing repeat Apply
- `started_at`, `finished_at`, `duration_ms`, `status`: timing and outcome
- discovery counts for new, changed, missing, unchanged, unreadable, and
  skipped preview items
- applied counts for new, changed, missing, and refreshed unchanged rows
- `safely_skipped_count`: candidates excluded by final safety checks
- `error_summary`: concise rollback or skip evidence

History rows are created only for explicitly approved Apply attempts. Preview,
preview cancellation, and Discard remain free of database writes.

Indexes cover library, title, ISBN, author, series/sequence, format, metadata
status, discovered date, modified date, and collection membership.

## Search and Dashboard Queries

Library queries exclude missing books by default. Search matches title, author,
ISBN, publisher, series, filename, and path. Filters cover format, metadata
status, author, series, collection, library location, and the
metadata-attention predicate. The RC6.5 browser adds matching counts, limit,
offset, and allowlisted title, author, series/sequence, date-added,
file-modified, format, and metadata-quality ordering. The older unpaged search
contract remains available to Search Results and Review Queue.

Collection names are created case-insensitively. Replacing a book's collection
memberships validates every ID, deletes and inserts within one transaction, and
never accesses or changes the ebook file.

Dashboard queries calculate active and missing counts, embedded-versus-needed metadata, total size, library count, metadata health, and active format counts.

## Schema Evolution

There is no separate migration framework. `initialise_database()` creates
tables and indexes when absent, then checks `PRAGMA table_info(books)` and adds
`publisher`, `language`, `published_date`, `series`, `description`, and
`cover_path` when missing. Future schema work must preserve existing data and
document its migration strategy. RC6.5 uses the same additive strategy for
`series_number`, creates collection tables with `IF NOT EXISTS`, and then
creates the new indexes only after the additive column exists. Migration and
foreign-key behavior are covered by focused tests. RC6.6 Milestone 1
additively introduces watched-source fields on `libraries`; existing rows
receive enabled, recursive, not-tested defaults and retain their IDs and book
relationships.

RC6.6 analysis reads `get_library_source_book_snapshot()` through a short-lived
connection. It does not update book rows, `is_missing`, `last_scanned_at`, or
connection/history evidence. The new nullable `file_fingerprint` column is
additive; accepted RC6.5 rows safely fall back to size and modification-time
comparison until approved Apply records fingerprints.

Milestone 4 additively creates `scan_history` and source last-result columns.
`apply_scan_preview()` uses optimistic catalogue predicates plus a unique scan
token. A stale row is safely skipped, and any SQL exception rolls back book,
source, and history changes as one unit.

RC6.7 Milestone 5 additively adds nullable
`scan_history.protection_operation_id`. Existing history remains valid with a
null link. New confirmed Apply attempts reference one `scan_apply` protection
operation. Applied book/source changes, Scan History, operation items, backup
identity, and the final protection status commit together. Cancelled and
failed attempts also record both linked terminal outcomes in one transaction.
The scan token remains the duplicate-application guard.

## RC6.7 online backup boundary

`backup_database()` uses SQLite's online backup API rather than copying an open
database file. It opens and closes both source and destination connections in
the caller's worker thread, refuses the live database as its destination, does
not overwrite an existing file, reports page progress, and removes the exact
destination if copy or cancellation fails.

`verify_database_backup()` opens the selected file read-only and runs
`PRAGMA integrity_check`. A SQLite progress handler permits cancellation
without sharing its connection. SHA256 manifests and backup-file ownership are
service responsibilities, so the database module remains independent of
PySide6 and presentation.

Milestone 1 adds no schema tables and does not modify the live catalogue while
creating or verifying a backup.

## RC6.7 operation audit tables

### `protection_operations`

- unique immutable operation and plan tokens
- operation type, human-readable title and summary
- initiator and initiating component
- created, updated, started, and finished timestamps
- status, risk, reversibility, and confirmation requirement
- affected-book, database-change, and file-change counts
- original warnings and complete plan JSON
- confirmation evidence, backup identity, error summary, and rollback outcome
- optional source-operation link connecting an Undo to its original operation

### `protection_operation_items`

- ordered target, action, and readable description
- optional durable book ID/title evidence without a deleting foreign key
- before/after summaries
- reversibility and per-item outcome
- error plus schema-validated inverse JSON for reversible executed items

Plan and item creation is one transaction. Status transitions use an expected
current status so repeated or stale approval/cancellation cannot silently
replace a newer outcome. Audit tables are additive and do not alter existing
book, collection, source, or scan-history rows.

`apply_collection_create_operation()` is the first RC6.7 allowlisted executor.
It validates the approved operation type, proves the collection is still
absent, creates the row, stores its exact delete inverse, and records Applied
as one transaction.

`apply_collection_undo_operation()` validates the linked source operation,
stored collection ID/name, empty membership state, and absence of a competing
Undo. It removes that collection, records the Undo as Applied, and marks the
source as Undone in one transaction. An exception rolls back both catalogue
and audit changes before the service records separate failure evidence.

## RC6.7 Restore and retention boundary

Restore does not copy an open SQLite file over the live catalogue. The service
first uses the existing online-backup path to create and verify a recovery
snapshot. It then stages the selected backup beside the live database, runs
`integrity_check`, recomputes SHA256, and publishes it with same-folder
`os.replace` only while other database workers are idle.

Because a backup captures its own `database_backup` audit while that row is
Applying, `complete_embedded_backup_operation()` reconciles the embedded row
after a snapshot becomes live. The completed Restore operation is then
inserted into the restored catalogue with the preserved immutable plan,
confirmation, selected-backup identity, and verified recovery-backup inverse.
If a later step fails, the recovery snapshot is staged and verified before the
pre-restore catalogue is republished.

Retention cleanup has no arbitrary SQL or path-delete API. The service parses
only the exact file items produced by its dry run, requires regular
Twano-prefixed SQLite files and exact sidecar manifests in the saved folder,
rejects symbolic links, rechecks age and immutable identity, and performs full
SQLite/SHA256 verification before moving the pairs to a private quarantine.
Unrelated, recent, changed, invalid, legacy, or unverified files never reach
the deletion phase.

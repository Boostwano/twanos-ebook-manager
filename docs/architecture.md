# Architecture

This page records implementation details visible in the current repository. Root [`ARCHITECTURE.md`](../ARCHITECTURE.md) states the stable boundaries and links here for detail.

## Current Package Overview

| Package or module | Responsibility |
| --- | --- |
| `src/app.py`, `src/main_window.py` | Startup, top-level window, page construction, and navigation |
| `src/ui/` | PySide6 widgets, presentation, signals, navigation, and interaction |
| `src/services/` | UI-independent banner, dashboard, Library, scan, metadata, approved-provider, and protected-credential orchestration |
| `src/workers/` | `QObject` workers for long-running work on `QThread` |
| `src/database/` | SQLite schema, connections, transactions, persistence, search, and statistics |
| `src/core/` | Domain utilities and local extraction, plus early modules for later features |
| `src/metadata/` | Provider-neutral model, interface, and provider manager |
| `src/metadata/providers/` | Built-in local extraction and Open Library enrichment providers |

Some destinations in `MainWindow` are placeholders. Early modules and product documents do not establish that their features are complete.

RC6.5 adds `LibraryModel`, `LibraryGridDelegate`, `BookDetailsPanel`, and
`ThumbnailCache`. Grid and list views use the same model and
`QItemSelectionModel`, so presentation changes do not reload the database.
`MainWindow.pages_by_id` remains the authoritative mapping from stable page IDs
to stacked widgets.

RC6.6 Milestone 1 adds watched-source presentation to `ScanPage`,
`LibrarySourceDialog` for validated settings, and `SourceConnectionWorker` for
read-only availability tests. Source configuration is detached through
`ScanService`; SQL remains in `DatabaseManager`.

Milestones 2–3 add `ScanAnalysisWorker` and immutable analysis items, issues,
and results. Analysis applies source rules, compares detached database
snapshots, and sends a preview to the GUI without writing catalogue state.
Milestone 4 adds `ScanApplyWorker`, immutable Apply results, guarded
filesystem/catalogue rechecks, and a database-owned transaction that includes
book changes, source result evidence, and scan history.

`BannerService` resolves validated fixed or once-per-launch banner choices
without depending on widgets. `DashboardPage` passes the resolved name and
asset path to `SquareHero`, which owns image cropping, the text contrast
overlay, and the painted fallback.

## Dependency Flow and Responsibilities

```text
PySide6 UI
  -> UI-independent services
    -> database and metadata abstractions
      -> SQLite and local file parsing

ScanPage -> QThread -> ScanWorker -> ScanService
ScanPage -> QThread -> SourceConnectionWorker -> ScanService
ScanPage -> QThread -> ScanAnalysisWorker -> ScanService -> read snapshot
ScanPage -> QThread -> ScanApplyWorker -> ScanService -> DatabaseManager
LibraryPage -> QThreadPool -> LibraryService -> DatabaseManager
ThumbnailCache -> QThreadPool -> QImage decode -> GUI-thread QPixmap
MetadataStudioPage -> QThread -> MetadataLookupWorker -> MetadataStudioService
MetadataStudioService -> enabled native provider -> documented HTTPS API
```

UI code owns widgets and presentation. Services coordinate use cases and return detached values. Workers adapt progress to Qt signals. `DatabaseManager` owns SQL and transactions. Metadata providers return `MetadataResult` without UI dependencies; the backward-compatible `enrich()` hook can receive the accumulated local result.

The manual Metadata Studio path is separate from scan-time enrichment.

Metadata Apply can optionally organise the reviewed physical ebook. The UI
only captures the explicit option and displays the immutable plan. Protection
Service derives and validates an Author or shared `-=Series=-` destination within the current
watched-library root, creates the verified catalogue backup, refuses path
collisions, and performs the move on its worker thread. DatabaseManager then
commits metadata plus `file_path` and `file_name` in one SQLite transaction and
records both plan items. If that transaction fails, ProtectionService moves the
ebook back before reporting failure. Ebook contents are never rewritten.
When optional `series_group` metadata is present, the path is
`-=Series=- / Series Group / Series Name`; `series_group_number` preserves the
broader universe order in catalogue sorting.
`PluginService` exposes only approved native providers and never imports a
Calibre plugin ZIP. `MetadataStudioService` searches the active providers and
maps every result to immutable `MetadataCandidate` values for field-level
review. `RemoteMetadataProviderService` owns Hardcover and Comic Vine HTTPS
requests. `PluginCredentialStore` encrypts provider keys with Windows DPAPI;
the Plugins UI receives only configured/not-configured state, never a saved
key.

## QThread Lifecycle

`ScanPage` creates a fresh `QThread` and `ScanWorker` per scan. The worker moves to that thread, and `QThread.started` invokes `run`. The worker creates its `ScanService` through a factory inside `run`, keeping database work in the worker thread.

Every outcome reaches `finished` from a `finally` block. That signal schedules worker deletion and quits the thread. `QThread.finished` clears references, schedules thread deletion, restores controls, and permits another scan. Cancellation uses a thread-safe event; shutdown requests cancellation and closes later instead of blocking the GUI.

Source connection checks use a separate short-lived worker and service
instance. The main window treats either worker as active background work and
defers closing until it finishes. Connection checks never write to ebook files
or mark catalogue books missing.

Safe Preview uses another fresh `QThread`. Cancellation uses a thread-safe
event checked during folder and file enumeration. A cancelled, unavailable, or
incomplete analysis returns no missing classification and never exposes Apply.

Approved Apply uses a separate fresh `QThread`. The worker creates its service
in that thread, rechecks detached catalogue facts and every candidate,
refreshes metadata only for new or changed files, and performs a final
filesystem check. Cancellation is honoured before the database transaction.
Once transaction work begins, it completes atomically and cannot leave a
partial catalogue.

Preview All queues every enabled watched source and creates a fresh analysis
worker/thread for each source in sequence. The UI combines the detached
results; it never shares SQLite connections between sources. Apply All uses
the same sequential pattern and preserves a separate atomic transaction,
verified backup, Scan History row, and protection history record per source.

Remove Watch uses its own short-lived worker and a fresh `ScanService`. Before
the worker starts, the UI shows the exact associated book count and confirms
that only Twano catalogue entries will be removed. The database layer deletes
only rows belonging to that source and archives the watch in one transaction.
The source folder, ebook files, embedded metadata, and every other source are
unchanged.

## SQLite Thread Safety

- Open, use, commit or roll back, and close each connection in one thread.
- Do not store or share live `sqlite3.Connection` objects.
- Construct scan-side services inside the worker thread.
- Commit scan results before notifying UI completion observers.
- Keep raw SQL in the database layer.

`DatabaseManager.connection()` creates one connection per context, enables foreign keys, commits on success, rolls back on error, and always closes it.

## Scan-to-Library Data Flow

The sequence below documents the accepted pre-preview pipeline retained for
regression coverage. RC6.6 does not expose it for configured watched sources;
watched sources use the preview/apply flow documented after it.

1. `ScanPage` starts a worker thread.
2. `ScanWorker` creates `ScanService`, validates the folder, and discovers files.
3. `ScanService` persists discovered books through `DatabaseManager`.
4. `ProviderManager` runs local extraction first, then Open Library when enabled, and merges non-empty fields conservatively.
5. Metadata updates commit before completion is signalled.
6. Navigation activates `LibraryPage`.
7. `LibraryModel` starts a background first-page service query.
8. `LibraryService` obtains filtered rows and creates immutable
   `LibraryRecord` values.
9. The GUI thread appends the detached page to the model; grid and list update
   from the same rows.
10. Scrolling requests the next page only when one is available.

## RC6.6 watched-source preview and Apply flow

1. `ScanAnalysisWorker` walks one connected enabled source using its recursion
   and include/exclude rules.
2. `ScanService` compares candidates with detached source-book snapshots and
   returns an immutable preview token, classifications, issues, and counts.
3. Preview, cancellation, and discard do not update books, missing flags,
   source scan timestamps, or history.
4. Explicit Apply starts `ScanApplyWorker`; incomplete or stale previews are
   rejected.
5. The service compares current catalogue facts with the preview and rechecks
   candidate existence, size, and modification fingerprint.
6. New and changed candidates receive metadata extraction off the GUI thread.
7. A final file check excludes candidates that changed, vanished, or
   reappeared while Apply was being prepared.
8. `DatabaseManager.apply_scan_preview()` applies the remaining changes and
   writes source result evidence plus one history row in one transaction.
9. A failure rolls back the full unit; cancellation before that unit records a
   cancelled approved attempt without changing books.
10. Library and Home refresh only after successful commit.

## RC6.7 verified backup flow

1. `ProtectionPage` validates and persists an absolute folder plus retention
   age; zero means Keep All.
2. A fresh `BackupWorker` constructs its `ProtectionService` inside a
   dedicated `QThread`.
3. `DatabaseManager.backup_database()` opens source and destination SQLite
   connections in that worker and uses the online backup API.
4. The copied private partial database passes read-only
   `PRAGMA integrity_check`.
5. `ProtectionService` calculates SHA256 and writes a versioned sidecar
   manifest with source identity, creation time, size, application version,
   and verification evidence.
6. Only then are the uniquely named database and manifest atomically moved to
   their final names.
7. Cancellation or failure removes the operation's exact partial and
   unpublished files.
8. Verify Backup repeats integrity and checksum comparison off the GUI thread;
   missing or legacy manifests are never labelled Verified.

The first checkpoint stored retention policy without deleting backups.
Milestone 4 now exposes routine Restore and cleanup through plain-language
actions while keeping detailed plan and audit evidence secondary.

## RC6.7 change-plan and audit flow

1. A component constructs a frozen `ChangePlan` with an exact token, expiry,
   basis token, risk, reversibility, confirmation requirement, affected count,
   warnings, and separated database/file items.
2. The model rejects incomplete intent, inconsistent targets, weak high-risk
   confirmation requirements, and invalid timestamps before persistence.
3. `ProtectionService.record_change_plan()` stores the original plan and all
   ordered items in one additive database transaction.
4. Preview changes no catalogue, metadata, collection, or ebook-file state.
5. Approval validates the exact plan token, current basis, expiry, repeated
   application evidence, and required confirmation, then records approval
   only.
6. Cancellation records a terminal outcome and item states without executing
   the proposed change.
7. `ProtectionHistoryPanel` reloads detached operation records after restart
   and presents original intent plus backup, error, and rollback evidence.
8. `AuditExportWorker` reopens its database service in a worker thread and
   atomically publishes a concise Markdown report.

The built-in Safety Check plan writes only its own audit evidence and has no
executor. Verified backup creation also records common
applied/cancelled/failed history. Milestone 5 links Scan Apply into that same
history while retaining Scan History as the source of scan-specific counts.

## RC6.7 protected executor and Undo flow

1. The built-in reversible checkpoint previews creation of one uniquely named
   empty collection. Its operation type and single database action are
   allowlisted; arbitrary plan actions cannot reach the executor.
2. Approval recalculates the collection-absence basis token. Apply rechecks
   Standard protection mode, stored confirmation, expiry, plan shape, and
   current basis.
3. `ProtectionExecutorWorker` constructs its service in a dedicated
   `QThread`. Before mutation, `ProtectionService` creates and verifies a
   catalogue backup and records its identity.
4. The plan is revalidated again after backup creation.
5. `DatabaseManager.apply_collection_create_operation()` changes the
   collection row, stores schema-validated inverse JSON, updates item outcome,
   and records Applied in one SQLite transaction.
6. Any SQL error rolls that entire transaction back. A separate transition
   records Failed, the verified backup identity, the concise error, and the
   truthful rollback outcome.
7. Preview Undo reads the persisted inverse after service recreation and
   proves the exact created collection still exists and remains empty.
8. Undo receives its own plan, confirmation, verified backup, source-operation
   link, and atomic database transaction. The Undo record becomes Applied
   while the original record becomes Undone; neither history record is
   deleted.

Cancellation is available during backup preparation and before the atomic
database transaction.

## RC6.7 Restore and retention flow

1. **Restore Backup** records and approves the exact selected-backup plan
   behind one plain-language confirmation; the user does not manage plan
   tokens or recovery mechanics.
2. The worker fully re-verifies SQLite integrity and SHA256, then creates a
   second verified backup of the current live catalogue.
3. The selected backup is copied to a private file beside the live database,
   verified again, hashed, and flushed before replacement.
4. MainWindow permits replacement only while Scan and Library database workers
   are idle and locks navigation for the replacement phase.
5. Same-folder `os.replace` publishes the staged catalogue. The restored
   database is migrated additively, its embedded backup audit is reconciled,
   and the Restore outcome plus recovery identity are recorded.
6. If a post-replacement step fails, the verified pre-restore backup is staged,
   verified, and automatically restored; failure history explains that result.
7. **Review Old Backups** runs a background dry run using the saved age policy
   and shows only candidate count and total size before confirmation.
8. Cleanup accepts regular, non-symbolic-link Twano backup/manifest pairs only.
   Every candidate is fully reverified and rechecked against the recorded
   folder, age, size, timestamp, and SHA256 evidence.
9. Exact pairs move to an operation-specific quarantine before deletion. A
   move failure restores all moved artifacts; any deletion-stage partial result
   is recorded truthfully with remaining recovery evidence.

## RC6.7 Scan Apply integration flow

1. The user reviews the immutable Preview Scan result and uses the existing
   single **Apply Preview** confirmation.
2. In the worker thread, `ScanService` records and approves an exact
   `scan_apply` operation, then rechecks source settings, catalogue facts, and
   every candidate file.
3. `ProtectionService` creates and verifies a catalogue safety backup
   automatically. Cancellation remains available before the database
   transaction.
4. `DatabaseManager.apply_scan_preview()` validates the linked approved
   operation and commits book/source changes, Scan History, operation items,
   backup identity, and Applied status in one transaction.
5. Cancelled and failed attempts record their linked Scan and protection
   outcomes together. Existing pre-RC6.7 Scan History remains valid with no
   operation link.
6. Scan Apply is labelled **No one-click Undo; safety backup available**.
   Recovery uses an explicit whole-catalogue Restore and never changes ebook
   files.

Redo and ebook-file execution remain later milestones.

## RC6.5 Library presentation flow

1. Filter and sort controls create a validated immutable `LibraryQuery`.
2. `LibraryModel` increments its generation and runs the service query in a
   thread-pool task.
3. `DatabaseManager` applies parameterised predicates, allowlisted ordering,
   limit, and offset using a connection owned by that task.
4. Stale generations are ignored after the user changes the visible query.
5. The grid delegate requests cover work only while painting visible cards.
6. A worker decodes and scales `QImage`; the GUI thread converts it to
   `QPixmap` and stores it in the bounded LRU cache.
7. The wide splitter and compact replacement both reuse the same
   `BookDetailsPanel`.

## Search and metadata-attention flow

1. Home asks `LibraryService` for a maximum of five displayed suggestions.
2. `SearchSuggestionPopup` renders as a child overlay below the search field,
   outside the Home layout.
3. Enter, Find a Book, or View all routes the query to
   `SearchResultsPage` through the explicit `search` page ID.
4. Search refinements return through `LibraryService`; publisher, series,
   author, location, format, and metadata predicates remain in
   `DatabaseManager`.
5. The Home metadata insight routes to `ReviewQueuePage`, whose service request
   explicitly enables `metadata_attention`.
6. Search and review result rows use the shared UI reader launcher, which loads
   current Reading preferences before opening a file.

## Current Limitations

- Embedded extraction supports only EPUB; other scanned formats receive an unsupported extraction status.
- Open Library enrichment is opt-in and has an in-memory scan-session cache rather than persistent or offline caching.
- Several navigation destinations are placeholders.
- Schema evolution uses additive column checks, not a versioned migration framework.
- Search Results and Review Queue retain their existing unbounded read contract;
  the dedicated Library browser is paged and background-loaded.
- RC6.5 does not download covers or edit metadata and ebook files.
- RC6.6 guarded Apply, native validation, performance, and package acceptance
  are complete.
- RC6.7 currently provides verified catalogue backups, immutable plan
  previews, persistent audit history, report export, protected database
  execution, persistent Undo, guided catalogue Restore, and reviewed retention
  cleanup. Confirmed Scan Apply also uses the common backup and audit layer.
  Redo and ebook-file execution remain later milestones.

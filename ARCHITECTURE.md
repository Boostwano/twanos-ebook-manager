# Architecture

Twano's eBook Manager is a Python and PySide6 desktop application. Its intended dependency direction is:

```text
UI -> Services -> Database -> SQLite
```

UI modules own widgets, signals, navigation, and presentation. UI-independent services coordinate application use cases. The database layer owns SQL, connections, transactions, and persistence. Metadata providers return provider-neutral results through `ProviderManager`; local metadata runs first and enabled external providers can enrich it. Long-running scans, including network enrichment, execute in a `QObject` worker on a `QThread`.

RC6.4 navigation uses explicit page IDs rather than stacked-widget indexes.
Home search suggestions are transient UI overlays; persistent result and
metadata-attention views query through `LibraryService`, which delegates all
search SQL to `DatabaseManager`. Reader launching is shared by the UI result
surfaces and remains driven by `PreferencesStore`.
Home banner validation and once-per-launch selection live in the
UI-independent `BannerService`; the Home widget owns only image presentation
and its painted missing-asset fallback.

Manual online lookup remains `UI -> worker -> service`. `PluginService` owns
the approved catalogue and activation state. `MetadataStudioService`
coordinates enabled Open Library, Hardcover, Comic Vine, and cover providers
and returns provider-neutral `MetadataCandidate` values. Network work runs in
`MetadataLookupWorker`; UI classes never contain provider requests. API keys
are encrypted for the current Windows account by `PluginCredentialStore`,
stored separately from plugin state, and retrieved only by the provider
service that needs them. Calibre ZIPs are never imported or executed.
Key-free Amazon, Google Images, and Edelweiss adapters also run behind
`RemoteMetadataProviderService`. They validate provider-specific response
markers before parsing. Bot/access pages, transport failures, and unknown page
layouts raise distinct provider failures. `PluginService` persists only the
safe health category, timestamp, and bounded diagnostic in
`provider-health.json`; the Plugins UI presents those checks without storing
search terms or response pages.

RC6.5 Library browsing uses one `LibraryModel` as the paged record source for
both a cover-grid delegate and `QTableView`. Production page queries run in
`QThreadPool` tasks; service calls open short-lived SQLite connections in the
worker thread and return detached immutable values. A shared
`QItemSelectionModel` preserves selection across presentation changes.
Thumbnail tasks decode and scale `QImage` values off the GUI thread, while
`ThumbnailCache` creates and retains bounded `QPixmap` values only on the GUI
thread. Collection membership remains a service/database operation and never
changes ebook files.

RC6.6 watched-source management extends the existing `libraries` identity
without deleting or relocating its books. `ScanService` validates and returns
detached source values. Read-only connection checks create their service and
SQLite connection inside `SourceConnectionWorker` on a dedicated `QThread`.
`ScanAnalysisWorker` separately produces an immutable, discardable preview.
Analysis reads detached book snapshots and never updates books, missing flags,
source scan timestamps, or history. `ScanApplyWorker` rechecks an explicitly
approved preview, refreshes metadata only for new or changed candidates, and
sends primitive change facts to one database-owned transaction. That
transaction atomically updates books, source result evidence, and scan history;
exceptions roll back the entire unit. The accepted immediate scan pipeline
remains internally regression-tested but is not exposed for watched sources.
The combined all-source workflow queues enabled sources in `ScanPage` and
starts one fresh worker/thread at a time. Its combined preview remains
non-mutating; approved sources are then applied sequentially so each source
retains its own atomic transaction, verified backup, and Undo history record.

RC6.7 introduces a common protection service without changing ebook files.
`ProtectionPage` persists policy in `PreferencesStore` and starts a fresh
`BackupWorker`; the worker constructs `ProtectionService` in its own
`QThread`. `DatabaseManager` owns SQLite online copy and read-only integrity
verification. The service publishes an immutable backup record only after
integrity and SHA256 evidence are complete, and removes its exact partial
artifacts on cancellation or failure.

Milestone 2 adds immutable change-plan contracts and additive
`protection_operations` / `protection_operation_items` audit persistence.
`ProtectionService` validates plan tokens, expiry, basis, risk, reversibility,
and confirmation before recording approval; approval remains separate from
execution.
`ProtectionHistoryPanel` presents detached plans and operation records and
starts `AuditExportWorker` for atomic Markdown report export. Verified backup
creation now records applied, cancelled, or failed evidence in the common
history.

Milestone 3 adds `ProtectionExecutorWorker` and one narrow allowlisted
collection-create executor. Standard mode, exact confirmation, expiry, basis,
plan shape, and a verified pre-change backup are required. Collection
creation, inverse JSON, and audit outcome share one transaction. Undo is a new
source-linked operation that revalidates the exact empty collection and
atomically leaves the source record as Undone. At that checkpoint Restore,
retention cleanup, redo, ebook-file execution, and Scan Apply integration
were still unavailable.

Milestone 4 keeps Restore and retention simple in the UI while retaining the
same protection contracts internally. Restore fully verifies the selected
backup, creates a verified safety copy of current state, stages and verifies a
same-folder replacement, and only then replaces the live catalogue. A
post-replacement failure restores the safety copy. Retention records a dry-run
plan and revalidates exact regular Twano backup/manifest pairs before bounded
quarantine-and-delete cleanup. Other database workers must be idle during live
replacement. Redo, ebook-file execution, and Scan Apply integration remained
unavailable at that checkpoint.

Milestone 5 keeps the accepted Scan UI unchanged while linking its confirmed
Apply to the common protection layer. `ScanService` records and approves the
exact immutable preview in its worker thread, creates a verified catalogue
backup, rechecks every candidate, and sends the operation identity with the
primitive changes to `DatabaseManager`. Book/source updates, Scan History, and
the linked protection outcome commit in one SQLite transaction. Cancellation
and failure also write both linked outcomes together. Scan Apply is labelled
as having no one-click Undo; its verified pre-change backup supports an
explicit whole-catalogue Restore.

SQLite connections are short-lived and thread-owned: each connection must be created, used, committed or rolled back, and closed in the same thread. The GUI must not block waiting for worker threads.

For the package map, scan lifecycle, data flow, limitations, and detailed responsibilities, see [`docs/architecture.md`](docs/architecture.md). Database and metadata specifics are in [`docs/database.md`](docs/database.md) and [`docs/metadata.md`](docs/metadata.md).

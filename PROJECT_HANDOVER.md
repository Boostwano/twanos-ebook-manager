# PROJECT HANDOVER — R4 RC1 Production Release Candidate

## Beta 2 handover

Beta 2 was accepted by the user on 30 July 2026 with all 142 guided checks
passed. RC1 is now feature-frozen and version-aligned. Source validation passes
all 272 tests. PyInstaller and Inno Setup have both produced an earlier RC1
binary candidate, but current acceptance work intentionally uses the
source-based `launcher.bat` package until the application is approved for its
final installer build.

The accepted Beta 1 package is now the baseline for Beta 2 reliability and
performance work. The application includes protected metadata/cover lookup,
multi-folder Preview All and Apply All, duplicate quarantine and restore,
actionable Library Health, Calibre/network integration, controlled plugins,
completed settings/guidance, and Windows packaging foundations. Use
`docs/R4-Beta2-Complete-Testing-Guide.md` for acceptance.

The test delivery intentionally starts with a new catalogue under
`%LOCALAPPDATA%\Twano`; the previous development catalogue remains untouched.
The distributed artefact is a validated source ZIP. A signed executable,
installer, and verified online update channel remain production release gates.

The latest Beta 2 acceptance fixes add bounded affected-item previews to every
Library Health card and A–Z/Z–A sorting to the approved Plugins list. The
Comic Vine and Hardcover API checks now also persist their real response
health. Metadata & Covers can search every active provider or one selected
provider, including a Comic Vine-only lookup. Numeric CBR/CBZ filenames now
provide series, publisher and issue-number terms for an exact Comic Vine issue
lookup. Cover thumbnails can now be clicked to open a larger screen-bounded
viewer. The Plugins table now includes the missing Version column, and Google
Images provider version 1.1 recognises current result markup while clearing
the obsolete version 1.0 layout warning for a fresh check. The current source
passed compilation and all 245 automated tests. The timestamped
`2026-07-30-2332` package and its clean extracted-package validation are
recorded in the master roadmap.

## Earlier RC6.7 handover record

## Final RC6.6 acceptance

- The user accepted the refreshed RC6.6 release candidate on 28 July 2026.
- Preserved package:
  `C:\Twano\Builds\Twano-R4-RC6.6-Safe-Scan-and-Import.zip`
- Preserved SHA256:
  `4C1117CC82801094671FF40B218532C3591E3A8A3A4C4B74D4A68A8C35B89CF7`
- RC6.7 development may proceed; the accepted RC6.6 ZIP and checksum must not
  be replaced.

## RC6.7 Milestone 1 — verified backup foundation

- `ProtectionService` owns immutable backup policies, records, status
  classification, SHA256 evidence, manifests, and final-file publication.
- `DatabaseManager.backup_database()` uses SQLite's online backup API; source
  and destination connections are created, used, and closed in the calling
  worker thread.
- `DatabaseManager.verify_database_backup()` opens backups read-only and runs
  `PRAGMA integrity_check`, with cancellable SQLite progress handling.
- Final backup and manifest names appear only after copy, integrity, and hash
  checks pass. Cancellation and failure remove exact partial and unpublished
  files.
- Protection preferences persist an absolute backup folder and retention age;
  `0` means Keep All. No automatic deletion is enabled yet.
- `BackupWorker` creates its service in a fresh `QThread`; completion, failure,
  and cancellation all terminate through `finished` without a GUI wait.
- The new responsive Protection & Undo destination creates, lists, and
  re-verifies backups. Restore, cleanup, operation history, and Undo are
  explicitly described as later RC6.7 work and have no premature controls.
- Restored and compact layouts reflow backup settings and action buttons so
  the right edge remains reachable.
- Full compile passes. The complete suite passes with 124 passed, 0 failed,
  and 0 skipped; all 105 accepted RC6.6 regressions remain green.
- Deterministic empty, verified restored, and verified compact Protection
  captures were generated and inspected.
- The user accepted this native checkpoint on 29 July 2026. Milestone 2
  change-plan and audit-history work then began.

## RC6.7 Milestone 2 — change plans and audit persistence

- `protection_models.py` defines frozen plan/item, risk, reversibility,
  confirmation, status, and operation-record contracts.
- Plans require readable intent, database/file item separation, warnings,
  affected counts, component, initiator, expiry, and a basis token.
- Confirmation validation rejects stale, expired, repeated, mismatched, and
  insufficiently confirmed high-risk plans.
- `protection_operations` and `protection_operation_items` are additive,
  preserve catalogue data, and retain original plan JSON plus outcome evidence.
- Preview and approval write audit intent only; neither can execute catalogue
  or ebook-file changes in Milestone 2.
- The Protection page offers an explicitly non-catalogue-changing Safety Check
  plan so preview, approval-only, cancellation, restart persistence, and
  reporting can be tested before real mutators integrate.
- Verified backup creation is now audited as applied, cancelled, or failed,
  including the final backup identity and exact cleanup/rollback evidence.
- Markdown report export runs in a worker thread and publishes atomically.
- Protection now uses Backups and Plans & History task tabs with no page-level
  scrollbar. Plan Preview and Operation History are separated, and secondary
  history columns are omitted at compact width. Plans & History is the default
  view so Preview, Approve, Apply, and Undo remain immediately discoverable.
- Home again uses a compact bookshelf hero and exactly three central cards;
  Find a Book remains below the hero and Check for Updates sits low in the
  sidebar.
- The full compile and 143-test suite pass: 143 passed, 0 failed, 0 skipped.
- Eight deterministic captures cover Home restored/compact, empty/verified
  backup, plan preview, cancelled history, restored layout, and compact
  layout.

## RC6.7 Milestone 3 — protected executor and persistent Undo

- The first executor accepts only the built-in `collection_create` plan with
  one exact reversible database item; arbitrary plan/file actions remain
  rejected.
- Apply validates Standard mode, approval evidence, expiry, current basis, and
  plan shape before and after creating a verified catalogue backup.
- Collection creation, inverse JSON, item outcome, and Applied status commit
  in one database transaction.
- Forced SQL failure rolls the entire mutation back and records Failed,
  verified backup identity, error summary, and rollback evidence separately.
- Preview Undo validates the persisted collection ID/name and empty state,
  then records a new plan linked to the source operation.
- Undo creates another verified backup and atomically removes the exact
  collection, marks its own operation Applied, and marks the source Undone.
- `ProtectionExecutorWorker` owns its service in a dedicated thread;
  cancellation is honoured before the atomic transaction.
- Plan Preview retains the no-page-scroll layout with Preview Safety, Preview
  Test Change, Preview Undo, Approve, Apply, and Cancel in two rows.
- Full compile and 152-test suite pass: 152 passed, 0 failed, 0 skipped.
- Twelve deterministic captures cover Home, backup, plan/history, protected
  Apply, Undo preview, and persistent Undo at restored/compact sizes.

## RC6.7 Milestone 4 — guided Restore and retention

- Routine Protection opens on **Backups & Restore**. Users select a backup and
  choose **Restore Backup**; one plain confirmation explains that Twano will
  recheck it and automatically create a safety copy first.
- The selected snapshot is fully reverified, staged beside the live database,
  integrity checked, hashed, flushed, and atomically published.
- A verified recovery backup of current state is mandatory. A post-swap
  failure automatically republishes that recovery copy and records the result.
- Restore runs in a worker, blocks in Read-Only mode, requires Scan and Library
  database work to be idle, locks navigation during replacement, and refreshes
  Library, Home, Scan, Review Queue, and Search afterward.
- **Review Old Backups** performs a background dry run and presents only the
  candidate count and total size before one confirmation.
- Cleanup accepts exact regular Twano backup/manifest pairs only and rechecks
  saved folder, age, identity, SQLite integrity, and SHA256. Unrelated,
  symbolic-link, recent, changed, invalid, legacy, and unverified files stay.
- Detailed plans, outcomes, recovery identities, and partial/rolled-back
  evidence remain in **Activity & Undo** without being required for routine
  Restore or cleanup.
- Eight focused service tests and two direct UI tests cover successful Restore,
  restart persistence, Read-Only rejection, stale backup rejection,
  cancellation, post-swap recovery, exact cleanup ownership, stale cleanup,
  cleanup rollback, and background one-confirmation workflows.
- Full compile and 162-test suite pass: 162 passed, 0 failed, 0 skipped.

## RC6.7 Milestone 5 — protected Scan Apply integration

- The accepted **Preview Scan → Apply Preview** interface remains unchanged:
  one readable confirmation covers rechecks, the automatic safety backup, and
  the catalogue update.
- `ScanService` records the confirmed immutable preview as one approved
  `scan_apply` operation inside the existing Apply worker thread.
- A verified catalogue backup is created automatically after final candidate
  rechecks and before the SQLite Apply transaction.
- `scan_history.protection_operation_id` is an additive nullable link; legacy
  Scan History remains valid without a protection record.
- Book/source changes, Scan History counts, operation-item outcomes, backup
  identity, and Applied status commit together in one database transaction.
- Cancelled and failed Apply attempts record matching linked terminal outcomes
  without a partial catalogue update.
- Read-Only mode disables **Apply Preview** and points directly to Settings.
- Scan now uses fitted **Sources**, **Preview & Apply**, and **History** task
  tabs instead of a page-level scrollbar. Compact tables stretch or omit
  secondary columns without horizontal scrolling.
- Activity & Undo uses the plain recovery label **No one-click Undo; safety
  backup available**. The backup supports explicit whole-catalogue Restore;
  Scan Apply does not claim narrow Undo.
- Eight focused tests cover additive migration, success and restart
  persistence, verified backup identity, cancellation, forced failure, stale
  source settings, Read-Only enforcement, and simple UI guidance.
- Full compile and the 170-test suite pass: 170 passed, 0 failed, 0 skipped.
- The 5,000-file scan validator completed with first protected Apply under
  0.9 seconds and changed protected Apply near 1.13 seconds.
- Restored and compact Sources, Preview & Apply, Scan History, and linked
  Activity & Undo captures were generated and inspected.

## Accepted baseline

- RC6.5 Living Library received final native acceptance on 28 July 2026.
- Preserved package:
  `C:\Twano\Builds\Twano-R4-RC6.5-Living-Library.zip`
- Preserved SHA256:
  `0D7B34A8B0D7D51596132ED8587C79AB1655620419137E529076D229AC3493E4`
- The accepted RC6.6 suite contains 105 passing tests.

## RC6.6 Milestone 1 — watched sources

- The existing `libraries` table now owns additive source name, enable state,
  recursion, include/exclude rules, archive state, and connection evidence.
- `ScanService` returns immutable source and connection values and validates
  absolute local, mapped-drive, and UNC-shaped paths.
- Disable and Remove Watch preserve all existing catalogue books.
- Archived paths can be restored without creating a second source identity.
- Connection tests perform read-only enumeration in a dedicated worker thread.
- Scan now lists watched sources and provides Add, Edit, Test Connection,
  Enable/Disable, and Remove Watch actions.
- The page scrolls vertically at constrained heights and hides secondary
  source columns in compact mode.
- The old immediate scan entry point remains internal regression coverage;
  watched sources use Safe Preview and guarded Apply.

## RC6.6 validation so far

- The accepted 81-test baseline passed before RC6.6 source changes.
- Seven focused source tests cover migration, lifecycle, book preservation,
  connection states, path/rule validation, UI actions, and background testing.
- Restored 1180 × 790 and compact 1000 × 720 source layouts were captured and
  inspected offscreen.
- Native source-management review through `launcher.bat` is the Milestone 1
  checkpoint.

## RC6.6 Milestones 2–3 — analysis and preview checkpoint

- `ScanService.analyse_source()` reads source and book snapshots and returns an
  immutable `ScanAnalysisResult`.
- Rules, recursion, repository-supported formats, size, modification time, and
  a fast size/mtime fingerprint drive classification.
- New, changed, unchanged, missing, unreadable, and skipped states are
  presented without updating any book, missing flag, source scan timestamp, or
  history record.
- Missing is inferred only after a complete connected walk. Cancellation,
  inaccessible folders, and unavailable sources suppress missing results.
- `ScanAnalysisWorker` performs analysis on a dedicated `QThread`.
- Scan shows a discardable preview and automatically scrolls to its result
  table.
- Restored and compact Safe Preview layouts were captured and inspected.
- The user accepted Safe Preview on Windows on 28 July 2026.

## RC6.6 Milestone 4 — transactional Apply and history checkpoint

- `ScanService.apply_analysis()` rejects incomplete, disconnected, cancelled,
  configuration-stale, and change-free previews.
- Every approved candidate is checked against the previewed catalogue facts
  and filesystem state before mutation, then checked again after metadata
  extraction.
- Vanished, reappeared, modified, duplicate, or catalogue-stale candidates are
  safely skipped rather than partially applied.
- `ScanApplyWorker` performs rechecks and new/changed metadata extraction on a
  dedicated `QThread`; cancellation before the transaction changes no books.
- `DatabaseManager.apply_scan_preview()` commits book changes, source result
  evidence, and one scan-history row in a single transaction.
- New books are inserted, changed books retain curated metadata when refreshed
  extraction has nothing stronger, unchanged books refresh last-seen evidence,
  and confirmed missing books are marked only from a complete preview.
- Scan displays recent applied, cancelled, failed, and safely skipped outcomes.
- Successful commits notify Library and Home to refresh; failed transactions
  explicitly report rollback.
- Ten focused Apply tests cover atomic outcomes, repeat scans, vanished and
  reappeared files, cancellation, forced rollback, and the complete UI path.
- Three hardening tests add duplicate-token rejection, stale-source-rule
  invalidation, and Apply-worker pre-cancellation coverage.
- The complete suite now passes: 105 passed, 0 failed, 0 skipped.
- Restored and compact Apply/history layouts were captured and inspected.
- Library details and Scan now use distinct, contrast-checked action colours;
  the common grey treatment is reserved for genuinely disabled buttons.
- The user accepted transactional Apply and scan history on Windows on
  28 July 2026.
- A representative 5,000-file source completed first Preview in 2,027.985 ms,
  first Apply in 937.522 ms, unchanged repeat Preview in 3,571.773 ms, and a
  changed Apply in 945.917 ms on the validation machine.

## RC6.6 release candidate

- Release ZIP:
  `C:\Twano\Builds\Twano-R4-RC6.6-Safe-Scan-and-Import.zip`
- The allowlisted archive contains 142 entries, all readable, with seven banner
  PNG files and no nested ZIP, Git, virtual environment, cache, bytecode,
  database, build, distribution, or test-runtime content.
- A clean temporary extraction compiled, passed all 105 tests, generated all
  six RC6.6 UI smoke captures, and identified itself as
  `R4 RC6.6 — Safe Scan and Import`.
- The external `.sha256` file beside the ZIP is the authoritative package
  checksum.
- RC6.7 began only after final RC6.6 release-candidate acceptance.

## RC6.5 completed

- Library now uses one paged `LibraryModel` shared by a painted cover grid and
  information-rich `QTableView`.
- View switching preserves the loaded records and shared selection without a
  presentation-only database query.
- Library database work runs through background query tasks in production;
  every `DatabaseManager` call still opens and closes its SQLite connection in
  the calling thread.
- Cover files decode to `QImage` outside the GUI thread. `QPixmap` conversion,
  bounded LRU storage, and widget updates remain on the GUI thread.
- The additive schema includes `series_number`, `collections`, and
  `book_collections`, with cascading foreign keys and filter/sort indexes.
- Library filters cover search, format, author, series, collection, location,
  and metadata status. Sort fields and directions are database allowlists.
- The single responsive details panel shows metadata, file state, issues, and
  collections. Restored windows retain the side panel even when the toolbar
  reflows. A compact book click gives the panel the full browser area and
  provides a Back action.
- Details actions precede long cover and metadata content and are constrained
  to the available panel width without horizontal scrolling.
- Collection operations change only SQLite membership. Open Book and Open
  Folder use shared helpers; Metadata and Review Issues only route to existing
  protected destinations.
- Library view, density, sort, direction, and details visibility preferences
  are validated, migrated, and persisted.

## RC6.5 validation

- `.\.venv\Scripts\python.exe -m compileall -q src tests` passes.
- `.\.venv\Scripts\python.exe -m pytest -v` passes: 81 passed, 0 failed,
  0 skipped.
- The 29 focused RC6.5 tests cover migration, collections, all allowed sorts,
  invalid sorts, paging, combined filters, preferences, model/view sharing,
  details routing, empty states, cache bounds, corrupt covers, stale results,
  Windows Explorer arguments, ebook-reader fallback behavior, compact
  right-edge containment, restored-window details visibility, and compact
  single-click details navigation.
- A deterministic 10,000-record run measured a 100-record initial query at
  18.539 ms, filtered/sorted query at 17.419 ms, incremental page at 21.532 ms,
  and first model/table render at 39.499 ms on the validation machine.
- Two hundred grid/list switches caused zero additional Library page queries.
- Offscreen smoke captures validated wide, 1180 x 790 restored, and compact
  grid/details geometry. Native Windows review through `launcher.bat` is still
  required before RC6.5 is marked accepted.

## Prior package — RC6.4

## RC6.4 completed

- Sidebar branding, navigation rows, protection panel, and typography now scale
  from both available width and height with emergency-only scrolling.
- Home cards and hero typography use shared clamped responsive helpers.
- The hero greeting uses natural label sizing and font metrics instead of a
  fixed painting rectangle.
- Home suggestions are a child overlay and never enter the dashboard layout.
- Search Results is a dedicated page with query retention, filter structure,
  detailed results, Library routing, and shared reader launching.
- Metadata insight actions route to a filtered, data-backed Review Queue.
- Main navigation and page registration use stable string IDs.
- Home renders all seven bundled banner artworks through validated fixed or
  rotate-on-startup preferences.
- Legacy banner modes migrate to the supported RC6.4 modes, and missing assets
  fall back without preventing Home from loading.

## RC6.4 validation

- `python -m compileall -q src tests` passes.
- The focused banner and RC6.4 UI suite passes: 15 passed.
- The complete suite passes: 55 passed, 0 failed, 0 skipped, 0 warnings.
- Banner, preference, and PySide6 regression coverage is included in the full
  suite using the pinned dependencies in `requirements.txt`.
- Offscreen visual renders cover 1280 Ã— 720 and 1920 Ã— 1080 geometry and
  artwork placement.
- The user confirmed the banner, responsive UI, navigation, and native
  Reading checks on Windows on 28 July 2026.
- The accepted ZIP was integrity-checked, extracted to a clean location, and
  smoke-launched with all seven banner assets present.

## Prior handover notes

## R4 RC6.1 — Responsive Home

- Rebuilt Home as a calm landing page rather than a statistics dashboard.
- Added square dark hero design, global book search, reader launching and Reading settings.
- Added Analytics navigation placeholder for RC7.
# PROJECT HANDOVER — R4 RC5.3 Living Dashboard

## Completed
- Responsive data-driven dashboard visuals using Qt painting.
- Top-card visuals appear only when the viewport has sufficient space.
- Lower cards show metadata health, format books, scan details and recent additions.
- Database dashboard query now includes sample locations and books needing metadata attention.

## Validation
- Python compilation passed.
- 28 non-UI tests passed.
- PySide6 UI tests require Windows validation.

## Test focus
- Compare maximised and smaller window sizes.
- Confirm compact mode hides top-card visuals without clipping text.
- Confirm metadata and format visuals reflect real library data.

## R4 RC6.2 update
The sidebar now uses the shared Twano Navigation System: responsive branding, large icons and text, grouped navigation, a prominent selected state, and a richer Protection Mode panel. User Guide, What's New and About remain available in the support group.

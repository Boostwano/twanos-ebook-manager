# Twano R4 RC6.6 — Safe Scan and Import

## Status

**In development from the accepted RC6.5 package.**

## Accepted source

```text
C:\Twano\Builds\Twano-R4-RC6.5-Living-Library.zip
SHA256 0D7B34A8B0D7D51596132ED8587C79AB1655620419137E529076D229AC3493E4
```

The accepted RC6.5 ZIP and checksum must remain unchanged while RC6.6 is in
development.

## Goal

Replace the current immediate scan-and-save flow with a predictable background
workflow that manages watched sources, analyses changes without mutating the
catalogue, presents an understandable preview, and applies only an explicitly
approved import.

## Existing behaviour and primary gap

RC6.5 already provides background discovery, cancellation, supported-format
detection, embedded metadata extraction, repeatable worker cleanup, and
database upserts. However, the current worker saves all discovered paths and
marks absent paths missing before the user sees the results. Cancellation
during later metadata processing can therefore leave legitimate but
unpreviewed catalogue changes.

RC6.6 must create a strict boundary:

```text
Source -> Analyse in worker -> Immutable preview -> Explicit apply -> SQLite
```

Analysis and cancellation before Apply must not change books, missing flags,
source scan timestamps, or scan history.

## Product guardrails

- Preserve the accepted RC6.5 Library, Home, search, reader, banner, and
  navigation behaviour.
- Keep dependency direction `UI -> Services -> Database -> SQLite`.
- UI modules must not contain SQL.
- Services must not depend on PySide6 widgets.
- Each SQLite connection must be created, used, and closed in one thread.
- Do not block the GUI thread or wait synchronously for a scan worker.
- Do not move, rename, overwrite, or delete ebook files in RC6.6.
- Removing a watched source must not cascade-delete its catalogue books.
- An unavailable source must never cause all of its books to be marked missing.
- A cancelled or failed analysis must remain safe to discard.
- All user-visible counts must distinguish analysed items from applied changes.

## Approved design decisions

### Watched-source lifecycle

The existing `libraries` table remains the source identity table and receives
additive source-management fields. Disable and Remove Watch are distinct:

- **Disable** keeps the source configured but excludes it from scans.
- **Remove Watch** archives the source configuration while preserving its
  books and history.
- Adding the same archived path restores that source rather than creating a
  duplicate.

Changing an existing source path is not allowed once it owns catalogue books.
Users may still edit its display name, recursion setting, and include/exclude
rules. This avoids silently reassigning old file paths.

### Path and connection handling

Local folders, drive-letter paths, mapped drives, and UNC strings use one
normalised path contract. A connection test opens and enumerates the source
root without writing to it. Results distinguish:

- available
- unavailable
- not a folder
- permission denied
- disabled

An availability failure is evidence about the source connection, not evidence
that every previously catalogued book was deleted.

### Source rules

Rules use simple semicolon-separated glob patterns stored as validated tuples
by the service layer:

- include patterns narrow supported ebook candidates
- exclude patterns skip matching relative paths or folder segments
- recursion may be disabled per source

Empty include rules mean all repository-supported ebook extensions. Rules do
not expand the configured supported-format set.

### Analysis and fingerprinting

Discovery produces detached candidates and issues. The fast fingerprint is
based on normalised path, file size, and modification time. SHA-256 may be
calculated only when required to distinguish ambiguous changes; RC6.6 must not
hash every large file without measured need.

Analysis classifies:

- new
- changed
- unchanged
- missing
- unreadable
- unsupported
- inaccessible

Missing classification is allowed only after a complete, connected source
walk. An interrupted or incomplete walk suppresses missing changes.

### Preview and apply

The preview is an immutable service result containing source identity, scan
token, completion state, item classifications, issues, and summary counts.
The Apply action sends that preview to one database transaction. Apply must:

- insert new books
- update changed books
- refresh last-seen data for unchanged books where appropriate
- mark missing books only after a complete connected scan
- skip unreadable or vanished candidates safely
- update source status and scan history

If a candidate disappears between preview and Apply, it is flagged/skipped and
must not corrupt or partially apply the transaction.

### Scan history

Store one history row per applied, cancelled, failed, or discarded analysis as
appropriate, without treating a preview as a book mutation. History records:

- source
- start and finish times
- status and duration
- discovered/new/changed/missing/unreadable/skipped counts
- concise error summary

## Required changes

### 1. Library sources

- Add additive source-management fields to `libraries`.
- Add immutable source and connection-test service values.
- Add, list, edit, enable/disable, archive, restore, and test source methods.
- Build a source table and focused source actions on Scan.
- Preserve books and history when a source is disabled or archived.

### 2. Discovery contract

- Move source rules and supported-format checks into `ScanService`.
- Report the current folder/file and discovery counts.
- Capture inaccessible folders and unreadable candidates instead of silently
  losing all diagnostic context.
- Honour cancellation throughout enumeration and fingerprint work.

### 3. Preview classification

- Compare candidates with detached existing-source snapshots.
- Produce immutable preview items and summary counts.
- Never mutate books during analysis.
- Suppress missing classification after incomplete or unavailable scans.

### 4. Preview UI

- Replace immediate result population with status-grouped preview rows.
- Show Added, Changed, Missing, Unreadable, Skipped, and Unchanged counts.
- Explain that Preview changes nothing.
- Enable Apply only for a complete valid preview with applicable changes.
- Allow the user to discard and rescan.

### 5. Transactional apply

- Apply an approved preview through one database-owned transaction.
- Recheck candidate existence where needed.
- Prevent duplicate rows on repeat scans.
- Keep cancellation before Apply mutation-free.
- Refresh Library and dashboard only after successful Apply.

### 6. History and failure guidance

- Add source-level last status, duration, counts, and error information.
- Add scan history records and an accessible history view or panel.
- Link failures to source connection testing and actionable issue details.
- Keep network interruption distinct from confirmed missing files.

## Automated validation

Add tests for:

- additive source migration from RC6.5
- source add/edit/disable/archive/restore behaviour
- book preservation when source watching is removed
- local, missing, non-folder, permission, mapped-drive, and UNC path handling
- include/exclude rules and recursion
- supported and unsupported detection
- immutable preview classification
- no database mutation during analysis or cancellation
- missing suppression after incomplete walks
- transactional apply and rollback
- repeated scans without duplicates
- vanished files between Preview and Apply
- history and source status counts
- QThread cancellation, cleanup, and repeated scan support
- Scan UI source selection, preview, Apply, discard, and compact layout

Required commands:

```text
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pytest -v
```

## Manual Windows validation

- Add a local source and verify its connection.
- Add or test a mapped-drive or UNC source when available.
- Edit source name and rules.
- Disable and re-enable a source.
- Remove Watch and confirm existing Library books remain.
- Analyse a folder and confirm Library counts do not change before Apply.
- Cancel discovery and confirm no catalogue changes.
- Review new, changed, missing, unreadable, and skipped preview states.
- Remove a candidate after Preview and confirm Apply reports it safely.
- Interrupt an unavailable/network source without marking all books missing.
- Apply a preview, refresh Library, and repeat the scan without duplicates.
- Close Twano during a scan without a thread warning or GUI freeze.

## Documentation and release records

Keep aligned:

- `README.md`
- `ARCHITECTURE.md`
- `CHANGELOG.md`
- `PROJECT_HANDOVER.md`
- `ROADMAP.md`
- `docs/architecture.md`
- `docs/database.md`
- `docs/roadmap.md`
- `prompts/roadmap.md`
- Master Delivery Roadmap
- RC6.6 test report and release notes

## Output package

```text
Twano-R4-RC6.6-Safe-Scan-and-Import.zip
```

## Non-goals

- ebook file rename, move, overwrite, or deletion
- metadata editing approval workflows
- general Undo implementation
- duplicate resolution
- Synology-specific APIs or cloud sync
- automatic scheduled scanning
- broad plugin hooks

## Exit criteria

- Source configuration is understandable and non-destructive.
- Analysis never changes the catalogue before explicit Apply.
- Scan operations remain responsive and cancellable.
- Cancelling or failing leaves the database consistent.
- Repeat scans do not create duplicates.
- Missing states require a complete connected source scan.
- Network interruption is reported without mass missing changes.
- History and source status provide useful evidence.
- Full automated, Windows, and package validation are recorded.

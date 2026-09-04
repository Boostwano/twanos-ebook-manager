# Twano R4 RC6.7 — Protection and Undo Foundation

## Status

**Milestone 5 Scan integration in validation from the accepted RC6.6
package.**

## Accepted source

```text
C:\Twano\Builds\Twano-R4-RC6.6-Safe-Scan-and-Import.zip
SHA256 4C1117CC82801094671FF40B218532C3591E3A8A3A4C4B74D4A68A8C35B89CF7
```

The accepted ZIP and checksum must remain unchanged during RC6.7 development.

## Goal

Create one reusable safety layer for future metadata, duplicate, catalogue, and
file operations. RC6.7 must make backups, plans, reversibility, execution
history, rollback evidence, and recovery understandable before later packages
gain broad write capabilities.

## Safety boundaries

- Preserve all accepted RC6.6 source, Preview, Apply, Library, Home, search,
  banner, reader, and responsive behavior.
- Keep dependency direction `UI -> Services -> Database -> SQLite`.
- UI modules contain no SQL.
- SQLite connections are created, used, and closed in one thread.
- Backup, verification, restore, export, and protected execution do not block
  the GUI thread.
- Do not modify ebook files in RC6.7 merely to demonstrate the framework.
- Never claim an operation is fully reversible unless its stored inverse and
  required backup material have been validated.
- Read-Only mode blocks protected mutations but permits backup, verification,
  history review, and report export.
- Backup retention is storage-aware and user controlled; it must not impose an
  unexplained small count limit.
- Restore never overwrites the live database without an additional recovery
  backup and explicit confirmation.

## Architecture

```text
Protection UI
  -> ProtectionService
    -> immutable policy / change-plan / operation values
    -> DatabaseManager for SQLite backup, integrity, audit, and transactions
    -> filesystem only for owned backup, manifest, and export artifacts
```

Later packages must submit changes to this layer instead of implementing their
own backup, confirmation, audit, or Undo mechanism.

## Deliverables

### 1. Protection Centre and backup policy

- Add a visible Protection & Undo destination.
- Persist an absolute backup location and retention age; zero days means keep
  all backups.
- Display the live catalogue path without exposing credentials.
- Create backups through SQLite's online backup API.
- Write a sidecar manifest containing creation time, source identity, size,
  SHA256, application version, and verification evidence.
- Verify SQLite integrity and manifest checksum.
- List backups with calm valid, changed, invalid, and legacy/unverified states.
- Keep creation and verification off the GUI thread and cancellable before
  completion.

### 2. Change-plan contract

- Add immutable operation, change, risk, and reversibility values.
- Require a human-readable title, summary, affected count, intended database
  changes, intended file changes, and warnings.
- Assign a unique plan token and detect stale or repeated application.
- High-risk plans require explicit confirmation.
- Plans remain mutation-free until protected execution.

### 3. Persistent audit model

- Add operation and operation-item tables additively.
- Store initiator, component, timestamps, status, risk, reversibility,
  affected books, backup identity, error summary, and rollback outcome.
- Keep operation details after restart.
- Provide a concise exportable report format.

### 4. Protected executor and persistent Undo

- Validate the approved plan and current protection mode.
- Create and verify the required database backup before significant mutation.
- Execute database changes in one transaction.
- Store inverse data for every operation labelled reversible.
- Record failed and rolled-back outcomes truthfully.
- Undo through a new protected operation so the original audit record remains.
- Permit redo only when it can be proven safe.

### 5. Restore and retention

- Validate backup integrity before restore.
- Create a recovery backup of the current live database.
- Restore only while no background database work is active.
- Reopen services cleanly after restore and refresh all dependent pages.
- Apply user-configured age retention only to Twano-owned verified backups.
- Present a dry-run cleanup summary before deletion.

### 6. RC6.6 integration

- Represent transactional Scan Apply through the common operation/audit layer.
- Preserve scan-specific history while linking it to the protected operation.
- Do not introduce a second competing history truth.

## First checkpoint

The first native checkpoint is intentionally limited to the backup foundation:

- open Protection & Undo
- choose or retain an absolute backup folder
- save the policy and confirm it survives restart
- create a verified database backup
- see the backup in the table with size, time, and verification status
- re-verify the selected backup
- cancel a backup without leaving a final or partial backup artifact

This first-checkpoint restriction is historical. Restore, Undo, retention
review, and Scan Apply protection integration are now implemented through
later RC6.7 milestones.

## Automated validation

Add coverage for:

- RC6.6 database compatibility
- policy validation, persistence, and invalid-value migration
- online backup consistency while the source database is open
- manifest SHA256 and SQLite integrity verification
- corrupt, modified, missing-manifest, and missing-file states
- cancellation and partial-file cleanup
- worker/thread cleanup and repeated backup support
- change-plan immutability and validation
- additive audit schema
- atomic protected execution and rollback
- Undo after service/application recreation
- restore into a clean environment
- retention dry-run and owned-file boundaries
- report export
- Protection Centre responsive layout and action states
- complete RC6.6 regressions

Required commands:

```text
.\.venv\Scripts\python.exe -m compileall -q src tests tools
.\.venv\Scripts\python.exe -m pytest -v
```

## Manual Windows validation

- Create and verify a backup through `launcher.bat`.
- Confirm the chosen backup location persists after restart.
- Cancel backup creation and confirm no final/partial artifact remains.
- Inspect invalid or modified backup guidance.
- Preview and cancel a protected change plan.
- Apply, restart, and Undo a reversible test operation.
- Export an operation report and open it.
- Restore a verified test backup only after a recovery backup is created.
- Confirm RC6.6 Scan, Apply, Library, and Home still work.
- Close during each background phase without GUI freeze or thread warnings.

## Output package

```text
Twano-R4-RC6.7-Protection-and-Undo-Foundation.zip
```

## Non-goals

- broad metadata editing
- duplicate resolution
- ebook rename, move, overwrite, or deletion
- cloud backup or synchronisation
- installer or automatic updates
- claiming arbitrary or infinite Undo retention

## Exit criteria

- A failed protected operation cannot leave partially committed database state
  without recorded recovery evidence.
- Verified backups restore in a clean test environment.
- Undo survives application restart.
- Audit history explains intended, applied, failed, undone, and rollback
  outcomes.
- Future write packages have one approved protection API to use.
- Full automated, Windows, performance, and package validation are recorded.

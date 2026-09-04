# Twano R4 RC6.6 Milestones Brief

**Release:** Twano R4 RC6.6 — Safe Scan and Import  
**Status:** Accepted on Windows on 28 July 2026

## Milestone 0 — Accepted baseline and contract

- Preserve the accepted RC6.5 ZIP and checksum.
- Record the final RC6.5 native acceptance.
- Run the complete 81-test baseline.
- Audit current scan mutation timing, cancellation, and database behavior.
- Approve the RC6.6 change specification and this brief.

Exit:

- RC6.5 remains reproducible and unchanged in Builds.
- The analyse/preview/apply safety boundary is explicit.
- Existing gaps are recorded without overstating RC6.6 readiness.

Status: complete.

## Milestone 1 — Watched library sources

- Extend `libraries` additively with source-management fields.
- Add detached source records and connection-test results.
- Add source creation, editing, enable/disable, archive/restore, and listing.
- Preserve catalogued books when Remove Watch is used.
- Add recursion and include/exclude rules.
- Add source management and connection testing to the Scan page.

Exit:

- Local and UNC-shaped paths use one validated service contract.
- Unavailable, non-folder, permission, disabled, and available states are
  distinct.
- Editing rules cannot silently relocate existing catalogue books.
- Disable and Remove Watch never delete books.
- Focused database, service, and UI tests pass.

Status: accepted on Windows on 28 July 2026.

## Milestone 2 — Background analysis and diagnostics

- Introduce immutable scan candidate, issue, and analysis values.
- Apply recursion and source rules during discovery.
- Add file modification and fast fingerprint information.
- Report current folder/file and inaccessible paths.
- Compare discovery with existing source records without mutation.
- Suppress missing classification after incomplete scans.

Exit:

- Analysis classifies new, changed, unchanged, missing, and unreadable items.
- Cancellation and connection failures produce no book or missing-flag writes.
- Large discovery remains off the GUI thread.

Status: accepted on Windows on 28 July 2026.

## Milestone 3 — Import preview

- Replace immediate scan results with a grouped preview.
- Show meaningful summary counts and issue explanations.
- Add Discard, Rescan, and Apply actions.
- Keep Apply disabled for cancelled, incomplete, or invalid previews.
- Handle files disappearing after preview.

Exit:

- Users can understand intended database changes before Apply.
- Library and dashboard counts remain unchanged while previewing.
- Compact and restored window layouts retain all preview actions.

Status: Safe Preview accepted on Windows on 28 July 2026. File rechecks and
Apply are implemented in Milestone 4.

## Milestone 4 — Transactional apply and scan history

- Add one database transaction for approved preview application.
- Add source last-result fields and scan-history records.
- Refresh metadata only for new or changed candidates.
- Preserve unchanged metadata.
- Prevent duplicate paths on repeat apply.
- Record applied, cancelled, failed, and safely skipped outcomes.

Exit:

- Apply is atomic and rollback-safe.
- Repeat scans create no duplicate books.
- Complete connected scans may mark confirmed missing books.
- Unavailable sources cannot cause mass missing changes.
- History counts match applied outcomes.

Status: accepted on Windows on 28 July 2026.

## Milestone 5 — Hardening and package gate

- Exercise local, mapped-drive-shaped, and UNC-shaped source paths.
- Validate cancellation and shutdown during each worker phase.
- Run representative large-source performance checks.
- Run compilation, focused tests, and the full regression suite.
- Complete Windows source, preview, apply, and interruption checks.
- Update version, architecture, database, release, and handover documents.
- Build, inspect, extract, test, and launch the RC6.6 ZIP.

Exit:

- RC6.6 change specification is satisfied.
- No unresolved data-integrity, UI-thread, cancellation, or network-source
  blocker remains.
- Human review accepts the package before RC6.7 begins.

Status: complete and accepted on Windows on 28 July 2026.

## Expected implementation files

### Existing files likely to change

- `src/config.py`
- `src/database/database.py`
- `src/services/scan_service.py`
- `src/workers/scan_worker.py`
- `src/ui/scan_page.py`
- `src/main_window.py`
- `tests/test_database.py`
- `tests/test_services.py`
- `tests/test_scan_lifecycle.py`
- relevant README, architecture, database, roadmap, release, and handover files

### Focused new files likely to be added

- `tests/test_rc6_6_sources.py`
- `tests/test_rc6_6_scan_analysis.py`
- `tests/test_rc6_6_scan_apply.py`
- `docs/RC6.6-Test-Report.md`
- `docs/RELEASE_NOTES_R4_RC6_6.md`

Prefer extending the existing Scan service, worker, and page. Do not create a
parallel scan subsystem or put SQL in UI code.

## First native checkpoint — accepted

After Milestone 1, verify only:

- adding a watched source
- selecting it in the source table
- testing its connection
- editing its name and rules
- disabling and re-enabling it
- removing the watch without removing Library books

## Safe Preview native checkpoint — accepted

- select an available watched source and run Preview Scan
- verify summary counts and status rows
- verify Library and Home counts do not change
- discard the preview and confirm the result clears
- cancel a preview and confirm no missing inference is reported
- verify restored and compact layouts retain all actions

Accepted on Windows on 28 July 2026.

## Transactional Apply native checkpoint

- use a disposable watched folder and run Preview Scan
- confirm Apply Preview is enabled only when changes are present
- Apply the preview and confirm applied counts match the intended changes
- confirm the books appear in Library and Home refreshes after commit
- run Preview Scan again and confirm no duplicate books are proposed
- remove a newly previewed candidate before Apply and confirm it is safely
  skipped
- confirm Recent Scan History shows the applied and safely skipped outcomes
- cancel an Apply during its recheck phase and confirm no books changed
- verify restored and compact layouts retain Apply and history

Accepted on Windows on 28 July 2026.

# Twano R4 RC6.7 Test Report

**Package:** Protection and Undo Foundation  
**Status:** Milestones 1–4 accepted; Milestone 5 in validation  
**Accepted baseline:** RC6.6, SHA256
`4C1117CC82801094671FF40B218532C3591E3A8A3A4C4B74D4A68A8C35B89CF7`

## Milestone 1 scope

- persistent absolute backup folder and storage-aware retention age
- online backup of the open SQLite catalogue
- SQLite integrity and SHA256 manifest evidence
- truthful backup inspection and full re-verification
- cancellable background creation and verification
- exact cleanup after cancellation or failure
- responsive Protection & Undo presentation

Restore, automatic retention deletion, operation history, and Undo are not
exposed in this checkpoint.

## Focused automated coverage

Nineteen RC6.7 tests cover:

- preference round-trip, Keep All, invalid migration, and rejected values
- absolute policy paths and retention boundaries
- consistency while the source database remains open
- unique repeated backups and ordered listing
- manifest filename, size, integrity evidence, and SHA256
- changed, corrupt, legacy/unverified, and missing evidence paths
- pre-copy and in-copy cancellation cleanup
- simulated failure cleanup
- worker cleanup across repeated create and verify runs
- saved policy after page/service recreation
- explicit action IDs and unavailable-feature boundary
- compact right-edge control containment
- Protection navigation at minimum supported height

## Commands

```text
.\.venv\Scripts\python.exe -m compileall -q src tests tools
.\.venv\Scripts\python.exe -m pytest -v
```

Result on 28 July 2026:

- compile: passed
- tests: **124 passed, 0 failed, 0 skipped**
- duration: 8.78 seconds
- the 105 accepted RC6.6 tests remain green

## Visual checkpoint

Deterministic restored and compact captures are generated with:

```text
.\.venv\Scripts\python.exe tools\capture_rc6_7_protection.py OUTPUT_FOLDER
```

The restored layout shows policy, distinct backup actions, progress, evidence,
and table together. At compact size the policy and action rows reflow
vertically so the right edge remains reachable.

Three screenshots were generated and inspected: empty restored, verified
restored, and verified compact. The first capture exposed a compact right-edge
overflow; the policy and actions were reflowed, and the corrected capture plus
automated containment test passed.

## Native checkpoint

Run `launcher.bat`, open **Protection & Undo**, then:

1. Retain the default backup folder or choose another absolute folder.
2. Leave retention at **Keep all backups** or choose an age and save.
3. Select **Create Verified Backup**.
4. Confirm a row appears as **Verified**.
5. Select the row and choose **Verify Selected Backup**.
6. Restart Twano and confirm the saved folder and retention remain.

Restore and automatic cleanup must not appear yet.

## Milestone 1 native acceptance

The user accepted the verified-backup checkpoint on Windows on 29 July 2026.
RC6.7 advanced directly to Milestone 2. The accepted RC6.6 ZIP and checksum
remain unchanged.

## Milestone 2 scope

- immutable change-plan and item contracts
- risk, reversibility, confirmation, expiry, and basis validation
- stale, repeated, expired, mismatched, and high-risk rejection
- additive operation and operation-item persistence
- readable preview, approval-only, and cancellation outcomes
- restart-persistent history and selected-plan evidence
- verified-backup audit integration
- background atomic Markdown report export

At this historical Milestone 2 checkpoint, protected Apply, inverse-data
execution, Undo, restore, retention cleanup, and Scan Apply integration
remained unavailable.

## Milestone 2 focused coverage

Eighteen focused tests cover:

- frozen plan and item values plus JSON round-trip
- required readable intent, target separation, and affected counts
- explicit and typed high-risk confirmation
- exact token, basis, expiry, and repeat protection
- additive schema creation with existing catalogue preservation
- atomic plan/item persistence and service recreation
- optimistic approval/cancellation transitions
- backup applied/cancelled evidence and backup identity
- readable atomic report export, overwrite refusal, and cancellation cleanup
- visible preview, approval-only, cancellation, and restart persistence
- worker-thread report export and repeated cleanup
- action identifiers, compact reflow, and zero page-level horizontal overflow

## Milestone 2 validation

Commands:

```text
python -m compileall -q src tests tools
python -m pytest -v
```

Result on 29 July 2026:

- compile: passed
- tests: **143 passed, 0 failed, 0 skipped**
- duration: 15.50 seconds
- all 105 accepted RC6.6 regressions remain green
- an initial full run exposed three legacy Home tests using the real user
  catalogue through default background services
- those tests were isolated onto temporary databases; the complete rerun
  passed

Eight deterministic captures now include refreshed Home restored/compact,
change-plan preview, cancelled operation history, and compact history
alongside the three backup captures.
The first Milestone 2 captures exposed page-level horizontal overflow caused
by long path and action size hints; the content policy and compact reflow were
corrected, recaptured, and covered by automated assertions.

The follow-up UI pass removed the Protection page scroll area entirely.
Backups and Plans & History now use task tabs, with Plan Preview and Operation
History separated inside the latter. Plans & History opens by default so the
Preview, Approve, Apply, and Undo workflow is visible without first finding a
secondary task tab. At compact width, secondary history columns are omitted
because the same facts remain in Plan Preview. Home again uses a compact
bookshelf hero and exactly three central cards, with Find a Book retained
below the hero and Check for Updates moved to the lower sidebar.

## Milestone 2 native checkpoint

Run `launcher.bat`, open **Protection & Undo**, then select
**Plans & History**:

1. On **Plan Preview**, select **Preview Safety Check**.
2. Confirm the preview says no catalogue, metadata, or ebook-file change will
   run.
3. Select **Cancel Plan** and confirm the row changes to **Cancelled**.
4. Preview a second Safety Check and select **Approve Plan**.
5. Confirm it reports that nothing was applied.
6. Open **Operation History**, restart Twano, and confirm both rows remain.
7. Select a row, export its report, and open the Markdown file.
8. Create another verified backup and confirm an **Applied** backup operation
   appears with its backup identity.

This was the historical Milestone 2 boundary; protected Apply and Undo are
covered by Milestone 3 below.

## Milestone 3 scope

- one allowlisted reversible collection-create test operation
- current-basis and exact-plan revalidation at approval and Apply
- Standard-mode enforcement in both UI and service
- verified pre-change backup with recorded identity
- one atomic database-and-audit transaction
- schema-validated persistent inverse JSON
- Undo preview as a new source-linked audited operation
- restart-persistent Apply and Undo outcomes
- background execution with cancellation before mutation
- truthful failed and rolled-back evidence

Restore, retention cleanup, redo, ebook-file execution, and Scan Apply
integration remain unavailable.

## Milestone 3 focused coverage

Nine new focused tests cover:

- verified backup before protected Apply
- exact stored collection inverse data
- Read-Only rejection before backup or mutation
- approved non-allowlisted plans being rejected before backup or mutation
- stale collection-basis rejection
- forced mid-transaction failure with complete rollback evidence
- cancellation that leaves an approved plan retryable
- Apply, service recreation, Undo, and preserved linked audit records
- stale Undo rejection after the target collection changes
- background UI Apply/Undo lifecycle, backup-table refresh, and action states

## Milestone 3 validation

Commands:

```text
.\.venv\Scripts\python.exe -m compileall -q src tests tools
.\.venv\Scripts\python.exe -m pytest -v
```

Result on 29 July 2026:

- compile: passed
- tests: **152 passed, 0 failed, 0 skipped**
- final full-run duration: 16.83 seconds
- all 143 Milestone 2 tests remain green

Twelve deterministic captures now include Home, backup, Safety Check,
operation history, reversible-plan preview, protected Apply, Undo preview, and
persistent Undo at restored and compact widths. The Plan Preview page retains
its no-page-scroll layout with six distinct actions arranged in two rows.

## Milestone 3 native checkpoint

Run `launcher.bat`, ensure **Settings → Home → Protection Mode** is
**Standard**, then open **Protection & Undo → Plans & History**:

1. Select **Preview Test Change** and inspect the exact empty collection name.
2. Select **Approve Plan** and confirm nothing changes yet.
3. Select **Apply Plan** and approve the final prompt.
4. Confirm the plan becomes **Applied**, its verified backup is recorded, and
   the empty collection appears in Library collection choices.
5. Restart Twano, select that Applied operation in **Operation History**, then
   return to **Plan Preview**.
6. Select **Preview Undo**, inspect the linked source operation, then
   **Approve Plan** and **Apply Plan**.
7. Confirm the Undo record is **Applied**, the source record is **Undone**, and
   the test collection is gone.
8. Switch Protection Mode to **Read-Only** and confirm Apply is unavailable.

No ebook file is changed by this checkpoint.

## Milestone 4 scope

- one plain **Restore Backup** confirmation instead of a user-managed
  preview/approval/apply sequence
- full selected-backup re-verification before replacement
- automatic verified recovery backup of current live state
- staged same-folder integrity, SHA256, and flush checks before `os.replace`
- automatic pre-restore recovery after a forced post-swap failure
- embedded backup-audit reconciliation and restart-persistent Restore evidence
- Scan/Library database-idle gate plus navigation lock during replacement
- dependent page refresh after successful Restore
- background **Review Old Backups** dry run with candidate count and total size
- exact regular owned backup/manifest allowlist, full re-verification,
  quarantine, rollback, and truthful partial evidence

## Milestone 4 focused coverage

Ten new focused tests cover:

- successful Restore, recovery backup contents, stored recovery identity, and
  history after service recreation
- Read-Only rejection before recovery or replacement
- changed selected-backup rejection
- cancellation before replacement with an approved retryable operation
- forced post-swap failure and automatic recovery of current catalogue state
- retention dry run and deletion of only an expired verified owned pair
- preservation of recent, unrelated, and unverified files
- stale retention-candidate rejection
- forced cleanup move failure with full artifact return and Rolled Back history
- direct background UI Restore and cleanup using one readable confirmation each

## Milestone 4 validation

Commands:

```text
.\.venv\Scripts\python.exe -m compileall -q src tests tools
.\.venv\Scripts\python.exe -m pytest -v
```

Result on 29 July 2026:

- compile: passed
- tests: **162 passed, 0 failed, 0 skipped**
- all 152 Milestone 3 tests remain green

The deterministic Protection captures were regenerated after the simplified
UI pass. **Backups & Restore** fits at restored and 900 x 600 sizes with all
five actions visible, no page-level scrollbar, and the progress bar hidden
when work is idle. **Activity & Undo** retains the existing compact history
and details layouts.

## Milestone 4 native checkpoint

Run `launcher.bat`, ensure protection mode is **Standard**, then open
**Protection & Undo → Backups & Restore**:

1. Create a new backup while the catalogue contains a recognisable temporary
   collection.
2. Change that temporary collection, select the earlier backup, and choose
   **Restore Backup**.
3. Confirm the single readable prompt. Twano should finish with
   **Catalogue restored** and add a newer safety backup automatically.
4. Confirm the catalogue matches the selected backup and ebook files are
   untouched.
5. Set **Keep backups for** to a small test age only if an expendable old
   Twano backup is available, then choose **Review Old Backups**.
6. Confirm the summary shows a count and size before deletion. Cancel once,
   then repeat and approve only if the listed test backup is expendable.
7. Confirm unrelated files in the backup folder remain and Activity & Undo
   records the outcome.
8. Switch to **Read-Only** and confirm Restore and cleanup are blocked.

## Milestone 5 scope

- preserve the existing one-confirmation Preview Scan and Apply workflow
- record the confirmed immutable preview in common protection history
- create a verified catalogue backup automatically before Apply
- add one nullable persistent link from Scan History to the protection
  operation
- commit catalogue changes, scan counts, backup identity, and protection
  outcome as one transaction
- record matching cancellation and failure outcomes without partial mutation
- keep Scan-specific classifications and counts in Scan History
- label recovery accurately without claiming one-click Undo
- separate Sources, Preview & Apply, and History so the page does not scroll

## Milestone 5 focused coverage

Eight focused tests cover:

- additive migration of legacy Scan History with a null operation link
- successful Apply, linked histories, verified backup, and restart persistence
- one and only one Scan Apply protection record for the confirmed preview
- cancellation before backup with matching non-mutating terminal outcomes
- forced Apply failure after backup with no partial catalogue update and
  retained recovery evidence
- stale source settings rejected before backup with linked failure evidence
- Read-Only rejection before plan, backup, or mutation
- simple Scan-page Standard-mode guidance without another approval screen
- restored and compact task-tab containment without page or table horizontal
  scrolling

Existing RC6.6 Scan Apply tests continue to exercise classifications, counts,
stale candidates, duplicate tokens, cancellation, atomic SQL rollback, worker
cleanup, and the native-facing page flow.

## Milestone 5 validation

Commands:

```text
.\.venv\Scripts\python.exe -m compileall -q src tests tools
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe tools\validate_rc6_6_scan.py
```

Result on 29 July 2026:

- compile: passed
- tests: **170 passed, 0 failed, 0 skipped**
- all 162 Milestone 4 tests remain green
- 5,000-file validation: first protected Apply 898 ms; changed protected Apply
  1,130 ms; two history rows; 5,050 active books; repeated processing created
  no duplicate catalogue records

Deterministic restored and compact captures cover Sources, Preview & Apply,
Scan History, and the linked Activity & Undo entry. All three Scan tasks fit
without a page-level scrollbar; compact source, result, and history tables do
not require horizontal scrolling.

## Milestone 5 native checkpoint

Run `launcher.bat`, then:

1. Set **Settings → Protection Mode** to **Standard**.
2. Open **Scan**, choose a safe test source, and run **Preview Scan**.
3. Choose **Apply Preview**. Confirm the single prompt mentions an automatic
   safety backup and that ebook files are unchanged.
4. Confirm Apply completes and Recent Scan History retains the expected New,
   Changed, Missing, and Safely skipped counts.
5. Open **Protection & Undo**. Confirm the fresh safety backup is Verified.
6. On **Activity & Undo**, select the Scan Apply entry and confirm it says
   **No one-click Undo; safety backup available**.
7. Switch to **Read-Only**, create another preview, and confirm Apply is
   unavailable with a direct Settings hint.

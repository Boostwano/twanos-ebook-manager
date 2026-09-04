# Twano R4 RC6.7 Milestones Brief

**Release:** Twano R4 RC6.7 — Protection and Undo Foundation  
**Status:** Milestone 5 — automated and visual validation complete; native
checkpoint pending

## Milestone 0 — Accepted baseline and contract

- Preserve the accepted RC6.6 ZIP and checksum.
- Record final RC6.6 native and package acceptance.
- Run the complete 105-test baseline.
- Audit existing database and file mutation paths.
- Approve the RC6.7 change specification and this brief.

Exit:

- RC6.6 remains reproducible and unchanged in Builds.
- RC6.7 safety boundaries and non-goals are explicit.
- Existing mutations are catalogued before integration work.

Status: complete.

## Milestone 1 — Protection Centre and verified backups

- Add persistent backup folder and retention-age policy.
- Add SQLite online backup and integrity verification in the database layer.
- Add immutable backup records and manifests with SHA256 evidence.
- Add cancellable background create and verify workers.
- Add a responsive Protection & Undo page with backup actions and status table.
- Keep restore and automatic retention deletion unavailable.

Exit:

- A backup of the live catalogue can be created without closing Twano.
- The final backup and manifest are written only after successful verification.
- Cancellation and failure leave no final or partial backup.
- Modified and corrupt backups do not display as verified.
- Settings survive restart.
- Repeated backup and verification worker cleanup is safe.

Status: accepted on Windows on 29 July 2026.

Automated gate: 124 passed, 0 failed, 0 skipped on 28 July 2026.

## Milestone 2 — Change plans and audit persistence

- Add immutable plan, item, risk, reversibility, and confirmation values.
- Add additive operation and operation-item tables.
- Add a human-readable plan preview.
- Add persistent operation-history presentation and report export.

Exit:

- Plans are detached, understandable, and mutation-free.
- High-risk plans cannot proceed without explicit approval.
- Audit records survive restart and explain their initiator and outcome.

Status: accepted by the user on Windows on 29 July 2026.

Automated gate: 143 passed, 0 failed, 0 skipped on 29 July 2026.

## Milestone 3 — Protected executor and Undo

- Add one executor for approved database change plans.
- Create a verified backup before significant operations.
- Store validated inverse data for reversible operations.
- Add Undo as a new audited protected operation.
- Add truthful failure and rollback evidence.

Exit:

- Apply and Undo are atomic.
- Undo survives application restart.
- A failed operation has recovery evidence and no silent partial state.

Status: accepted by the user on Windows on 29 July 2026.

Automated gate: 152 passed, 0 failed, 0 skipped on 29 July 2026.

## Milestone 4 — Restore and retention

- Add verified backup restore with explicit warnings.
- Create a recovery backup before replacing live state.
- Refresh services and UI after restore.
- Add retention dry-run, owned-file validation, and cleanup controls.

Exit:

- A verified backup restores in a clean environment.
- Restore failure preserves the pre-restore recovery path.
- Retention never deletes unrelated files or unverified backups.

Status: accepted by the user on Windows on 29 July 2026.

Automated gate: 162 passed, 0 failed, 0 skipped on 29 July 2026.

## Milestone 5 — Scan integration

- Adapt RC6.6 Apply to the common plan/executor/audit layer.
- Link scan history to protected operation identity.
- Preserve scan-specific classifications and counts.
- Keep the existing one-confirmation Scan workflow; do not expose plan or
  approval mechanics on the Scan page.
- Fit Sources, Preview & Apply, and History into task tabs without a
  page-level scrollbar.
- Create a verified catalogue safety backup automatically before Apply.
- Label recovery accurately: no one-click Undo; whole-catalogue Restore remains
  available from the safety backup.

Exit:

- Scan Apply retains accepted behavior.
- Protection history and scan history agree without duplicate truth.
- Undo support is labelled accurately for catalogue imports.

Status: automated and visual validation complete; native `launcher.bat`
checkpoint pending.

Automated gate: 170 passed, 0 failed, 0 skipped on 29 July 2026.

## Milestone 6 — Hardening and package gate

- Exercise local, mapped-drive-shaped, and UNC-shaped backup locations.
- Validate cancellation and shutdown in every worker phase.
- Run large-database backup, verification, restore, and Undo observations.
- Run complete compilation and regression tests.
- Complete native Protection Centre, plan, Undo, restore, and export checks.
- Build, inspect, extract, test, and launch the RC6.7 ZIP.

Exit:

- RC6.7 change specification is satisfied.
- No unresolved data-integrity, recovery, threading, or misleading-
  reversibility blocker remains.
- Human review accepts the package before RC6.8 begins.

## Expected implementation files

### Existing

- `src/config.py`
- `src/preferences.py`
- `src/database/database.py`
- `src/main_window.py`
- `src/ui/settings.py`
- `src/ui/sidebar.py`
- `src/ui/theme.py`
- RC6.7 architecture, database, roadmap, release, test, and handover documents

### Focused new files

- `src/services/protection_service.py`
- `src/workers/backup_worker.py`
- `src/ui/protection_page.py`
- `tests/test_rc6_7_preferences.py`
- `tests/test_rc6_7_backups.py`
- `tests/test_rc6_7_protection_ui.py`
- later milestone-specific plan, executor, Undo, restore, and audit tests

## Current native checkpoint

Run `launcher.bat`, then:

- ensure **Settings → Protection Mode** is **Standard**
- open **Scan**, choose an expendable test source, and run **Preview Scan**
- choose **Apply Preview** and confirm the one readable prompt mentions the
  automatic safety backup
- confirm Apply completes and Recent Scan History shows the same new, changed,
  missing, and safely skipped counts as before
- open **Protection & Undo** and confirm the new backup is Verified
- on **Activity & Undo**, confirm the Scan Apply entry says there is no
  one-click Undo and that a safety backup is available
- switch to **Read-Only** and confirm **Apply Preview** is unavailable with a
  direct Settings hint

# Twano R4 RC6.6 Test Report

**Package:** Safe Scan and Import  
**Checkpoint:** Milestone 5 — Hardening and Package Gate  
**Status:** Accepted on Windows on 28 July 2026

## Accepted baseline

```text
C:\Twano\Builds\Twano-R4-RC6.5-Living-Library.zip
SHA256 0D7B34A8B0D7D51596132ED8587C79AB1655620419137E529076D229AC3493E4
```

Baseline commands:

```text
.\.venv\Scripts\python.exe -m compileall -q src tests
Passed

.\.venv\Scripts\python.exe -m pytest -v
81 passed
0 failed
0 skipped
```

## Milestone 1 automated validation

```text
.\.venv\Scripts\python.exe -m compileall -q src tests
Passed

.\.venv\Scripts\python.exe -m pytest -v
88 passed
0 failed
0 skipped
```

Seven focused RC6.6 tests cover:

- additive RC6.5 source migration and safe defaults
- source add, duplicate rejection, edit, disable, enable, archive, and restore
- preservation of related catalogue books during Remove Watch
- available, unavailable, non-folder, disabled, and permission-denied states
- persisted connection evidence without book mutation
- absolute local, mapped-drive-shaped, and UNC-shaped path validation
- source-relative include/exclude pattern validation and de-duplication
- Scan-page selection, source actions, and non-destructive removal
- connection testing on a dedicated Qt worker thread

The user accepted the native watched-source checkpoint on 28 July 2026.

## Analysis and preview automated validation

```text
.\.venv\Scripts\python.exe -m compileall -q src tests
Passed

.\.venv\Scripts\python.exe -m pytest -v
95 passed
0 failed
0 skipped
```

Seven additional analysis tests cover:

- new, changed, unchanged, and missing classification
- skipped unsupported files
- unchanged source and book rows after preview
- include, exclude, and recursion scope
- cancellation without missing inference or database mutation
- unavailable-source protection against mass missing results
- explicit unreadable-file diagnostics
- preview UI completion, guarded Apply eligibility, and discard
- worker pre-cancellation and terminal cleanup

The complete suite retains all accepted RC6.4 and RC6.5 regressions, including
Library paging, restored-window details, reader launching, collection
membership, banner validation, and existing scan worker cleanup.

The user accepted the native Safe Preview checkpoint on 28 July 2026.

## Transactional Apply automated validation

```text
.\.venv\Scripts\python.exe -m compileall -q src tests
Passed

.\.venv\Scripts\python.exe -m pytest -v
102 passed
0 failed
0 skipped
```

Ten Apply tests cover:

- atomic new, changed, missing, unchanged-refresh, source, and history outcomes
- preservation of curated metadata when changed-file extraction has nothing
  stronger
- repeat preview behavior without duplicate paths
- vanished candidates safely skipped between Preview and Apply
- reappeared missing candidates protected from incorrect missing flags
- cancellation before mutation with a cancelled history outcome
- forced SQL failure rolling back both books and history
- the complete background UI Apply, refresh signal, and history path
- repeat use of one preview token being rejected without duplicates
- source-setting changes invalidating a stale preview
- pre-cancellation through the actual Apply worker and terminal cleanup

## Hardening and performance validation

The complete suite after hardening:

```text
.\.venv\Scripts\python.exe -m compileall -q src tests
Passed

.\.venv\Scripts\python.exe -m pytest -v
105 passed
0 failed
0 skipped
```

Representative source command:

```text
.\.venv\Scripts\python.exe tools\validate_rc6_6_scan.py
```

Measured on the validation machine on 28 July 2026:

| Observation | Result |
| --- | ---: |
| Supported source files | 5,000 |
| Unsupported files in changed run | 100 |
| File creation | 2,158.620 ms |
| First preview, 5,000 new | 2,027.985 ms |
| First transactional Apply | 937.522 ms |
| Unchanged repeat preview | 3,571.773 ms |
| Changed preview | 3,637.919 ms |
| Changed transactional Apply | 945.917 ms |
| Cancellation after 100 discoveries | 858.793 ms |
| Unavailable-source result | 0.754 ms |
| Final active/total catalogue books | 5,050 / 5,074 |
| Applied history rows | 2 |
| Vanished/reappeared candidates safely skipped | 2 |

The validation asserts classification counts, repeat-scan identity, safe
missing behavior, cancellation without missing inference, unavailable-source
protection, final active/total counts, and matching history. Timings are
observations from one machine, not universal performance guarantees.

## Offscreen UI validation

Command:

```text
.\.venv\Scripts\python.exe tools\capture_rc6_6_sources.py OUTPUT_FOLDER
```

The deterministic smoke run:

- created available, unavailable, and disabled sources in a temporary database
- selected an available source
- displayed source state, watch state, rules, and last-scan columns
- displayed Add, Edit, Test Connection, Disable, and Remove Watch actions
- captured and inspected the restored 1180 × 790 layout
- captured and inspected the compact 1000 × 720 layout
- confirmed the page scrolls vertically rather than overlapping controls
- confirmed compact mode hides secondary Rules and Last scan columns
- generated a complete preview containing New, Changed, Missing, Unchanged,
  and Skipped outcomes
- confirmed the preview automatically scrolls into view
- confirmed Apply is enabled only for a complete preview with changes
- captured and inspected restored and compact Safe Preview layouts
- applied the deterministic preview through the background worker
- confirmed the result table identifies applied outcomes
- confirmed Recent Scan History contains matching counts
- captured and inspected restored and compact Apply/history layouts
- confirmed distinct enabled action colours on Library details and Scan while
  disabled actions retain the subdued unavailable state
- confirmed every enabled action background retains at least 4.5:1 contrast
  with white text
- closed without a worker or thread warning

Offscreen font rasterization does not replace native Windows text and keyboard
review.

## Package validation

Final source release:

```text
C:\Twano\Builds\Twano-R4-RC6.6-Safe-Scan-and-Import.zip
```

The allowlisted package builder and clean-extraction validator confirmed:

- 142 source-release entries
- every ZIP entry opened and read successfully
- all required RC6.6 source, worker, test, launcher, release, and validation
  files are present
- 7 expected banner PNG files
- 0 nested ZIP files
- 0 Git, virtual-environment, cache, bytecode, database, build, distribution,
  or test-runtime entries
- clean extraction compilation passed
- clean extraction full suite passed: 105 passed, 0 failed, 0 skipped
- clean extraction generated 6 source, Preview, and Apply/history UI smoke
  captures without worker or thread warnings
- extracted version identified itself as `R4 RC6.6 — Safe Scan and Import`

The final SHA256 is distributed beside the ZIP in
`Twano-R4-RC6.6-Safe-Scan-and-Import.zip.sha256`. The checksum is external
because an archive cannot truthfully contain its own final hash.

## Safety boundary

Safe Preview is available and the accepted immediate scan pipeline remains
unexposed for configured watched sources. Preview reads source and book
snapshots but does not update books, missing flags, source scan timestamps, or
history. Explicit Apply rechecks catalogue and file facts, refreshes metadata
only for new or changed candidates, performs a final filesystem check, then
commits books, source evidence, and history in one database transaction. Ebook
files are never changed.

## Native Windows checkpoint — accepted

Run `launcher.bat`, open Scan, and verify:

- existing Library locations appear as watched sources
- Test Connection reports a readable source as Available
- Add Source accepts a local folder
- Edit Source changes its name, recursion, and rules
- Disable Source changes the watch state and Enable Source restores it
- Remove Watch clearly says catalogue books are retained
- removing a test watch does not remove or alter ebook files
- re-adding that folder restores the watch
- restored and compact window layouts do not overlap controls
- Preview Scan completes and displays summary counts and status rows
- Library and Home counts remain unchanged after preview
- Discard Preview clears the result without changing the Library
- cancelling a preview reports that no missing books were inferred
- Apply Preview is enabled for a complete preview containing changes
- Apply commits the intended new, changed, and missing catalogue outcomes
- Home and Library refresh only after successful Apply
- a repeated preview proposes no duplicate catalogue rows
- a candidate removed after Preview is safely skipped during Apply
- Recent Scan History shows matching applied and safely skipped counts
- cancelling Apply during rechecks makes no book changes

The user confirmed watched-source management, Safe Preview, transactional
Apply, Library refresh, and scan history on Windows on 28 July 2026.

Do not use a source containing irreplaceable data for UI experimentation,
although this milestone performs no ebook file mutations.

## Final acceptance

The user accepted the refreshed RC6.6 package and action-colour correction on
28 July 2026. RC6.7 Protection and Undo Foundation is authorised to begin.

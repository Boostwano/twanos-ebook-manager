# Twano R4 RC6.5 Test Report

**Package:** Living Library  
**Status:** Accepted after automated, performance, package, offscreen UI, and
native Windows validation

## Accepted baseline

RC6.5 started only after the user accepted RC6.4 on Windows. The preserved
accepted package is:

```text
C:\Twano\Builds\Twano-R4-RC6.4-Responsive-Home-and-Smart-Search.zip
SHA256 F3F47BBF788CE21698263FBFBBCEE89808E051C8A8861B03819BF574472B93BD
```

Baseline before RC6.5 source changes:

```text
.\.venv\Scripts\python.exe -m compileall -q src tests
Passed

.\.venv\Scripts\python.exe -m pytest -v
55 passed
0 failed
0 skipped
0 warnings
```

## Automated validation

```text
.\.venv\Scripts\python.exe -m compileall -q src tests
Passed

.\.venv\Scripts\python.exe -m pytest -v
81 passed
0 failed
0 skipped
```

The focused RC6.5 set contains 29 tests covering:

- additive legacy-schema migration
- collection uniqueness, membership, filtering, and foreign-key cascade
- every allowed sort field in both directions
- rejected invalid sort fields, directions, and paging boundaries
- combined filters, paging boundaries, matching count, and total count
- persisted and invalid Library preferences
- incremental model fetch and stale query-result rejection
- grid/list model and selection sharing without a view-switch query
- details selection, route-only actions, missing files, empty library, and no
  matches
- bounded thumbnail caching, missing/corrupt covers, and stale worker results
- Windows Explorer selection for paths containing spaces
- Calibre ebook-viewer fallback when Windows reports only `OpenWith.exe`
- preservation of a real Windows default ebook reader
- compact toolbar reflow and right-edge containment at a 700-pixel Library
  page width
- restored-window details visibility while the toolbar remains reflowed
- single-click compact details activation, Back restoration, top-priority
  actions, and horizontal panel containment

The full suite also retains the accepted RC6.4 banner, Home, search, review,
reader, scan lifecycle, metadata provider, service, and database regressions.

## 10,000-record performance observations

Command:

```text
.\.venv\Scripts\python.exe tools\validate_rc6_5_library.py
```

Measured on the validation machine on 28 July 2026:

| Observation | Result |
| --- | ---: |
| Synthetic records | 10,000 |
| Dataset insert | 241.876 ms |
| Initial query, 100 records | 18.539 ms |
| Filtered and file-date-sorted query | 17.419 ms |
| Filter matches | 20 |
| Incremental 100-record page | 21.532 ms |
| First-page model and table render | 39.499 ms |
| 200 grid/list switches | 2528.258 ms total |
| Queries caused by those switches | 0 |
| Thumbnail-cache bound | 192 pixmaps |

These are observations from one machine, not universal timing guarantees. The
automated cache test separately confirms eviction above its configured bound.

## Offscreen UI and worker smoke validation

Command:

```text
.\.venv\Scripts\python.exe tools\capture_rc6_5_library.py OUTPUT_FOLDER
```

The smoke run:

- constructed `MainWindow` against a temporary database
- navigated to Library using production background queries
- loaded 36 records and visible cover thumbnails
- selected a book in the shared selection model
- captured and inspected restored 1180 x 790 grid/details geometry
- captured and inspected 1680 × 980 wide grid/details geometry
- captured and inspected 1000 × 720 compact grid geometry
- activated the same details widget in compact replacement mode
- confirmed compact details collapse browser controls and restore them on Back
- confirmed details actions remain at the top and within the panel width
- closed cleanly after query and thumbnail work

Offscreen font rasterization is not a substitute for native ClearType or
keyboard review. The captures validate structure, sizing, selection, cover
states, and responsive reparenting.

## Native Windows checklist — accepted

Run `launcher.bat`, then verify:

- Library opens and remains responsive while records and covers appear.
- Grid and List retain the same selection and do not visibly reset on switch.
- Compact, Comfortable, and Spacious cover density remain usable.
- Search and all six filter controls produce sensible results.
- Every sort option works in both directions.
- Keyboard arrows and Enter select and activate details.
- Wide details and compact Back behavior are usable.
- At a restored 1180-pixel window width, the details panel and all action
  columns remain available without horizontal scrolling.
- At narrower widths, one book click opens details and Back returns to the
  Library browser.
- Missing/corrupt covers and missing files show calm disabled states.
- Open Book and Open Folder use native Windows behavior.
- Edit Metadata routes to Metadata; Review Issues routes to Review Queue.
- Collections can be created, assigned, and removed without moving the file.
- Closing the application produces no worker or thread warning.

The user confirmed the final restored-window details correction on 28 July
2026. This completed the remaining native gate and authorised RC6.6 to begin.

Partial native evidence:

- The user confirmed Open Folder selects the book correctly.
- The user confirmed Open Book launches the selected book correctly.
- The user reported that the details panel still disappeared in a
  non-maximized 1180-pixel window after compact controls were reflowed.
  Toolbar and details breakpoints are now separate, actions are top-priority
  and width-constrained, and both restored and compact modes pass offscreen
  regression checks. The user confirmed the corrected native behaviour.

## Package validation

Candidate file-set validation completed on 28 July 2026:

- output name: `Twano-R4-RC6.5-Living-Library.zip`
- 127 source entries
- every entry opened and read successfully
- 7 expected banner PNG files
- all required RC6.5 source, launcher, and release-report entries present
- 0 nested ZIP files
- 0 Git, virtual-environment, cache, bytecode, build, distribution, or
  test-runtime entries
- Builds and workspace-root copies were byte-identical
- clean extraction compilation passed
- clean extraction full suite passed: 81 passed
- clean extraction offscreen `MainWindow` and Library smoke passed as
  `R4 RC6.5`

The final SHA256 is distributed beside the ZIP in
`Twano-R4-RC6.5-Living-Library.zip.sha256`. The checksum is external because an
archive cannot truthfully contain its own final hash.

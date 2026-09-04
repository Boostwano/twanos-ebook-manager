# Twano R4 Beta 2 Milestones Brief

## Milestone 1 — Baseline and measurement

**Status: Completed**

- Freeze the accepted Beta 1 package and hash.
- Run the full baseline suite.
- Add repeatable 1,000-, 5,000- and 10,000-book measurements.
- Capture phase timings for scan safety, backup and verification.
- Record current memory/cache and UI responsiveness observations.

## Milestone 2 — Scan and database performance

**Status: Completed and accepted**

- Remove duplicated filesystem/database work proven unnecessary by profiling.
- Preserve final file and catalogue rechecks.
- Improve progress wording so long safety phases remain understandable.
- Validate cancellation and repeated Apply.
- Test large local, missing-file and offline-source cases.
- Add several watched folders together and preview every enabled source in one
  action without sharing SQLite connections between workers.
- Apply combined previews sequentially with one approval and a separate
  verified backup and Undo history record per source.

## Milestone 3 — Provider and session reliability

**Status: Completed and accepted**

- Add Project Gutenberg/Gutendex, Harvard LibraryCloud, Crossref, Big Book API
  and OpenWeb Ninja as approved optional providers.
- Keep ISBNdb available for users with paid accounts while documenting free
  and no-key alternatives accurately.
- Test timeouts, rate limits, malformed results and one-provider failures.
- Preserve good metadata and covers from providers that completed.
- Verify persistent caches invalidate safely after schema changes.
- Verify protected credential save, re-entry and removal.
- Exercise repeated lookup sessions without stale UI state.
- Advance to the next book with listed metadata issues after a successful
  reviewed Apply.
- Support checkbox-based bulk plugin lifecycle actions with safe restrictions
  for required built-ins and confirmed deletion of downloaded packages.
- Move user-confirmed invalid files into a scan-excluded manual-review folder,
  remove their active catalogue entries, and continue with the next book.

## Milestone 4 — Accessibility and responsive hardening

**Status: Completed and accepted**

- Audit tab order, shortcuts, focus indicators and accessible names.
- Validate text scaling and high-DPI layouts.
- Check all state labels without relying on colour.
- Correct clipped or scrolling core pages at 900 x 600.
- Re-run native visual smoke captures.

## Milestone 5 — Migration and recovery matrix

**Status: Completed and accepted**

- Migrate a copy of Beta 1 settings and catalogue.
- Test fresh startup and preserved existing data.
- Test cancellation/failure cleanup and forced-restart recovery.
- Repeat backup, verification, Restore and Undo after restart.
- Validate mapped/UNC offline and reconnect behaviour where available.

## Milestone 6 — Beta 2 release gate

**Status: Completed and accepted on 30 July 2026**

- Run `python -m pytest -v`.
- Compile source, tests and tools.
- Run performance and accessibility reports.
- Build a timestamped Beta 2 ZIP.
- Validate from a clean extraction and capture native UI pages.
- Update release notes, User Guide, Known Issues, test report and roadmap.
- Deliver the complete Beta 2 acceptance guide.
- Prepare the private GitHub source repository with licensing, third-party
  notices, security policy, Windows CI, dependency monitoring, and publication
  safety checks.

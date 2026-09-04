# Version History

## R4 RC1 — Production Release Candidate

- Accepted Beta 2 behaviour is feature-frozen.
- Application and Windows packaging versions are aligned to R4 RC1.
- Portable and installer builds use timestamp-first output folders and
  adjacent SHA256 files.
- Binary production packaging remains blocked until the pinned local
  PyInstaller dependency is available; signing is not yet configured.

## R4 Beta 2 — Reliability and Performance Test Package

- Added multiple watched folders in one action plus combined Preview All and
  sequential protected Apply All.
- Expanded direct metadata and cover providers, provider-health reporting,
  cover validation, and metadata review progression.
- Improved large-library preview performance and visible backup progress.
- Consolidated first-run setup and launch into `launcher.bat`.
- Prepared the private source repository with licensing, third-party notices,
  security guidance, automated Windows tests, dependency monitoring, and a
  pre-publication safety audit.

## R4 Beta 1 — Complete Library Test Package

- Consolidated Metadata Studio, Duplicate Intelligence, actionable Health,
  Calibre/network integration, controlled plugins, Settings, accessibility,
  guidance, and packaging foundations.
- Feature scope frozen for complete guided user testing.
- Fresh `%LOCALAPPDATA%\Twano` catalogue; older development data preserved.
- Source test ZIP with setup/launcher and clean-package validator.

## R4 RC6.7 — Protection and Undo Foundation (in development)

- Protection & Undo centre with persistent backup policy
- SQLite online backup while the live catalogue remains open
- SQLite integrity and SHA256 manifest verification
- Background create, re-verify, cancellation, and cleanup
- Immutable change plans with risk, reversibility, confirmation, and expiry
- Persistent operation/item audit history and readable report export
- Separate preview, approval, protected Apply, cancellation, and Undo
- Verified pre-change backup and atomic allowlisted collection executor
- Schema-validated persistent inverse data and source-linked Undo after restart
- One-confirmation Restore with automatic verification, safety backup, staged
  replacement, and post-swap recovery
- Plain-language old-backup review with verified owned-file cleanup boundaries
- Existing Scan Apply confirmation linked to the common protected operation
  and audit history
- Automatic verified catalogue backup before Scan Apply
- Atomic Scan History/protection outcome link with persistent counts and status
- Accurate Scan recovery label: no one-click Undo; whole-catalogue Restore
  remains available from the safety backup
- Explicit boundary keeping redo and ebook-file execution unavailable

## R4 RC6.6 — Safe Scan and Import

- Watched-source configuration for local, mapped-drive, and UNC-shaped paths
- Read-only connection testing outside the GUI thread
- Editable source names, recursion, and include/exclude rules
- Non-destructive disable and Remove Watch behavior
- Non-mutating Safe Preview with change classification and discard
- Guarded transactional Apply with final candidate rechecks and rollback
- Source result evidence and recent scan history

## R4 RC6.5 — Living Library

- Shared paged grid and list Library browser
- Responsive book details, series sequence, and basic collections
- Background cover decoding with a bounded thumbnail cache
- Validated Library view, density, sort, and details preferences
- 10,000-record query and model/view validation

## R4 RC6.4 — Responsive Home and Smart Search

- Responsive sidebar, hero, cards, actions, and status insight
- Floating Home suggestions with keyboard and dismissal behavior
- Dedicated Search Results page and metadata Review Queue
- Explicit page-ID routing and automatic Home search reset
- Seven selectable hero banners, startup rotation, preference migration, and
  missing-asset fallback

## R4 RC6.3 — Twano Design System

- Scalable open-book branding
- Colour-coded navigation and larger application typography

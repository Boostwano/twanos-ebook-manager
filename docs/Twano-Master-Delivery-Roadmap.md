# Twano Master Delivery Roadmap

## Document purpose

This document defines the planned delivery path from the accepted **Twano R4
RC6.4** baseline through a production-ready **Twano R4 Final** release.

It is the master release roadmap for the desktop agent. It does not replace the detailed specification and milestone brief for an individual package. Each package must still receive its own change specification, implementation brief, test report and release notes before development begins.

The current implementation package is:

```text
2026-07-30-2345-Twano-R4-RC1-Source-Candidate.zip
```

By user approval, the former RC6.8 through RC7.4 recommendations were
consolidated into Beta 1 to reduce the number of intermediate packages.
Actionable Library Health was retained while a separate technical analytics
dashboard was removed from scope. Beta 1 is now feature-frozen for guided
end-to-end testing.

The historical accepted engineering baseline is:

```text
C:\Twano\Builds\Twano-R4-RC6.6-Safe-Scan-and-Import.zip
SHA256 4C1117CC82801094671FF40B218532C3591E3A8A3A4C4B74D4A68A8C35B89CF7
```

The latest validated development candidate is:

```text
C:\Twano\Builds\2026-07-30-2345-Twano-R4-RC1-Source-Candidate.zip
SHA256 is provided in the adjacent `.zip.sha256` file.
245 passed, 0 failed, 0 skipped
Clean extracted-package validation passed
Windows binary build blocked by missing local PyInstaller/Inno Setup
```

---

# Product vision

**Twano — Your Library, Beautifully Organised**

Twano is a digital librarian, not merely an ebook file manager. It should help people organise, protect, repair, understand and rediscover their digital libraries without requiring expert technical knowledge.

Every feature should answer:

> Does this make organising a digital library easier, safer or more enjoyable?

## Product principles

- Beginner friendly
- Safe by design
- Preview before changes
- Automatic backups
- Persistent Undo
- No vendor lock-in
- Calm, professional single-window interface
- Dark visual theme
- Beautiful rather than corporate
- Clear explanations instead of technical error messages
- Every warning provides a path to review or resolve it
- Destructive actions are never the default
- User data remains portable and recoverable

## Meaning of Persistent Undo

Twano should not impose an arbitrary small limit on undo history. In practice, undo retention is constrained by available storage, backup policy and user-controlled cleanup. Twano must communicate those constraints honestly rather than claiming infinite storage.

---

# Delivery strategy

Twano will be completed through small, reviewable release packages. Each package must:

1. Start from the latest verified package or Git branch.
2. Preserve working behaviour unless a change is explicitly approved.
3. Establish baseline tests before source changes.
4. Implement one coherent product area.
5. Add automated tests for new logic where practical.
6. Perform truthful manual testing for behaviour that cannot be automated.
7. Update documentation and version information.
8. Produce a validated ZIP package.
9. Leave the repository in a clean, reviewable Git state.

A package is not complete merely because the interface opens. It must satisfy its exit criteria and include an accurate test report.

---

# Release sequence at a glance

| Package | Release title | Primary outcome |
|---|---|---|
| R4 RC6.4 | Responsive Home and Smart Search | Stable responsive shell, non-disruptive search and completed hero-banner settings |
| R4 RC6.5 | Living Library | Modern library browser, book details, filters, series and collection foundations |
| R4 RC6.6 | Safe Scan and Import | Reliable scanning, source management, preview and import workflow |
| R4 RC6.7 | Protection and Undo Foundation | Backups, change plans, audit history and recoverable operations |
| R4 RC6.8 | Metadata Studio | Metadata enrichment, provider matching and exception-based review workflow |
| R4 RC6.9 | Duplicate Intelligence | Safe duplicate detection, edition awareness and review-based resolution |
| R4 RC7.0 | Library Health and Analytics | Actionable health reporting, trends and exportable reports |
| R4 RC7.1 | Calibre, Synology and Network Libraries | Safe interoperability with Calibre and resilient network paths |
| R4 RC7.2 | Plugin and Provider Platform | Controlled extension system, provider diagnostics and compatibility checks |
| R4 RC7.3 | Settings, Accessibility and Guidance | Complete settings, accessibility, onboarding, help and recovery experience |
| R4 RC7.4 | Windows Packaging and Updates | Installer, portable build, migration and update workflow |
| R4 Beta 1 | End-to-End Beta | Feature-complete build for controlled real-library testing |
| R4 Beta 2 | Reliability and Performance Beta | Performance, accessibility, data integrity and usability hardening |
| R4 RC1 | Production Release Candidate | Code freeze, clean install/upgrade validation and release sign-off |
| R4 Final | Twano R4 | Supported production release |

The numbering is a delivery plan, not a reason to force unfinished work into a release. A package may receive a small hotfix suffix when necessary, but unrelated features must not be silently added.

---

# R4 RC6.4 — Responsive Home and Smart Search

## Goal

Complete the responsive Home experience and introduce a dedicated search workflow without regressing the RC6.3 design system.

## Main deliverables

- Responsive sidebar without normal scrolling at supported sizes
- Responsive Home cards, icons, spacing and typography
- Correctly sized hero greeting without clipping
- Floating search suggestions that do not move dashboard content
- Dedicated Search Results page
- Home search cleared whenever Home is reopened
- Actionable metadata insight opening a filtered Review Queue
- Fixed-banner and rotate-on-startup modes
- Seven selectable hero banners
- Banner preference migration, validation and missing-asset fallback
- Reading-setting validation for search results

## Source-of-truth documents

```text
docs/RC6.4-Change-Specification.md
docs/Twano-R4-RC6.4-Milestones-Brief.md
```

## Output package

```text
Twano-R4-RC6.4-Responsive-Home-and-Smart-Search.zip
```

## Exit gate

RC6.5 must not begin until RC6.4 passes its automated checks and Windows UI checklist, or any accepted exceptions are recorded explicitly.

---

# R4 RC6.5 — Living Library

## Goal

Transform Library from a basic management page into a fast, enjoyable and useful digital bookshelf while preserving safe management features.

## Main deliverables

### Library browser

- Cover-grid and information-rich list views
- Fast switching between views without reloading the database unnecessarily
- Responsive cover sizing and density controls
- Sorting by title, author, series, date added, file date, format and metadata quality
- Filters for format, author, series, collection, location and metadata status
- Clear empty-library and no-results states
- Persistent user view preference

### Book details

- Dedicated or side-panel book details view
- Cover, title, author, series, description and identifiers
- File format, size, location and modified date
- Metadata quality and issue summary
- Open Book, Open Folder, Edit Metadata and Review Issues actions
- Graceful display when fields or covers are missing

### Series and collections foundation

- Series name and sequence display
- Basic collection/tag support
- Series grouping in Library
- Foundation for later smart collections without adding an overly complex rules engine yet

### Performance

- Pagination, incremental loading or model/view architecture suitable for large libraries
- Cover thumbnail caching
- No blocking database or image work on the UI thread

## Non-goals

- Built-in ebook reader
- Cloud sync
- Social features
- Advanced recommendation engine

## Output package

```text
Twano-R4-RC6.5-Living-Library.zip
```

## Exit criteria

- Library remains responsive with a representative large test library.
- Opening, filtering and sorting books produce correct results.
- Missing files and metadata do not crash the page.
- Book actions honour configured Reading settings.

---

# R4 RC6.6 — Safe Scan and Import

## Goal

Deliver a predictable, background scan and import workflow that users can understand before Twano changes its library database.

## Main deliverables

### Library sources

- Add, edit, disable and remove watched library locations
- Local folders, mapped drives and UNC path foundations
- Clear connection and permission tests
- Distinguish unavailable sources from deleted books
- Source-level include and exclude rules where supported by the existing architecture

### Scan workflow

- Background scanning with cancellation
- Clear progress and current-location reporting
- Supported-format detection based on repository configuration
- File fingerprinting or hashing where appropriate
- Embedded metadata extraction
- Detection of unreadable, unsupported and inaccessible files
- Incremental rescans rather than unnecessary full rescans

### Import preview

- Preview newly discovered, changed, missing and unreadable items
- No silent destructive database changes
- Explicit apply/import step
- Summary of what will be added, updated, skipped or flagged
- Safe handling of files that disappear during a scan

### Scan history

- Last scan status per source
- Duration and counts
- Error summary
- Link from scan failures to actionable review information

## Output package

```text
Twano-R4-RC6.6-Safe-Scan-and-Import.zip
```

## Exit criteria

- Scan operations do not block the interface.
- Cancelling a scan leaves the database consistent.
- Repeated scans do not create duplicate records.
- Network interruptions are reported without treating the entire library as deleted.

---

# R4 RC6.7 — Protection and Undo Foundation

## Goal

Build the safety infrastructure required before Twano performs broad metadata updates, duplicate resolution or file operations.

## Main deliverables

### Change plans

- Every multi-book change creates a human-readable change plan
- Preview shows intended database and file changes
- High-risk actions require explicit confirmation
- Plans can be cancelled before application

### Backups

- Automatic database backup before significant operations
- File backup or recoverable copy strategy before supported file modifications
- Configurable backup location and retention policy
- Backup integrity checks
- Restore workflow with clear warnings and validation

### Undo and history

- Persistent operation history
- Undo for every Twano-managed reversible operation
- Clear distinction between fully reversible and partially reversible actions
- No arbitrary small count limit
- Storage-aware retention and cleanup controls
- Redo only where it can be implemented safely

### Audit trail

- Timestamp, operation type, affected books, result and initiating component
- Error and rollback details
- Exportable operation report

## Architectural requirement

Metadata application, duplicate resolution and file changes in later releases must use this common transaction/change-plan layer rather than inventing separate safety mechanisms.

## Output package

```text
Twano-R4-RC6.7-Protection-and-Undo-Foundation.zip
```

## Exit criteria

- A failed operation cannot leave partially committed database state without a recorded recovery path.
- Backups can be restored in a clean test environment.
- Undo survives application restart.
- Audit history explains what changed and whether rollback succeeded.

---

# R4 RC6.8 — Metadata Studio

## Goal

Provide a calm, exception-based metadata enrichment workflow that completes lookups first and asks the user to review only ambiguous or risky cases.

## Main deliverables

### Provider architecture

- Stable provider interface
- Open Library integration retained and hardened
- Google Books or other approved provider integration only after legal and technical review
- Local embedded metadata provider
- Provider enable/disable and priority controls
- Timeouts, retry limits and rate-limit awareness
- Persistent metadata cache
- Provider diagnostics without exposing raw technical errors to beginners

### Matching engine

- Normalised title and author matching
- ISBN and identifier matching
- Confidence scoring with explainable reasons
- Edition-aware candidate handling
- Multiple-match and no-match states
- Cover comparison

### Metadata review wizard

1. Select books or use Review Queue
2. Lookup metadata in the background
3. Automatically accept only high-confidence, policy-approved matches
4. Review exceptions
5. Approve changes at field level
6. Preview the full change plan
7. Apply through the RC6.7 protection layer
8. Show completion and error summary

### Session recovery

- Persist lookup queue and review state
- Resume interrupted sessions
- Avoid repeating completed lookups unnecessarily

## Output package

```text
Twano-R4-RC6.8-Metadata-Studio.zip
```

## Exit criteria

- No metadata write occurs without preview and recoverability.
- Provider failures do not lose completed work.
- Confidence decisions are testable and explainable.
- Users can review fields rather than accepting an entire record blindly.

---

# R4 RC6.9 — Duplicate Intelligence

## Goal

Detect likely duplicates without encouraging unsafe deletion or confusing different editions as identical books.

## Main deliverables

### Detection methods

- Exact file hash duplicates
- Same canonical path or accidental duplicate database entries
- ISBN duplicates
- Normalised title and author similarity
- Edition, format and file-quality awareness
- Series-aware comparison where relevant

### Duplicate groups

- Explain why items were grouped
- Show cover, metadata, format, size, location and quality indicators
- Distinguish exact copies from possible alternate editions
- Confidence or evidence summary

### Safe resolution

- Keep all
- Mark as intentional editions
- Choose preferred record
- Merge metadata without deleting files
- Move redundant file to a recoverable quarantine area
- Delete only through the protection and backup layer
- Preview every result before application

## Non-goal

Twano must never automatically delete duplicate files based only on similarity scoring.

## Output package

```text
Twano-R4-RC6.9-Duplicate-Intelligence.zip
```

## Exit criteria

- Exact and probable duplicates are clearly separated.
- Alternate editions can be preserved intentionally.
- Every destructive resolution has a tested undo or restore path.

---

# R4 RC7.0 — Library Health and Analytics

## Goal

Turn library data into useful, actionable information without turning Home back into a statistics dashboard.

## Main deliverables

### Library Health

- Missing or weak metadata
- Missing covers
- Missing or inaccessible files
- Unreadable and unsupported files
- Duplicate groups
- Failed metadata lookups
- Unavailable library sources
- Stale scan status
- Quality score with transparent calculation

### Actionable workflow

- Every health item opens the relevant filtered page or workflow
- Health counts link to Review Queue, Scan, Metadata or Duplicate Intelligence
- Clear distinction between information, warning and urgent risk

### Analytics

- Library size and growth
- Formats
- Authors and series
- Recently added books
- Metadata quality trends
- Scan and lookup outcomes
- Storage usage where reliable
- No invented reading-progress analytics without a real progress source

### Reporting

- Export health summary in a portable format
- Export detailed issue list
- Include generation date and scope

## Output package

```text
Twano-R4-RC7.0-Library-Health-and-Analytics.zip
```

## Exit criteria

- Health scores are deterministic and documented.
- Every warning has a direct route to action.
- Analytics queries remain responsive on large libraries.

---

# R4 RC7.1 — Calibre, Synology and Network Libraries

## Goal

Provide safe interoperability for users who keep books in Calibre libraries, Synology shares, NAS devices or Windows network locations.

## Main deliverables

### Network resilience

- UNC and mapped-drive support
- Path normalisation that does not corrupt network paths
- Connection tests and permission diagnostics
- Offline-source state rather than false missing-file state
- Safe retry and rescan behaviour
- Clear Synology setup guidance

### Calibre integration

- Detect Calibre installations and libraries
- Read Calibre metadata safely
- Use supported Calibre command-line interfaces where practical
- Never write directly to Calibre's database in an unsupported way
- Preview import and update plans
- Preserve Calibre identifiers and library integrity
- Clear ownership rules when both Twano and Calibre can modify metadata

### Portability

- Library source paths remain editable after moving to another computer
- Settings migration supports changed drive letters and network locations

## Output package

```text
Twano-R4-RC7.1-Calibre-Synology-and-Network-Libraries.zip
```

## Exit criteria

- A temporarily unavailable NAS does not mark all books as deleted.
- Calibre integration passes tests against a copy of a test library.
- Unsupported Calibre operations are refused safely rather than attempted.

---

# R4 RC7.2 — Plugin and Provider Platform

## Goal

Introduce a controlled extension mechanism without compromising startup reliability, data safety or compatibility.

## Main deliverables

### Plugin framework

- Plugin manifest and version requirements
- Discovery from a dedicated plugin directory
- Enable, disable and quarantine controls
- Compatibility checks against Twano and API versions
- Isolated plugin error handling
- Plugin-specific logging and diagnostics
- Safe startup when a plugin fails

### Initial extension points

- Metadata providers
- Export/report providers
- Non-destructive library analysis tools

File-modification plugins should remain restricted until a stronger permission and transaction model is approved.

### User experience

- Installed plugin list
- Status and compatibility information
- Configuration panel generated through a supported interface
- Clear warning that third-party plugins may access library data

## Output package

```text
Twano-R4-RC7.2-Plugin-and-Provider-Platform.zip
```

## Exit criteria

- Twano starts when a plugin is missing, incompatible or broken.
- Plugins cannot silently bypass the common protection layer for supported changes.
- The plugin API is documented and versioned.

---

# R4 RC7.3 — Settings, Accessibility and Guidance

## Goal

Complete the application-wide user experience so first-time and returning users can configure, understand and recover Twano without specialist help.

## Main deliverables

### Settings completion

- General behaviour
- Appearance and responsive-density preferences
- Hero banner settings
- Reading/open-book behaviour
- Library sources
- Metadata providers
- Backups and undo retention
- Network and Calibre options
- Plugin controls
- Diagnostics and privacy-relevant options
- Per-section Restore Defaults rather than one dangerous global reset

### Settings reliability

- Schema-versioned preferences
- Validation before saving
- Migration from older settings
- Safe fallback for invalid paths, values or missing assets
- Clear indication of settings requiring restart

### Accessibility

- Complete keyboard navigation
- Visible focus states
- Screen-reader labels where supported by PySide6
- Text scaling and high-DPI validation
- Colour-contrast review
- Reduced-motion behaviour for any animations
- No information communicated by colour alone

### Guidance

- First-run setup flow
- Contextual empty states
- User Guide populated with current workflows
- What's New generated from release notes
- About page with version, data locations and support information
- Diagnostics export that excludes private library content by default

## Output package

```text
Twano-R4-RC7.3-Settings-Accessibility-and-Guidance.zip
```

## Exit criteria

- Settings survive restart and upgrade.
- Core workflows are usable by keyboard.
- First-time users can add a library and scan it without external instructions.

---

# R4 RC7.4 — Windows Packaging and Updates

## Goal

Produce repeatable, trustworthy Windows distributions suitable for beta testing and eventual public release.

## Main deliverables

### Build outputs

- Windows installer
- Portable ZIP build
- Application icon and version metadata
- Clean separation of program files and user data
- Correct handling of spaces and non-ASCII characters in paths
- Bundled licences and notices for dependencies

### Installation and migration

- Per-user installation by default unless elevated installation is justified
- Upgrade without deleting user database or settings
- Configuration and database schema migration
- Uninstall that does not remove user libraries or backups without explicit consent
- Optional clean-uninstall choice with clear warnings

### Updates

- Signed or verifiable update metadata where feasible
- Update-check setting
- Release-channel foundation for stable and beta builds
- Download and install flow that does not silently replace a running application
- Rollback guidance if an update fails

### Build automation

- Reproducible scripted build
- Automated version injection
- ZIP and installer integrity checks
- GitHub release workflow foundation
- Software signing documented even if a production certificate is not yet available

## Output package

```text
Twano-R4-RC7.4-Windows-Packaging-and-Updates.zip
```

The package should also produce the installer and portable application artefacts defined by the build system.

## Exit criteria

- Clean installation works on a supported Windows machine.
- Upgrade from the latest prior package preserves data.
- Portable build does not write application files into its source folder unexpectedly.
- Installer and ZIP contents are validated automatically.

---

# R4 Beta 1 — End-to-End Beta

## Goal

Freeze feature scope and validate the complete application with real but backed-up libraries.

## Main activities

- End-to-end workflow testing from first run through scan, search, metadata review, duplicates, health and restore
- Clean install, upgrade and portable-build testing
- Small, medium and large library datasets
- Local, mapped-drive and UNC source testing
- Calibre test-library validation
- Corrupt file and unavailable path scenarios
- Recovery after forced application termination
- Structured beta feedback collection
- Privacy and diagnostics review

## Rules

- No major new features
- Fix data-loss, crash, workflow-blocking and serious usability defects first
- Every beta defect receives reproduction steps and a regression test where practical

## Output package

```text
Twano-R4-Beta1-End-to-End.zip
```

## Exit criteria

- No known critical data-loss defect.
- No known reproducible startup blocker on supported systems.
- Core workflows complete successfully with representative libraries.

---

# R4 Beta 2 — Reliability and Performance Beta

## Goal

Validate fixes from Beta 1 and harden Twano for daily use.

## Main activities

- Performance profiling and database-query optimisation
- Memory and thumbnail-cache behaviour
- Long-running scan and metadata session stability
- Accessibility and high-DPI validation
- Installer upgrade and rollback testing
- Settings and database migration testing from supported prior builds
- Backup and restore drills
- Error-message and recovery-path review
- Documentation verification against the actual application

## Output package

```text
Twano-R4-Beta2-Reliability-and-Performance.zip
```

## Exit criteria

- No unresolved critical defect.
- High-severity defects have accepted fixes or documented release blockers.
- Performance targets are recorded and met for agreed library sizes.

---

# R4 RC1 — Production Release Candidate

## Goal

Create the exact build intended for production release unless a blocking defect is found.

## Release freeze

Permitted changes:

- Release-blocking bug fixes
- Documentation corrections
- Packaging corrections
- Security and data-integrity fixes

Not permitted:

- New features
- Visual redesign
- New provider or plugin capabilities
- Database changes without exceptional justification and migration tests

## Validation matrix

- Clean install
- Upgrade from latest supported pre-release
- Portable launch
- Fresh database
- Existing database migration
- Local library
- Network library
- Calibre test library
- Backup and restore
- Undo after restart
- Offline-source recovery
- Uninstall and reinstall

## Output package

```text
Twano-R4-RC1-Production-Candidate.zip
```

## Exit criteria

- Release checklist signed off.
- No open release-blocking defects.
- Final installer and portable build hashes recorded.
- Documentation and version information match the binaries.

---

# Twano R4 Final

## Goal

Publish the first supported production release from the R4 development line.

## Final release artefacts

- Windows installer
- Portable ZIP
- Release notes
- User Guide
- Known Issues document
- Privacy and diagnostics statement
- Licence and dependency notices
- Checksums
- Upgrade and rollback guidance
- Git tag and release record

## Suggested release names

```text
Twano-R4-Windows-Setup.exe
Twano-R4-Portable.zip
```

The exact version number should be chosen consistently across the application, installer, documentation and Git tag before RC1. Do not mix the historical internal RC labels with a different public version number without documenting the mapping.

## Production support baseline

Before release, document:

- Supported Windows versions
- Supported ebook formats
- Supported Calibre versions, if integration ships
- User-data and backup locations
- Update policy
- Known limitations
- How to report defects safely

---

# Definition of Done for every package

A package is complete only when all applicable items below are satisfied.

## Source and architecture

- Source changes are committed to the correct Git branch.
- Changes follow the existing architecture or document an approved architecture decision.
- UI code, business logic, database access and external providers remain separated.
- No abandoned duplicate implementation is left active.
- Database migrations are explicit, versioned and tested.

## Safety

- User-facing changes are previewed before destructive application.
- File and database changes use the common protection layer once available.
- Errors preserve recoverability and produce clear next steps.
- Missing files, unavailable networks and malformed metadata are handled safely.

## Testing

- Python compilation succeeds.
- Existing automated tests are run.
- New logic receives tests where practical.
- Test failures are reported rather than hidden.
- UI behaviour not covered automatically receives a written manual checklist.
- Windows-specific tests are run on Windows before release approval.

## Documentation

- Version updated consistently.
- `CHANGELOG.md` updated.
- `README.md` updated where behaviour changed.
- `ROADMAP.md` status updated.
- `PROJECT_HANDOVER.md` updated.
- User Guide and architecture documents updated where relevant.
- Known limitations recorded honestly.

## Packaging

- Entry point is present.
- Required assets are included.
- Cache directories, virtual environments, test artefacts and Git metadata are excluded.
- ZIP integrity is tested.
- Packaged application is launched from the packaged location.
- Output path and checksums are recorded.

---

# Desktop agent operating instructions

The desktop agent should use this roadmap as the long-term delivery guide.

For the currently approved package:

1. Read this master roadmap.
2. Read the package-specific change specification and milestones brief completely.
3. Audit the repository before changing source.
4. Report baseline tests and existing defects.
5. Propose an implementation plan and expected file list.
6. Implement only the current package.
7. Stop at the package completion gate for human testing.
8. Once the user explicitly confirms the package is working, record it as
   accepted and begin the next planned build without requiring a separate
   instruction to continue.

When a package is accepted:

- Update the status table in this roadmap.
- Create the next package-specific specification and milestones brief.
- Create a new Git branch from the accepted baseline.
- Preserve the accepted ZIP and release report.

The desktop agent must never claim that tests, packaging or Windows validation succeeded unless those actions were actually performed.

---

# Current status tracker

| Package | Status | Notes |
|---|---|---|
| R4 RC6.3 — Twano Design System | Baseline | Current source package before RC6.4 |
| R4 RC6.4 — Responsive Home and Smart Search | Accepted | Automated, Windows and package gates passed |
| R4 RC6.5 — Living Library | Accepted | Automated, package, action, restored-window, and native user gates passed |
| R4 RC6.6 — Safe Scan and Import | Accepted | Native, automated, performance, package, and action-colour gates passed |
| R4 RC6.7 — Protection and Undo Foundation | Consolidated | Completed and carried into Beta 1 |
| R4 RC6.8 — Metadata Studio | Consolidated | Manual protected metadata and cover workflow in Beta 1 |
| R4 RC6.9 — Duplicate Intelligence | Consolidated | Explainable groups and recoverable exact-copy quarantine in Beta 1 |
| R4 RC7.0 — Library Health and Analytics | Trimmed and consolidated | Actionable Health retained; separate analytics omitted |
| R4 RC7.1 — Calibre, Synology and Network Libraries | Consolidated | Safe detection, opening, source routing and offline diagnostics in Beta 1 |
| R4 RC7.2 — Plugin and Provider Platform | Consolidated | Controlled approved catalogue and compatibility checks in Beta 1 |
| R4 RC7.3 — Settings, Accessibility and Guidance | Consolidated | Completed Settings and guidance surfaces in Beta 1 |
| R4 RC7.4 — Windows Packaging and Updates | Foundation complete | Reproducible scripts included; signed installer/update delivery remains a production gate |
| R4 Beta 1 | Accepted | User accepted the timestamped API-key status package |
| R4 Beta 2 | Accepted | User accepted all 142 guided checks on 30 July 2026 |
| R4 RC1 | In development | Production release candidate |
| R4 Final | Planned | Supported production release |

---

# End-of-build milestone and remaining-work ledger

This ledger is the short operational view of the production roadmap. Update it
at the end of every packaged build. A build may be technically validated while
still awaiting user acceptance; those are different states and must not be
combined.

## Status meanings

- **Built:** implementation exists in a packaged candidate.
- **Automated validation passed:** compilation and automated tests passed.
- **User acceptance pending:** the guided real-application checks have not yet
  been confirmed by the user.
- **Accepted:** the user has confirmed the package as the baseline for the next
  build.
- **Blocked:** a release gate cannot be completed without a decision,
  credential, external service, certificate, or supported test environment.

## Build 1 — R4 Beta 1 complete-library validation

**Current status:** Accepted by the user on 30 July 2026.

**Latest package**

```text
2026-07-30-1513-Twano-R4-Beta1-Plugin-API-Key-Status-Test-Package.zip
```

### Delivered

- Responsive Home, simplified navigation, Library, Scan and source management
- Combined metadata and cover-art search without requiring Calibre
- Open Library and Google Books metadata/cover support
- Optional credential-based Hardcover and Comic Vine providers
- Provider descriptions when supplied, including readable HTML cleanup
- Field-level metadata selection, protected preview and reviewed Apply
- Cover preview, local cover-file selection and provider reporting
- Approved plugin catalogue with install, configure, enable and disable states
- Exact-duplicate review and recoverable quarantine
- Actionable Library Health
- Catalogue backups, verification, restore, protected operations and history
- User Guide, testing guide, release notes and clean source ZIP tooling
- Visible pressed feedback for enabled buttons throughout the application
- Detection and clear re-entry guidance for encrypted API keys Windows can no
  longer unlock
- Readable Google Books failures for invalid keys, disabled Books API,
  incompatible key restrictions and exhausted quota
- A dedicated API-key testing and pre-release removal guide
- A Plugins **API Key** column showing **API Key Added**, **Not Added**,
  **Needs Re-entry**, or **None Required** without revealing credentials

### Validation completed

- Python compilation passed
- `python -m pytest -v`: **210 passed, 0 failed, 0 skipped**
- Clean ZIP extraction, compilation and complete test run passed
- Seven native Qt UI smoke captures produced
- Package contains 196 entries and no nested ZIP files

### Acceptance follow-up carried into Beta 2

- Complete `docs/R4-Beta2-Complete-Testing-Guide.md` using a fresh extraction.
- Confirm metadata descriptions and suitable covers with live provider results.
- Confirm all active providers are listed as searched and failures remain
  understandable when a service is unavailable or rate-limited.
- Confirm enabled buttons visibly depress on Home, Library, Scan, Metadata,
  Plugins, Settings and the bottom update action.
- Test Open Book with the user's chosen Windows ebook reader.
- Test small and large local libraries, including the 1,268-book sample.
- Confirm the long post-scan safety/integrity stage completes and record its
  duration for performance work.
- Test watched-folder removal, offline sources and repeat scans with copied
  ebook data.
- Test metadata Apply, duplicate quarantine/restore, catalogue backup/restore
  and Undo using expendable files.
- Record every failure with reproduction steps and screenshots.
- Fix Beta 1 blocking defects and issue timestamped hotfix packages until the
  acceptance guide passes.

### Known Beta 1 boundaries

- ReadAnyBook is not scraped directly. Manual **Cover File** selection remains
  available when approved providers do not supply a suitable cover.
- Live provider results depend on the provider's catalogue, availability,
  rate limits and any required user-owned API credentials.
- The current ZIP is a source/test package using one self-configuring
  `launcher.bat`; it is not the final signed Windows installer.
- Calibre is optional and is not required for metadata, cover lookup or normal
  ebook-reader use.

### Next build after acceptance

```text
R4 Beta 2 — Reliability and Performance Beta
```

## Build 2 — R4 Beta 2 reliability and performance

**Current status:** Accepted by the user on 30 July 2026.

### Beta 2 work completed so far

- Added a multi-folder source picker so several watched locations can be added
  in one step.
- Added one-click combined Preview and Apply All for every enabled watched
  folder, with sequential thread-safe processing and a separate verified
  backup and Undo record per source.
- Merged first-run dependency setup into `launcher.bat` so the same file sets
  up and starts Twano.
- Prepared the private source repository for GitHub with proprietary licensing,
  third-party notices, security guidance, automated Windows validation,
  dependency monitoring, and a pre-publication safety audit.
- Reduced repeated path-resolution work in large scan comparisons and recorded
  1,000-, 5,000- and 10,000-book performance baselines.
- Added verified-backup progress during scan Apply.
- Added Apple Books and ISBNdb to the approved direct provider catalogue.
- Added optional Project Gutenberg/Gutendex, Harvard LibraryCloud, Crossref,
  Big Book API and OpenWeb Ninja providers with accurate credential and quota
  guidance.
- Kept ISBNdb available as an optional paid provider for users with an
  existing account.
- Added ISBN/title fallback across editions and safe cross-provider enrichment
  of blank ISBN, description, publisher, language, date and series fields.
- Added background validation that removes unavailable cover choices before
  the user can select them.
- After a successful reviewed metadata Apply, automatically advances to the
  next book in library order with listed metadata issues.
- Added per-plugin checkboxes and safe multi-plugin Install, Enable, Disable
  and Uninstall actions while preserving the highlighted-row workflow.
- Added confirmed permanent deletion for downloaded external plugin packages;
  approved built-in providers cannot be deleted and the required embedded
  metadata reader cannot be uninstalled.
- Added a confirmed Metadata action that physically moves invalid files into
  `To be manually reviewed`, removes their active catalogue rows, preserves
  filename collisions and advances to the next book needing attention.
- Excluded every `To be manually reviewed` directory from current and legacy
  scan discovery and added a bottom Library action to open existing review
  folders.
- Added optional key-free Amazon, Google Images, and Edelweiss providers that
  run inside Twano without requiring Calibre.
- Added persistent provider health checks that distinguish a genuine empty
  result from bot/access blocking, temporary connection failure, and an
  unrecognised provider page layout.
- Added a Plugins **Provider Check** column with **Working**, **Access
  Blocked**, **Provider Update Needed**, **Temporarily Unavailable**, and **Not
  Checked Yet** states. Metadata lookup also shows the immediate failure
  reason, and bounded developer diagnostics exclude searches, response pages,
  and credentials.
- Fixed the Home Library Summary so archived/removed watched folders are not
  counted as current locations. Removing the final watched folder now shows
  **0 locations**, no recent library locations, and no last-scan date.
- Added bounded affected-book and location previews to every Library Health
  issue card, followed by an **and N more** summary and the existing full
  review action.
- Added the missing Plugins **Version** column and updated Google Images cover
  extraction for current result markup. The obsolete version 1.0 layout
  warning is reset so version 1.1 receives a fresh real-search check.
- Current automated validation: **245 passed, 0 failed, 0 skipped**.

### Beta 2 acceptance completed

- All 142 guided checks passed.
- No failure, pending item, or skipped check remains in the acceptance guide.
- Automated validation passed with **245 passed, 0 failed, 0 skipped**.
- Clean extracted-package compilation, tests and seven UI smoke captures passed.
- The accepted package and SHA256 remain preserved under `C:\Twano\Builds`.

### Beta 2 exit gate

- No unresolved critical defect.
- High-severity defects are fixed or explicitly recorded as release blockers.
- Agreed performance targets are documented and met.
- Accessibility and high-DPI results are recorded.
- Clean extracted-package validation passes.
- The user completes the Beta 2 acceptance schedule.

### Work remaining after Beta 2

- Freeze features and prepare production packaging.
- Build the Windows installer and portable executable distribution.
- Add final version resources, licences, privacy material and checksums.
- Complete clean install, upgrade, rollback and uninstall validation.
- Obtain or explicitly defer production code signing.
- Complete final release-candidate sign-off.

### Next build

```text
R4 RC1 — Production Release Candidate
```

## Build 3 — R4 RC1 production candidate

**Current status:** In development from the accepted Beta 2 package.

### Work to complete in RC1

- Freeze features; permit only release-blocking, security, data-integrity,
  documentation and packaging corrections.
- Produce the exact Windows installer and portable build intended for release.
- Ensure the installed application includes its Python runtime and required
  dependencies; end users must not need to install pytest.
- Apply consistent production version information and Windows icons.
- Bundle dependency licences and required legal notices.
- Validate clean install on supported Windows versions.
- Validate upgrade from the supported Beta build without losing settings,
  catalogue data or backups.
- Validate uninstall/reinstall and clearly preserve user libraries by default.
- Validate paths containing spaces and non-ASCII characters.
- Validate fresh database, existing database migration, local library, network
  library, backup/restore, Undo after restart and offline-source recovery.
- Finalise update metadata, release channels and failed-update rollback
  guidance.
- Record installer and portable-build SHA256 checksums.
- Complete privacy, diagnostics, support and known-issues review.
- Decide and document code-signing status before public distribution.

### RC1 work completed so far

- Accepted Beta 2 feature set frozen with 142/142 guided checks passed.
- Application, Windows version resource and installer aligned to **R4 RC1**.
- Timestamp-first, overwrite-safe Windows output folders implemented.
- Automatic portable and installer SHA256 generation implemented.
- RC1 release notes, known issues, automated report and test guide added.
- Source compilation, **272 automated tests**, PowerShell parser validation and
  GitHub publication audit passed.
- An isolated eight-book repeat scan, real launcher start, live provider probes
  and all 14 application routes at 900 x 600 and 1600 x 900 passed the
  autonomous acceptance cycle. Remaining provider limits are recorded in
  `KNOWN_ISSUES_R4_RC1.md`.

### Current RC1 release gates

- PyInstaller 6.21.0 and Inno Setup 7.0.2 x64 are available and produced an
  earlier binary candidate. Further acceptance deliveries intentionally remain
  source-based and run through `launcher.bat` until the application is approved
  for its final installer build.
- The final installer must be rebuilt from the accepted source and complete the
  exact clean-install, upgrade, uninstall and Windows security checks.
- Code signing is not configured and remains an explicit release decision.

### RC1 exit gate

- No open release-blocking defect.
- Final automated, clean-install, upgrade and recovery matrices pass.
- Documentation and visible version information match the binaries.
- Installer and portable artefact hashes are recorded.
- The user signs off the release checklist.

### Work remaining after RC1

- Fix only newly discovered release blockers.
- Rebuild and repeat the complete RC1 matrix if any binary changes.
- Publish the approved, byte-identical production artefacts and documentation.

### Next build

```text
Twano R4 Final
```

## Build 4 — Twano R4 Final

**Current status:** Planned.

### Work to complete for Final

- Promote the accepted RC1 binaries without unvalidated feature changes.
- Publish the Windows installer and portable package.
- Publish release notes, User Guide, Known Issues, privacy statement, licences,
  checksums, supported-platform details, update policy and rollback guidance.
- Create the formal release record and approved version tag when explicitly
  authorised.
- Confirm the public update check identifies the production release correctly.
- Archive the accepted source, installer, portable package, test evidence and
  hashes.

### Work remaining after Final

- No additional work is required to complete the R4 production milestone.
- Production support continues through defect triage, security maintenance and
  documented R4.x updates.
- Deferred reader, mobile, cloud, AI and public-marketplace ideas remain future
  work and must not be treated as unfinished R4 requirements.

## Mandatory end-of-build update template

Append or refresh the relevant build entry whenever a new ZIP, installer or
portable package is produced:

```text
Build:
Date and time:
Package filename:
SHA256:
Version shown in application:
Implementation status:
Automated tests: passed / failed / skipped / duration
Clean-package validation:
Manual tests completed:
User acceptance status:
Defects fixed:
Known issues:
Work still remaining:
Next milestone:
```

Do not mark a milestone **Accepted** merely because its tests pass. Record the
latest validated candidate, preserve older packages, and wait for explicit user
acceptance before replacing the accepted baseline.

---

# Explicitly deferred beyond R4 Final

These ideas remain valuable, but including them before the first stable release would create unacceptable scope and risk:

- Built-in EPUB/PDF reader
- Reading-progress synchronisation
- Mobile applications
- Web dashboard
- Multi-user server mode
- Cloud-library synchronisation
- OCR pipeline
- AI-generated summaries or recommendations
- Remote library administration
- Public plugin marketplace
- macOS and Linux distributions

They should be considered for R4.x or R5 only after production usage provides evidence for their priority.

---

# Roadmap governance

This roadmap is a living planning document, but changes require explicit approval.

When changing the sequence:

- Explain why the dependency order changed.
- Identify effects on safety, migration and testing.
- Update package names and outputs consistently.
- Do not mark work complete based only on planned intent.
- Preserve prior release records rather than rewriting history.

**Atlas principle:** challenge attractive scope expansion when it threatens reliability, recoverability or completion. Twano should reach a trustworthy production release before pursuing every possible feature.

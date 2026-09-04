## R4 RC1 — Production release candidate

- Cover lookup now retries a verified title and author without the edition
  ISBN when an exact metadata edition has no image, allowing another edition
  to supply the cover automatically. Unrelated low-confidence images no longer
  suppress that retry, and an exact-title pass handles older catalogue records
  that credit an underlying author instead of the ebook's house name.
- Changed series organisation to `-=Series=- / Series Name / numbered book` so a
  reading order stays together when different volumes have different authors.
  Standalone books continue to use their author folder.
- Added optional Series group and Group number metadata. Nested series are
  organised as `-=Series=- / Group / Series / numbered book`, while ordinary
  series keep the simpler structure. Verified Belgariad and Sparhawk component
  series are grouped automatically, and unnumbered retail collections are not
  migrated into the reading-order tree.
- Added a live **New file** path beside **Original file** in Metadata & Cover
  Art so the exact proposed Author/Series destination is visible before
  Preview or Apply.
- Added a non-blocking startup check for validated, data-only provider search
  locations, with a cached fallback and strict HTTPS/domain allow-list.
- Added Open Library first-sentence matching as a second provider for bounded
  low-confidence EPUB identification.
- Added a conservative Wikipedia work resolver for short stories whose actual
  metadata and cover belong to a containing collection.
- Froze the user-accepted Beta 2 application behaviour.
- Aligned application, Windows resource and installer versions to **R4 RC1**.
- Added overwrite-safe timestamped Windows build folders and automatic SHA256
  files for portable and installer artifacts.
- Added the RC1 release notes, known release gates, automated report and
  focused clean-install/upgrade/uninstall testing guide.
- Imported structured series names and reading order from Open Library,
  Google Books and Hardcover, recognised Amazon's
  `Title (Series Name Book 12)` format, refreshed older cached results and
  kept conflicting provider series visible for review.
- Allowed genuine unnumbered collections from Google Books to retain their
  series folder and use a normal unnumbered filename instead of blocking the
  protected Preview when no reading position exists.
- Updated Amazon's result parser for current linked-heading cards, rejected
  unrelated Apple Books matches, and retained clear provider-block messages.
- Reflowed compact Metadata review so essential fields and cover actions fit
  at 900 x 600 without clipped fields or whole-page scrolling.
- Kept Metadata fields directly beneath **Possible matches** at maximised
  sizes instead of stretching a large empty gap through the review panel.
- Restored the warm open-book sidebar identity and changed the centred product
  wording to **Twano's** with **eBook Manager** directly underneath.
- Applied the selected warm-serif **Twano's** identity to the startup splash,
  with **eBook Manager** centred directly beneath it.
- Enlarged the warm-serif **Twano's** sidebar wordmark while keeping the
  subtitle centred and the complete navigation usable at compact sizes.
- Ensured the enlarged sidebar identity overrides the application's default
  text size instead of being silently reduced by the global stylesheet.
- Made the sidebar identity measure the live space beside its book mark and
  select the largest fitting title and subtitle sizes after every resize.
- Made the Metadata description editor grow with wrapped provider text while
  retaining an internal scrollbar for unusually long summaries.
- Ran independent online metadata providers concurrently with bounded network
  timeouts, a live elapsed-time status, and thread-safe provider-health saves.
- Returned control after loading the first available cover preview instead of
  downloading every cover result before the user could continue; other covers
  are checked when selected and broken choices are removed automatically.
- Automatically continue with the broader active-provider cover search when a
  combined metadata lookup returns no cover or its supplied cover cannot be
  displayed, matching the successful **Find Covers Only** workflow without an
  extra click or an infinite retry loop.
- Cleared a prepared Preview whenever the selected book changes and added a
  final book-ownership check before Apply, preventing a previous book's
  reviewed plan from appearing against or being applied to the current book.
- Made a successfully displayed cover part of the same protected metadata
  Preview and Apply, removing the need to select metadata and cover separately.
- Added checkable multi-format and downloaded website-rating filters to
  Library. Google Books and Apple Books ratings are reviewed and applied with
  the rest of a selected metadata match.
- After Metadata Apply, Library now clears stale filters and reselects the
  updated book so a renamed or reorganised title does not appear to vanish.
- Moved the five Library detail actions below the description in one smaller,
  evenly spaced row.
- Rejected numeric UUID fragments that fail ISBN checksums, preventing them
  from overriding accurate title-and-author searches.
- Kept trusted embedded titles and authors when an entirely numeric filename
  such as `101 - 22 - 63.epub` could otherwise be mistaken for a
  `Title - Author` filename and produce an unusable online query.
- Added a bounded retry for publisher title variants using `The Mystery of...`
  and `The Secret of...`, allowing older series filenames to resolve their
  official metadata and cover without broad fuzzy matching. Exact alternate
  titles preserve a known pen name when the catalogue credits the underlying
  author or series creator instead.
- Added a bounded EPUB opening-text fallback when every ordinary metadata
  result is 60% or lower. It checks Google Books with a short fingerprint and
  accepts only author-matching results without uploading the ebook.

## R4 Beta 2 — Reliability and performance

- Added the missing plugin **Version** column so publisher, source, version,
  status, capability, API-key state and provider health are all visible.
- Updated the Google Images cover parser for current image-result markup,
  stopped valid empty result pages being misreported as layout failures, and
  reset the obsolete version 1.0 provider warning for a fresh check.

- Added clear A–Z and Z–A alphabetical sorting to the approved Plugins list.
- Comic Vine and Hardcover searches now save their real API response health in
  the Plugins **Provider Check** column.

- Added bounded, readable affected-book and location previews to every Library
  Health issue card, including a remaining-result count and the existing route
  to the complete review workflow.
- Accepted the timestamped Beta 1 API-key status package as the new baseline.
- Added several watched folders from one **Add Folders** dialog.
- Added **Preview All Watched Folders** so every enabled source can be scanned
  without highlighting sources individually.
- Added one-confirmation **Apply All Previews** with sequential thread-safe
  source processing and an independent verified backup and Undo record for
  each watched folder.
- Replaced the separate setup and launch batch files with one self-configuring
  `launcher.bat`.
- Aligned the application, installer, portable package and documentation to
  R4 Beta 2.
- Added private/proprietary repository licensing, third-party notices,
  security-reporting guidance, strict publication ignore rules, automated
  Windows validation, Dependabot monitoring, and a GitHub-readiness audit.
- Added approved Apple Books and ISBNdb metadata/cover providers to the same
  one-button lookup. Apple Books needs no key; ISBNdb uses a user-supplied key.
- Added ISBN/title fallback across editions and enriched blank ISBN,
  description, publisher, language, date and series fields from other strong
  matches without replacing each provider's own cover choice.
- Verify every offered cover image in the background, automatically omit
  unavailable images, and reuse verified previews when users change choices.
- Removed duplicate Windows path resolution during source comparison without
  removing final filesystem, catalogue, backup or integrity checks.
- Reduced measured 10,000-book unchanged Preview from 7.06 to 3.85 seconds and
  changed Preview from 7.57 to 3.83 seconds on the development machine.
- Added selectable 1,000-, 5,000- and 10,000-book benchmark runs.
- Added live verified-backup progress after file rechecks so SQLite integrity
  and checksum work no longer appears to hang at 100% processed.

## R4 Beta 1 — Native metadata and cover plugins

- Audited every Calibre plugin ZIP supplied under `zip/` without executing it.
- Added native Google Books cover, Hardcover metadata/cover, and Comic Vine
  metadata/cover options to the approved Plugins catalogue.
- Kept cover lookup inside Twano through direct providers without requiring
  Calibre or opening provider websites.
- Added Setup required, Configure API Key, protected-key, Enable, Active,
  Disable, and key-removal states for providers that require credentials.
- Encrypted API keys for the current Windows account with DPAPI and kept them
  separate from ordinary plugin state and diagnostics.
- Made one Find Metadata & Covers action search all active direct providers
  while preserving field-level review and protected Apply.
- Added an automatic, readable cover preview to the combined lookup and made
  each **Found covers** choice display its image before selection.
- Doubled the cover preview in large/maximized windows while retaining compact
  responsive sizes so restored windows do not require page scrolling.
- Made **Find Metadata & Covers** explicitly query every active direct cover
  provider, reuse a strong ISBN found by the first metadata result, retry
  Google Books with a broader title query, report every provider searched, and
  hide low-confidence unrelated cover results.
- Escaped the Windows mnemonic marker so the button visibly includes its
  ampersand.
- Invalidated legacy metadata lookup cache entries and converted a lone ISBN-10
  to ISBN-13 so later cover providers receive the strongest identifier.
- Added protected optional Google Books API-key configuration for anonymous
  request failures or rate limits while keeping the provider usable without a
  key.
- Included provider descriptions from Google Books and Open Library in the
  same reviewable metadata result, with simple HTML removed for readability.
- Added consistent pressed feedback to every enabled button so a click visibly
  moves the button content down and right and changes its border/background.
- Detect saved provider keys that Windows can no longer unlock, request
  re-entry instead of silently treating them as configured, and verify every
  newly saved key can be read back securely.
- Report readable Google Books failures for invalid keys, disabled Books API,
  incompatible website-referrer/IP restrictions, and exhausted quota.
- Documented the exact API credentials needed for Beta testing and their
  pre-release removal process.
- Added an **API Key** column to Plugins with **API Key Added**, **Not Added**,
  **Needs Re-entry**, and **None Required** states without revealing key text.
- Added a complete ZIP audit, provider-key guide, privacy notes, and manual
  API-provider testing schedule.

## R4 RC6.7 — Protection and Undo Foundation (in development)

- Recorded RC6.6 as the accepted protected baseline.
- Added persistent absolute backup-folder and retention-age preferences.
- Added SQLite online catalogue backups with same-thread source and
  destination connection ownership.
- Added integrity verification, SHA256 evidence, and atomic sidecar manifests.
- Added immutable backup policy, record, and status values.
- Added truthful Verified, Changed, Invalid, Unverified, and Missing states.
- Added background create and verify workers with cancellation and exact
  partial-artifact cleanup.
- Added a responsive Protection & Undo page and explicit future-feature
  boundary for restore, retention cleanup, history, and Undo.
- Corrected compact Protection controls and the expanded sidebar so restored
  windows retain every right-side action without navigation scrolling.
- Added immutable change-plan items, risk, reversibility, confirmation,
  expiry, basis, and operation-status contracts.
- Added stale-basis, repeated-token, expired-plan, and high-risk confirmation
  rejection before protected execution exists.
- Added additive protection operation and operation-item tables with original
  plan JSON, affected books, initiator, component, result, backup identity,
  error, and rollback evidence.
- Added a safe no-catalogue-change plan preview, approval-only and cancellation
  controls, restart-persistent history, and readable selected-plan details.
- Added background atomic Markdown report export.
- Linked verified-backup success, cancellation, failure, backup identity, and
  exact partial-artifact cleanup into the common history.
- Kept protected Apply, Restore, retention deletion, and Undo unavailable at
  the Milestone 2 preview-only checkpoint.
- Isolated legacy MainWindow tests from the real user catalogue after the
  additive audit migration exposed their hidden default-database dependency.
- Replaced the long Protection page with fitted Backups and Plans & History
  task tabs; Plan Preview and Operation History are separated without a
  page-level scrollbar.
- Restored Home to a compact bookshelf hero and three-card dashboard while
  retaining Find a Book, and moved Check for Updates to the lower sidebar.
- Added the 900 x 600 no-page-scroll rule for future application pages.
- Added the first allowlisted protected executor for a uniquely named empty
  test collection, with Standard-mode, approval, expiry, basis, and exact-plan
  revalidation.
- Required and recorded a verified catalogue backup before protected Apply
  and Undo.
- Stored schema-validated inverse data in the same transaction as the applied
  collection change.
- Added Preview Undo as a separate source-linked audited operation that
  survives restart and leaves the original operation recorded as Undone.
- Added background Apply/Undo execution, safe pre-transaction cancellation,
  and truthful atomic rollback evidence.
- Kept Restore, retention cleanup, redo, ebook-file execution, and Scan Apply
  integration unavailable through the Milestone 3 checkpoint.
- Added a plain **Restore Backup** action with one confirmation; Twano
  re-verifies the selected snapshot and automatically creates a verified
  safety copy of the current catalogue.
- Added staged same-folder catalogue replacement, post-swap automatic recovery,
  embedded backup-audit reconciliation, and complete Restore outcome evidence.
- Added **Review Old Backups**, which presents one readable count/size summary
  and only deletes fully reverified expired Twano backup/manifest pairs.
- Excluded unrelated, changed, invalid, legacy, recent, unverified, and
  symbolic-link files from retention cleanup.
- Moved the routine Protection view to **Backups & Restore** while retaining
  detailed **Activity & Undo** history for users who need it.
- Linked the existing one-confirmation **Apply Preview** flow to a persistent
  Scan Apply protection operation without exposing another plan screen.
- Added an automatic verified catalogue backup before Scan Apply commits.
- Added an additive Scan History link so catalogue changes, scan counts, and
  the protection outcome commit as one transaction.
- Recorded cancellation and failure in both histories together, while keeping
  stale candidates and transaction failures non-mutating.
- Labelled Scan Apply recovery plainly: there is no one-click Undo, but its
  verified safety backup can restore the complete earlier catalogue.
- Made Read-Only mode disable **Apply Preview** with a direct Settings hint.
- Replaced the long Scan page scrollbar with fitted **Sources**,
  **Preview & Apply**, and **History** tabs; tables resize internally at the
  supported compact window width.

## R4 RC6.6 — Safe Scan and Import

- Accepted RC6.5 after native restored-window details validation.
- Added additive watched-source fields to the existing libraries table.
- Added detached source records, validated local/mapped/UNC path handling,
  editable recursion and glob rules, and distinct connection states.
- Added add, edit, enable, disable, archive, restore, and non-destructive
  Remove Watch service and database operations.
- Added background read-only connection testing with safe Qt worker cleanup.
- Rebuilt Scan around a responsive watched-source table and focused source
  actions.
- Added immutable, rule-aware source analysis for new, changed, unchanged,
  missing, unreadable, and skipped files.
- Added cancellation and unavailable-source safeguards that suppress missing
  classification after incomplete analysis.
- Added a background Safe Preview worker and discardable preview table.
- Added an explicit background Apply workflow that rechecks file and catalogue
  facts before mutation.
- Added one database-owned transaction for new, changed, missing, last-seen,
  source-result, and scan-history updates.
- Added rollback-safe failure handling, pre-transaction cancellation, repeat
  scan protection, and safe skips for vanished, reappeared, or stale
  candidates.
- Added recent scan history to Scan and refresh Library and Home only after a
  successful commit.
- Gave every enabled Library-details and Scan action its own labelled accent
  colour so separate commands no longer resemble a selected blue option plus
  inactive grey options.
- Kept ebook files untouched; previewing and discarding do not mutate the
  Library.

## R4 RC6.5 — Living Library

- Replaced the unbounded Library `QTableWidget` with a shared paged Qt model
  used by responsive grid and list views.
- Added database-backed search, format, author, series, collection, location,
  and metadata-status filters with allowlisted sorting.
- Added series sequence, collection, and collection-membership schema through
  additive, data-preserving initialization.
- Added one responsive book-details panel with file, identifier, description,
  metadata-quality, issue, and collection information.
- Added database-only collection creation and atomic membership replacement;
  ebook files are never moved or modified.
- Added background cover decoding, painted missing-cover states, bounded LRU
  pixmap caching, and stale-result rejection.
- Added validated persistent grid/list, density, sorting, direction, and
  details visibility preferences.
- Added distinct loading, empty-library, no-match, and query-failure states.
- Added a Windows-safe pytest runtime configuration and expanded the full suite
  from 55 to 81 tests.
- Corrected Explorer selection for paths containing spaces and added a Calibre
  ebook-viewer fallback when Windows has no real ebook file association.
- Renamed the route-only Metadata action to avoid implying that RC6.5 already
  includes metadata editing.
- Reflowed Library options into three compact rows and constrained long filter
  values so non-maximized windows retain every right-side control.
- Separated toolbar reflow from details replacement so restored windows keep
  the details pane visible while genuinely narrow layouts use a full-page
  detail view.
- Moved book actions above long cover and metadata content, constrained them to
  the panel width, and made one compact book click open the detail actions.

## R4 RC6.4 — Responsive Home and Smart Search

- Reworked sidebar sizing around clamped width-and-height calculations so all
  approved navigation destinations fit normal desktop window sizes.
- Kept the hero at a compact fixed height while cards, actions, spacing, and
  status content absorb the remaining fullscreen space.
- Replaced inline Home results with a floating, keyboard-accessible suggestion
  panel that leaves dashboard geometry unchanged.
- Added a dedicated Search Results page with query refinement, filter
  structure, detailed results, reader launching, and Library routing.
- Made metadata warnings actionable through a filtered Review Queue that
  identifies weak fields and provides direct review actions.
- Replaced numeric page indexes with explicit page IDs and reset transient Home
  search state whenever Home is revisited.
- Completed the seven-image Home banner system with fixed and
  rotate-on-startup modes, legacy preference migration, validation, and safe
  missing-asset fallback.

## R4 RC6 — Home Experience

- Rebuilt Home as a calm landing page rather than a statistics dashboard.
- Added square dark hero design, global book search, reader launching and Reading settings.
- Added Analytics navigation placeholder for RC7.
## R4 RC5.3 — Living Dashboard

- Added responsive cover previews to the Books card on large displays.
- Added live library-location previews.
- Added a storage-by-format donut chart.
- Added metadata-attention title previews.
- Added success artwork when no files are missing.
- Added four metadata-health bookshelf states in 25% bands.
- Added book-style format visuals and improved recent additions.
- Preserved compact text-first layouts on smaller displays.

## R4 RC5.2 — Proportional Dashboard Fix

- Fixed dashboard panel proportions at wide and compact window sizes.
- Added adaptive hero typography and collision-free theme labelling.
- Added viewport-aware spacing and component heights.


## R4 RC3 — Dashboard Reimagined

- Rebuilt the entire Home dashboard.
- Added seven self-rendered Hero Banner themes.
- Added responsive metric, health and format panels.
- Fixed immediate Settings refresh and preference synchronisation.

## R4 RC2 — The Homecoming

- Added the Hero Banner framework and Dynamic Welcome Panel.
- Added Standard and Read-Only protection modes.
- Added persistent Home and protection settings.
- Added neutral library insights and time-of-day greetings.
- Added project vision, ADRs, handover and GitHub upload documentation.

## R4 RC4 — Dashboard Perfection
- Added recent additions backed by SQLite data.
- Added last-scan and seven-day activity summaries.
- Refined reusable metric cards and dashboard panels.
- Deferred final hero artwork until the visual-design phase.

## R4 RC6.1 — Responsive Home
- Responsive sidebar width, fonts, navigation spacing and Home card typography.
- Restored User Guide, What's New and About navigation pages.
- Added scalable navigation symbols and improved maximised-screen presentation.

## R4 RC6.2 — Twano Navigation System
- Rebuilt the sidebar to match the darker concept design.
- Added large DPI-aware icons and stronger Segoe UI navigation typography.
- Added clear primary and support navigation groups with a divider.
- Added responsive sidebar widths, icon sizes, row heights and branding.
- Replaced the compact protection badge with a richer Protection Mode status panel.
- Changed navigation routing to explicit page IDs so visual separators cannot break page selection.

## R4 RC6.3 — Twano Design System
- Added scalable book branding, colour-coded navigation and larger application-wide typography.
## R4 Beta 1 — Complete Library Test Package

- Added filename-aware metadata queries so a clear `Title - Author` filename
  can correct noisy embedded search terms without renaming the ebook.
- Expanded Google Books from cover-only search to metadata and cover results.
- Combined metadata and cover lookup into one action and one review page.
  Open Library, Google Books, Hardcover, and Comic Vine return book details
  and available covers without opening browser search websites.
- Changed Remove Watch to show the associated book count and, after explicit
  confirmation, remove that source's books from the Twano Library in one
  background transaction. Folders, ebook files, and other sources are
  unchanged.
- Corrected the Plugins page so actions preserve the selected row, enabled
  plugins show **Active**, success messages remain visible, unavailable actions
  are visibly disabled, and the Install → Enable workflow is unambiguous.
- Consolidated the approved metadata, covers, duplicates, health, Calibre,
  network, plugin, settings, accessibility, guidance, packaging, and testing
  recommendations into one feature-complete Beta.
- Simplified the visible navigation and moved the global library/book/version
  status plus compact update action to the bottom bar.
- Completed manual Open Library metadata and cover lookup with explainable
  matching, field-level selection, preview, verified backup, and atomic Apply.
- Added exact-content and possible-edition duplicate evidence, intentional
  exceptions, recoverable quarantine, and Restore.
- Added deterministic actionable Library Health without a technical analytics
  dashboard.
- Added safe Calibre detection/opening, network diagnostics, and controlled
  approved plugins.
- Completed in-app User Guide, What's New, About, privacy information,
  accessibility preferences, Windows build scripts, and the full Beta test
  schedule.
- Moved new Beta data to `%LOCALAPPDATA%\Twano` while leaving the previous
  development catalogue untouched.
- Added a **Search provider** choice to Metadata & Covers. Users can search
  every active provider or restrict a lookup to one active provider such as
  Comic Vine, and the left navigation now uses the clearer
  **Metadata & Covers** name.
- Added general CBR/CBZ filename recognition for `(Publisher) Series 001`,
  `[Publisher] Series 001`, and `Series #001` patterns. Comic Vine now matches
  the series volume first and then requests the exact issue number, returning
  issue-specific titles, creators, dates, descriptions, series fields, and
  covers instead of a generic volume result.
- Made the Metadata & Covers thumbnail clickable. It now opens the full cached
  image in a separate, screen-bounded large-cover viewer with mouse, keyboard,
  and Close-button access.

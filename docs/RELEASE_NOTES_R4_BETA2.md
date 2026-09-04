# Twano R4 Beta 2 Release Notes

**Release name:** Reliability and Performance Test Package  
**Purpose:** Beta 2 reliability, provider, and multi-folder Windows testing

## What is complete

- Calm Home page with restored bookshelf hero, three information cards, search,
  configurable banners, and a compact global status/footer.
- Responsive grid/list Library with filters, details, distinct action colours,
  collections, and correctly routed book/folder/metadata actions.
- Multi-folder local, mapped, and UNC sources with connection checks,
  one-click Preview All, sequential guarded Apply All, scan history,
  offline-source protection, and a
  clearly confirmed Remove Watch action that removes only the selected source's
  Twano catalogue entries while preserving every ebook file.
- Verified catalogue backups, human-readable change plans, persistent audit
  history, Restore, retention review, and supported Undo.
- One-button, filename-aware metadata and cover lookup through active Open
  Library, Google Books, Hardcover, and Comic Vine providers. Users can search
  every active provider or select one provider, such as Comic Vine, for the
  current lookup. Results and covers share one page and no browser-based cover
  search is required.
- Issue-aware CBR/CBZ searches recognise common publisher, series and numeric
  issue filename patterns. Comic Vine now retrieves the exact issue record and
  issue-specific cover instead of stopping at a generic series volume.
- Clicking a loaded cover thumbnail opens its full cached image in a larger,
  screen-bounded viewer without selecting or applying any changes.
- Exact-content and possible-edition duplicate groups, intentional exceptions,
  recoverable quarantine, and Restore.
- Deterministic, actionable Library Health with a short affected-book or
  location list on every issue card and a clear remaining-result count.
- Controlled built-in plugin/provider catalogue and strict approved-hash checks
  for external packages, with clear Install, Enable, Active, Disable, and
  Disabled states, visible publisher/source/version/capability details, and
  A–Z/Z–A provider sorting. API-key providers include masked setup,
  Windows-account encryption, in-app key instructions, and persisted provider
  response checks after a real search. Google Images supports current image
  result markup and no longer reports a valid empty result as a layout change.
- Read-only Calibre detection/opening and network-library diagnostics.
- Completed Settings, accessibility preferences, User Guide, What's New, About,
  privacy notes, packaging scripts, and the full Beta test schedule.
- Added repository publication safeguards, a proprietary licence, third-party
  notices, a security policy, automated Windows tests, Dependabot monitoring,
  and a repeatable GitHub-readiness audit.

## Product simplification

The visible navigation is limited to everyday tasks. Detailed Review Queue,
Duplicates, and Protection pages remain available from the relevant workflow
instead of permanently occupying the navigation. Full analytics were omitted;
Library Health contains the useful actionable information.

## Fresh catalogue

Beta 2 uses `%LOCALAPPDATA%\Twano`. The older development catalogue under
`%USERPROFILE%\.twanos_ebook_manager` is left untouched.

## Distribution

This test delivery is a source ZIP. Use `launcher.bat` for both first-run setup
and every later launch. The repository includes repeatable PyInstaller/Inno
Setup build scripts, but the enclosed package is not a signed production
installer.

See `KNOWN_ISSUES_R4_BETA2.md` before testing and follow
`R4-Beta2-Complete-Testing-Guide.md`.

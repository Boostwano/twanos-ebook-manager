# Twano R4 Beta 2 Change Specification

## Purpose

R4 Beta 2 hardens the accepted Beta 1 feature set for daily use. It does not
add major product areas. The priority order is data integrity, reliability,
performance, accessibility, understandable recovery and accurate guidance.

## Accepted baseline

```text
C:\Twano\Builds\2026-07-30-1513-Twano-R4-Beta1-Plugin-API-Key-Status-Test-Package.zip
SHA256 F49B1C4C52F110C0C30821A8D1B676806124BC7228E4CCF5462EDDDA5FFA03A4
210 passed, 0 failed, 0 skipped
User accepted 30 July 2026
```

## Scope

### Performance

- Measure 1,000-, 5,000- and 10,000-book catalogue workflows.
- Separate discovery, comparison, metadata extraction, safety recheck, backup,
  SQLite verification and database Apply timings.
- Optimise repeated scans and unnecessary work without weakening safety gates.
- Keep all long work outside the GUI thread and cancellable at safe boundaries.
- Bound thumbnail and metadata lookup caches.
- Record machine-specific observations rather than universal promises.

### Reliability and recovery

- Repeat scan Preview and Apply after success, cancellation and failure.
- Test forced termination before backup, during backup and before Apply.
- Verify startup recovery does not publish partial backup or credential files.
- Exercise backup, Restore and Undo across application restarts.
- Test database and settings migration from supported Beta 1 data.
- Keep offline mapped/UNC sources separate from missing files.

### Provider resilience

- Preserve successful results when one provider times out or rejects a key.
- Search approved Open Library, Google Books, Apple Books, ISBNdb, Hardcover
  and Comic Vine providers independently of Calibre.
- Retry by title/author when one edition ISBN is incomplete, and fill blank
  fields from other strong matches for the same work.
- Remove a cover option when its image cannot be downloaded or previewed,
  then automatically check the next result. Metadata-only matches remain
  available for book details but do not appear as cover choices.
- Give readable timeout, invalid-key, disabled-API, restriction and quota
  messages.
- Ensure API keys are never logged, displayed in result text or packaged.
- Confirm a malformed provider response cannot crash lookup.

### Accessibility and interface

- Complete keyboard navigation and logical focus order for core workflows.
- Provide accessible names/descriptions for icon-only or ambiguous controls.
- Preserve visible focus and pressed states.
- Validate 100%, 125%, 150% and 200% text/display scaling where practical.
- Check colour contrast and ensure state is never communicated by colour alone.
- Keep supported 900 x 600 layouts free of page-level scrolling and clipped
  actions.

### Documentation

- Update the User Guide alongside every corrected workflow.
- Add a Beta 2 acceptance schedule.
- Record performance measurements, accessibility results, known limitations
  and clean-package evidence.
- Keep the master roadmap's remaining-work ledger current.

## Non-goals

- New reader, cloud, mobile or AI features
- An unrestricted public plugin marketplace
- New website scrapers without a documented, approved interface
- Removing backup, preview, verification or Undo safety to gain speed
- Final installer signing, which remains an RC1 production gate

## Completion gate

- No unresolved critical data-loss, startup or workflow-blocking defect.
- Full automated suite, compilation and clean-package validation pass.
- Performance targets and observed results are recorded.
- Keyboard, scaling, contrast and compact-layout checks are recorded.
- The complete Beta 2 manual guide is ready for user acceptance.
- A timestamped ZIP and SHA256 are produced without overwriting Beta 1.

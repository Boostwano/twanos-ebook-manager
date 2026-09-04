# Twano R4 RC6.5 Milestones Brief

**Release:** Twano R4 RC6.5 — Living Library  
**Status:** Accepted on Windows on 28 July 2026

## Milestone 0 — Baseline and contract

- Start only from the accepted RC6.4 package.
- Run compilation and the complete 55-test baseline.
- Record existing Library behavior and representative query counts.
- Approve this brief and the RC6.5 change specification.

Exit:

- Baseline is reproducible.
- Scope and non-goals are accepted.
- No RC6.5 source change precedes the baseline.

## Milestone 1 — Database and service paging

- Add series-sequence and collection schema.
- Add safe schema migration and indexes.
- Add allowlisted sorting, filters, counts, limit, and offset.
- Expand immutable Library records and filter options.
- Add database and service tests.

Exit:

- Paged results and counts are correct.
- Invalid sort input cannot alter SQL structure.
- Collection membership is transactional and file-neutral.
- Existing search and dashboard queries remain compatible.

## Milestone 2 — Shared Library model and preferences

- Add one paged Qt model used by both views.
- Preserve selection and loaded pages across view changes.
- Add validated view, density, and sort preferences.
- Add loading, empty, no-results, and failure model states.

Exit:

- View switching produces no presentation-only database reload.
- Paging fetches each page once.
- Invalid preferences fall back safely.

## Milestone 3 — Grid, list, and thumbnails

- Build responsive cover-grid presentation.
- Replace `QTableWidget` with a model/view list presentation.
- Add background thumbnail decoding.
- Add bounded cache and stale-result protection.
- Add painted missing-cover artwork.

Exit:

- Both views use the shared model.
- Cover work does not block the GUI event loop.
- Missing and corrupt covers remain safe.

## Milestone 4 — Details, series, collections, and actions

- Add one responsive details widget.
- Show series, sequence, identifiers, files, dates, metadata quality, and
  collections.
- Add basic collection creation and membership.
- Add series grouping or contiguous series sorting.
- Route actions through shared reader, folder, Metadata, and Review Queue
  pathways.

Exit:

- Details update with selection in either view.
- Collection operations change only Twano database state.
- No ebook file or metadata mutation is introduced.

## Milestone 5 — Hardening and package gate

- Generate and exercise a 10,000-record synthetic dataset.
- Run compilation, focused tests, and the full regression suite.
- Complete the Windows UI and keyboard checklist.
- Update version, architecture, database, release, and handover documents.
- Build, inspect, extract, and smoke-launch the RC6.5 ZIP.

Exit:

- RC6.5 change specification is satisfied.
- Performance observations are recorded.
- No unresolved data-integrity, startup, or GUI-thread blocker remains.
- Human review accepts the package before RC6.6 begins.

## Expected file set

The implementation should remain close to this expected set. Variations must
be explained in the handover.

### Existing files likely to change

- `src/config.py`
- `src/preferences.py`
- `src/database/database.py`
- `src/services/library_service.py`
- `src/ui/library_page.py`
- `src/ui/book_actions.py`
- `src/main_window.py`
- `tests/test_database.py`
- `tests/test_library_page.py`
- relevant README, architecture, database, roadmap, changelog, release, and
  handover documents

### Focused new modules likely to be added

- `src/ui/library_model.py`
- `src/ui/library_grid.py`
- `src/ui/book_details.py`
- `src/ui/thumbnail_cache.py`
- `src/workers/thumbnail_worker.py`
- focused service, model, UI, preference, and thumbnail tests

Do not create parallel Library services, duplicate details widgets, or a new
SQL-owning UI layer.

## Review questions before implementation

- Confirm the responsive side-panel details presentation.
- Confirm that basic collection membership is in RC6.5 while smart collection
  rules remain deferred.
- Confirm the initial page size and bounded thumbnail-cache target during
  implementation based on measured behavior.
- Confirm that Metadata and Review actions route without introducing edits
  before RC6.7 protection infrastructure.

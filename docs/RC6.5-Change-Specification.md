# Twano R4 RC6.5 — Living Library

## Status

**Accepted on Windows on 28 July 2026.**

## Accepted source

Continue only from the accepted:

```text
Twano-R4-RC6.4-Responsive-Home-and-Smart-Search.zip
```

Do not alter or replace the accepted RC6.4 package while RC6.5 is under
development.

## Goal

Transform Library from a basic table into a responsive digital bookshelf with
fast grid and list views, useful book details, strong filters, series support,
and a safe collection foundation.

## Product guardrails

- Preserve the accepted RC6.4 Home, search, navigation, banner, scan, and
  reader behaviour.
- Keep the dependency direction `UI -> Services -> Database -> SQLite`.
- UI modules must not contain SQL.
- Database modules must not import PySide6.
- Do not perform database or image work that can noticeably block the GUI.
- Do not modify, move, rename, or delete ebook files in RC6.5.
- Do not implement metadata writes before the protection foundation.
- Missing covers, files, fields, and folders must produce calm empty states.

## Approved design decisions

### Shared data model

Grid and list views will share one paged Library result model. Switching views
must retain the current query, filters, sort, selection, and loaded records
without re-querying solely because the presentation changed.

### Details presentation

Use a responsive side panel on wide layouts. On compact layouts, the same
details widget may replace or overlay the browser area with a clear Back
action. Do not create a second competing book-details implementation.

### Performance strategy

Replace unbounded `QTableWidget` population with Qt model/view components and
database-backed paging. Load an initial page and fetch additional pages on
demand. Cover decoding and thumbnail creation must use background workers;
`QPixmap` creation and widget updates remain on the GUI thread.

### Safe action boundary

`Open Book` and `Open Folder` may act immediately through shared launch
helpers. `Edit Metadata` and `Review Issues` route to the existing Metadata and
Review Queue destinations. RC6.5 must not introduce direct metadata or file
mutation.

## Required changes

### 1. Library query contract

Add immutable service values for:

- book ID
- title and author
- series name and sequence
- identifiers
- description
- cover path
- format and size
- file and library locations
- date added and file-modified date
- metadata status and issue count
- collection names

Add a paged query contract containing:

- matching records
- matching count
- active-library total
- offset and page size
- whether another page is available

Supported sorting:

- title
- author
- series and sequence
- date added
- file-modified date
- format
- metadata quality

Sort fields and directions must use explicit allowlists. Never interpolate
unvalidated UI text into SQL.

### 2. Filters

Library filters must cover:

- search text
- format
- author
- series
- collection
- library location
- metadata status

Filter options must come through `LibraryService` and database methods. The UI
must preserve selected values when options refresh and provide one clear reset
action.

### 3. Database foundation

Extend the additive schema safely:

- add nullable `series_number`
- expose `discovered_at` and `file_modified_at` in Library queries
- add a `collections` table with a unique, case-insensitive name
- add a `book_collections` join table with cascading foreign keys
- add indexes required by paging, sorting, series, and collection filters

Collection changes affect only Twano's database. They must use explicit
transactions and must never alter ebook files.

### 4. Grid view

Provide:

- responsive cover cards
- title, author, series, and format
- painted missing-cover placeholder
- selectable compact, comfortable, and spacious density
- keyboard selection and activation
- incremental page loading
- clear empty-library and no-results states

### 5. List view

Provide an information-rich `QTableView` or equivalent model/view control with:

- sortable columns
- title, author, series, format, size, metadata status, and location
- keyboard selection and activation
- the same records and selection as grid view
- no full database reload merely to switch presentation

### 6. Book details

The shared details widget must show:

- cover or missing-cover state
- title and author
- series and sequence
- description
- ISBN and other available identifiers
- format and size
- file location and modified date
- metadata quality and issue summary
- collections

Actions:

- Open Book
- Open Folder
- Edit Metadata
- Review Issues

Unavailable actions must explain why rather than failing silently.

### 7. Series and collections

- Display series and sequence consistently in both views and details.
- Support grouping or contiguous sorting by series.
- Allow filtering by series.
- Provide basic collection creation, assignment, removal, and filtering.
- Collection removal must remove membership only; it must not remove books or
  files.
- Do not add a general smart-collection rules engine in RC6.5.

### 8. Preferences

Persist and validate:

- grid or list view
- cover density
- sort field and direction
- details-panel visibility where appropriate

Invalid or legacy values must fall back safely without preventing Library from
opening.

### 9. Cover loading and caching

- Never assume a cover path exists or is readable.
- Decode and scale covers outside the GUI thread.
- Use a bounded in-memory thumbnail cache.
- Key cached entries by path plus modification information.
- Ignore stale worker results after the visible query changes.
- Do not download covers in RC6.5.

### 10. Empty and failure states

Provide distinct states for:

- no library records
- no filter matches
- missing cover
- missing file
- unavailable library location
- failed thumbnail load

Errors shown to users must provide a useful next action.

## Performance validation

Create a deterministic synthetic Library dataset with at least 10,000 records.
Record:

- initial query and first-page render time
- filter and sort query time
- incremental page-fetch time
- view-switch behavior
- thumbnail cache size and eviction behavior

The interface must continue processing events during cover work. Results must
be recorded truthfully against the validation machine rather than claiming an
unmeasured universal timing guarantee.

## Automated testing

Add tests for:

- additive schema migration
- collection foreign keys and membership
- every allowed sort field and direction
- rejected invalid sort fields
- paging boundaries and counts
- filter combinations
- stable grid/list view switching
- persisted and invalid preferences
- series sorting and display
- missing covers and files
- bounded thumbnail caching and stale-result rejection
- details-panel selection
- action routing
- empty-library and no-results states

Run:

```text
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pytest -v
```

## Manual Windows testing

Verify:

- grid and list views at supported RC6.4 window sizes
- compact, comfortable, and spacious cover densities
- keyboard-only browsing and details actions
- view switching without visible reset or duplicate query
- paging with a large synthetic library
- missing and corrupt covers
- missing files and unavailable folders
- all Library filters and sorts
- series grouping and collection membership
- Open Book and Open Folder
- routing to Metadata and Review Queue
- clean application shutdown with no worker warnings

## Documentation and release records

Update:

- application version and release title
- `README.md`
- `CHANGELOG.md`
- `ROADMAP.md`
- `PROJECT_HANDOVER.md`
- architecture and database documentation
- Master Delivery Roadmap status
- RC6.5 test report and release notes

## Output package

```text
Twano-R4-RC6.5-Living-Library.zip
```

## Non-goals

- built-in ebook reader
- metadata editing or provider expansion
- file rename, move, or delete operations
- cover downloading
- smart-collection rules engine
- duplicate resolution
- cloud sync
- recommendations or social features
- RC6.6 scan-source work

## Exit criteria

- Grid and list views share one paged record source.
- Switching views preserves state without an unnecessary database reload.
- Filters and sorts return correct paged results.
- Details remain usable with missing metadata, covers, files, and locations.
- Series and basic collections work without modifying ebook files.
- Cover work does not block the GUI thread.
- Existing RC6.4 behavior remains green.
- Automated, large-library, Windows, and package validation are recorded.

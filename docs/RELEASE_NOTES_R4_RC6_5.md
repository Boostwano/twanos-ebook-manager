# Twano R4 RC6.5 — Living Library

RC6.5 turns Library into a responsive bookshelf while preserving the accepted
RC6.4 Home, search, banner, navigation, scan, review, and reader behavior.

## Highlights

- Grid and list views share one paged result model and one selection.
- Switching views retains loaded records without a presentation-only query.
- Filters cover text, format, author, series, collection, library location,
  and metadata status.
- Sorting covers title, author, series/sequence, date added, file modified,
  format, and metadata quality through explicit database allowlists.
- A single responsive details panel shows cover, description, identifiers,
  series, file facts, metadata issues, and collections.
- Restored windows keep that panel visible even while Library controls reflow.
- Compact details reuse that widget with single-click activation and a clear
  Back action.
- Cover images decode and scale outside the GUI thread.
- A bounded 192-item thumbnail cache rejects stale visible-query results.
- Missing files, covers, folders, fields, empty libraries, no matches, corrupt
  covers, and query failures have explicit calm states.
- Library view, cover density, sort, direction, and details visibility persist
  through validated preferences.

## Series and collections

- Existing databases gain nullable `series_number` through additive migration.
- Collections use unique case-insensitive names and cascading join records.
- Membership replacement is atomic and affects only Twano's SQLite catalogue.
- Ebook files are never moved, renamed, deleted, or modified by collection
  actions.

## Safe action boundary

- Open Book continues to respect Reading preferences.
- Open Folder uses the native containing-folder path when available.
- View Metadata and Review Issues route to existing destinations. The Metadata
  copy states clearly that editing is not part of RC6.5.
- RC6.5 does not write metadata, download covers, or add file-management
  operations.

## Compatibility and validation

- Existing unpaged `LibraryService.get_library()` remains compatible with Home
  suggestions, Search Results, and Review Queue.
- The RC6.5 Library browser uses its new paged background contract.
- Compilation passes and the complete automated suite contains 81 passing
  tests with no failures or skips.
- A deterministic 10,000-record run measured first-page query and model/table
  render at under 60 ms combined on the validation machine.
- Native Windows acceptance through `launcher.bat` remains the final candidate
  gate.

## Known limitations

- Covers are local only; RC6.5 does not download artwork.
- Search Results and Review Queue retain their earlier unpaged result contract.
- Metadata editing, smart collections, file mutation, built-in reading, and
  cloud sync remain outside RC6.5 scope.

## Windows acceptance fixes

- Open Folder now passes Explorer's `/select,` switch separately from the full
  file path, including paths containing spaces.
- When Windows reports only `OpenWith.exe` (or Calibre's library application)
  for an EPUB-family file, Twano uses an installed Calibre
  `ebook-viewer.exe`. Explicit Custom readers and real Windows associations
  still take priority.
- Non-maximized Library options reflow across three rows, and long filter
  choices can shrink without pushing controls beyond the right edge.
- Toolbar reflow and details replacement use separate width thresholds, so an
  1180-pixel restored window keeps the right-hand details pane.
- Open Book, Open Folder, View Metadata, Review Issues, and Manage Collections
  appear before long detail content and fit without horizontal scrolling.

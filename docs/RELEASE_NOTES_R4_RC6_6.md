# Twano R4 RC6.6 — Safe Scan and Import

## Accepted release

Watched Library sources, non-mutating Safe Preview, guarded transactional
Apply, and recent scan history are available. Native Apply acceptance and the
hardening/package gate are complete.

## Watched sources

- Existing RC6.5 library locations migrate automatically.
- Add local folders, mapped-drive paths, and UNC-shaped locations.
- Edit the source name, recursion setting, and relative include/exclude rules.
- Enable or disable watching without changing Library books.
- Remove Watch archives the source configuration while retaining its books.
- Re-adding an archived path restores the same source identity.

## Connection safety

- Test Connection performs read-only root enumeration.
- Connection work runs through a dedicated Qt worker and thread-owned database
  connection.
- Available, unavailable, non-folder, permission-denied, disabled, and
  not-tested states remain distinct.
- An unavailable source is not treated as evidence that its books were
  deleted.

## Interface

- Scan now begins with a watched-source table and focused source actions.
- The page scrolls at constrained heights instead of overlapping controls.
- Compact mode hides secondary Rules and Last scan columns.
- Preview Scan classifies New, Changed, Missing, Unreadable, Unchanged, and
  Skipped outcomes.
- Preview automatically scrolls to a discardable result table.
- Apply is enabled only for complete connected previews with catalogue
  changes.
- Recent Scan History shows applied, cancelled, failed, and safely skipped
  outcomes.
- Enabled Scan actions use distinct colours for adding, editing, testing,
  toggling, removal, Preview, Cancel, Discard, and Apply. Disabled actions
  remain deliberately subdued.

## Library action clarity

- Open Book, Open Folder, View Metadata, Review Issues, and Manage Collections
  now use distinct blue, teal, violet, amber, and green accents.
- The colours identify different commands; they do not indicate selection.
- Disabled actions retain the common subdued state so unavailable commands
  remain clear.

## Preview safety

- Analysis runs on a dedicated Qt worker.
- Source recursion and include/exclude rules constrain its scope.
- Size, modification time, and a fast fingerprint identify changes.
- Cancellation and incomplete walks suppress missing classification.
- Unavailable sources do not create mass missing previews.
- Preview and Discard do not change Library books or counts.

## Apply safety

- Apply runs outside the GUI thread and remains cancellable before mutation.
- Source settings, catalogue facts, and filesystem state are rechecked.
- New and changed candidates refresh metadata; unchanged metadata is preserved.
- A final existence/fingerprint check safely skips vanished, reappeared, or
  modified candidates.
- Books, source result evidence, and history commit in one database
  transaction; failures roll back the entire unit.
- Complete connected previews may mark confirmed missing books.
- Repeat previews do not create duplicate book paths.
- Ebook files are never moved, renamed, edited, or deleted.

## Validation

- Compilation passes.
- The full suite contains 105 passing tests with no failures or skips.
- Restored 1180 × 790 and compact 1000 × 720 source, preview, and Apply/history
  layouts were inspected offscreen.
- Native Windows Safe Preview was accepted on 28 July 2026.
- Native Windows Apply/history behavior was accepted on 28 July 2026.
- A representative 5,000-file source completed Preview, repeat Preview,
  changed Preview, guarded Apply, cancellation, and unavailable-source checks
  with matching catalogue/history assertions.
- The 142-entry release ZIP passed integrity inspection, clean-extraction
  compilation, all 105 tests, six UI smoke captures, and version validation.

The refreshed RC6.6 release was accepted on Windows on 28 July 2026.

# Twano R4 RC5 — User Experience Refresh

## Focus

This milestone introduces Twano's shared visual design system and fixes the two usability problems identified during Windows testing.

## Changes

- Added a shared application theme in `src/ui/theme.py`.
- Replaced black-and-white table striping with two readable dark row colours.
- Added consistent table headers, selection, hover, grid lines and scrollbars.
- Applied the shared table behaviour to Library and Scan.
- Reduced Library and Scan page margins to improve usable space at smaller resolutions.
- Rebuilt the Home dashboard as a fit-to-window layout without a page-level scroll area.
- Reduced hero, card and panel height while retaining all core dashboard information.
- Limited Recent Additions to the three most useful entries on the compact dashboard.
- Combined format and last-scan information into one compact panel.
- Updated the displayed release version to R4 RC5.

## Testing

- Python source compilation passed.
- 28 non-Qt automated tests passed.
- Qt graphical tests require PySide6 and must be completed on Windows.

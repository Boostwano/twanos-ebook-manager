# Twano R4 RC3 — Dashboard Reimagined

## Home dashboard rebuild

- Replaced the original placeholder-style dashboard.
- Added a responsive, scrollable dark dashboard layout.
- Added a full-width hero banner rendered directly by Qt.
- Added seven distinct built-in banner scenes and palettes.
- Removed the dependency on external banner image paths.
- Added six compact library metric cards.
- Added metadata-health progress and explanatory status text.
- Added a cleaner format summary panel.
- Preserved launch-time greeting behaviour and live library insights.

## Settings and protection fixes

- Protection Mode values are normalised before storage.
- Preferences are explicitly synchronised after saving.
- The sidebar protection indicator updates after every save.
- The dashboard refreshes and repaints immediately after settings are saved.

## Validation

- Python source compilation: passed.
- Non-UI automated tests: 28 passed.
- Full PySide6 graphical testing must be completed on Windows.

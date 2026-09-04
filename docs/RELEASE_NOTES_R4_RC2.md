# Twano R4 RC2 — The Homecoming

## Added

- Dark Home-focused visual refresh
- Hero banner framework with seven named banner choices
- Dynamic Welcome Panel
- Time-of-day greeting selected once per launch
- Live library summary and Today's Insight
- Standard and Read-Only protection modes
- Persistent Home preferences through QSettings
- Functional Settings page for Home and protection preferences
- Sidebar protection status indicator
- Project vision and architecture decision records

## Important limitations

- Banner artwork files are not yet bundled; RC2 implements the banner framework and presentation area.
- Read-Only mode is visible and persisted, but every future write workflow must still be wired to enforce it before production release.
- Full UI test execution requires PySide6 in the test environment.

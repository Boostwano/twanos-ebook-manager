# Twano R4 RC6.4 — Responsive Home and Smart Search

RC6.4 keeps Home welcoming while making search and metadata warnings directly
useful.

## Highlights

- Sidebar content scales to fit normal supported desktop sizes, with scrolling
  retained only as an emergency fallback.
- Home keeps a compact fixed-height hero while card typography, icons, buttons,
  padding, and spacing grow and shrink within readable limits.
- Greeting labels use their real font metrics, preventing descenders from being
  clipped.
- Home suggestions float over dashboard content and support Up, Down, Enter,
  Escape, outside-click dismissal, and a View all destination.
- Search Results is a dedicated page with detailed book rows and an expandable
  set of format, author, series, metadata, and location filters.
- Metadata warnings provide a Review Now action that opens a filtered Review
  Queue and lists missing or weak fields.
- Returning Home clears the transient query, selection, popup, and focus.
- Home now displays all seven bundled hero-banner artworks.
- Banner settings provide a fixed choice or one rotation per application
  startup.
- Legacy and invalid banner preferences are migrated or corrected
  automatically, with a painted fallback if artwork is unavailable.

## Safety and compatibility

No file-changing workflow was added. Opening a result continues to respect
Windows default, custom reader, ask-every-time, and containing-folder Reading
settings. SQLite schema changes are additive and connections remain
thread-owned.

## Manual Windows checks

Verify the interface at 1280 × 720, 1366 × 768, 1600 × 900, 1920 × 1080, and
2560 × 1440. Also verify each native Reading mode against installed Windows
applications. Select each Home banner, verify Fixed survives restart, and
verify Rotate on startup remains stable for the duration of each launch.

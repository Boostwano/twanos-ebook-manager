# Architecture Decisions

## ADR-001 — Safe by design
Potentially destructive library operations must use previews, confirmations, backups and Undo.

## ADR-002 — Protection modes
Twano uses two user-selectable modes: Standard and Read-Only. The mode can be changed without restarting.

## ADR-003 — Dynamic Welcome Panel
The Home greeting is selected once at application startup. It does not change while the application remains open.

## ADR-004 — Hero Banner framework
The Grand Library is the default banner. Banner choice and rotation preference are persisted separately from the dashboard.

## ADR-005 — No name-based greetings
The application never uses the person's name in Home greetings.

## ADR-006 — Neutral seasonal messaging
Default seasonal content is neutral and library-focused. Religious holiday messages are not enabled by default.

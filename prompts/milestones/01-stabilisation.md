# Milestone 1: Stabilisation

**Status: Completed**

## Goal

Stabilise the scan lifecycle and ensure the real dashboard and Library remain responsive around background scans.

## Historical Record

- Removed the duplicate `DashboardPage` and wired the real dashboard page.
- Corrected `ScanWorker` and `QThread` shutdown and cleanup.
- Restored controls after success, cancellation, and failure.
- Supported repeated scans without restarting the application.
- Investigated and resolved the Library navigation hang after scanning.
- Kept SQLite connections local to the thread performing the work.
- Prevented duplicate Library refreshes.
- Improved Library query and table-rendering performance.
- Added timing logs for Library queries and rendering.
- Added regression testing for scan completion, cancellation, failure, repeated scans, database visibility, and Library behaviour.

## Completion Evidence

The current repository contains lifecycle regression tests, non-blocking cancellation, thread-finished cleanup, service-owned database orchestration, guarded Library refreshes, and efficient table population.

## Related

- [Library navigation hang](../bugfixes/library-navigation-hang.md)
- [Architecture](../../docs/architecture.md)

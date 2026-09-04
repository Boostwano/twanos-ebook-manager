# Library Navigation Hang After Scanning

**Status: Resolved**

## Background

A scan completed successfully, but navigating to Library caused the application to hang.

## Reproduction Steps

1. Start the application.
2. Scan a library and wait for successful completion.
3. Navigate to Library.

## Observed Behaviour

The application became unresponsive while opening or refreshing Library.

## Expected Behaviour

Library opens after scanning and displays committed results without blocking the GUI thread.

## Investigation and Resolution

- Reviewed worker completion and `QThread` shutdown ordering.
- Checked SQLite connection creation, use, commit, and close ownership by thread.
- Prevented duplicate refresh calls through one activation refresh and a re-entry guard.
- Made table population efficient by suppressing sorting, signals, and updates during the batch.
- Added timing logs for Library queries and rendering.
- Ensured scan database work commits before completion is signalled.
- Removed GUI-thread blocking waits from the scan lifecycle.

## Acceptance Record

The current implementation confirms that Library opens after scanning, reads committed results, and supports later scans. Regression coverage is in `tests/test_scan_lifecycle.py`, `tests/test_library_page.py`, and `tests/test_database.py`.

## Manual Verification

Complete a scan, open Library, exercise its filters, run a second scan, and open Library again.

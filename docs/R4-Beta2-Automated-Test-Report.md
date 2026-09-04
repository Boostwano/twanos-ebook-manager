# Twano R4 Beta 2 Automated Test Report

**Date:** 30 July 2026  
**Environment:** Windows, Python 3.14.6, PySide6 6.11.1, pytest 9.1.1

## Source validation

Command:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests tools
```

Result: **Passed**

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Result:

- **245 passed**
- **0 failed**
- **0 skipped**
- elapsed time: 22.02 seconds

Coverage includes banners, responsive UI, library actions, metadata providers,
persistent lookup cache, protected metadata Apply, native Hardcover and Comic
Vine response mapping, Windows-protected API-key storage, plugin setup/state
transitions, the unified metadata-and-cover lookup, filename-derived searches,
automatic cover-preview caching, matching a cover to the selected metadata
result, querying every active cover provider, reusing discovered ISBNs across
providers, legacy metadata-cache invalidation, ISBN-10 to ISBN-13 conversion,
Google Books fallback queries and optional protected API keys, filtering
unrelated low-confidence covers, the visible **Find Metadata & Covers** label,
Google Books and Open Library description mapping and plain-text cleanup,
unreadable Windows credential detection, protected credential round-trip
verification, and readable Google Books key/restriction failures,
the Plugins version/API-key status columns without credential disclosure and
selection-preserving A–Z/Z–A plugin sorting, persisted Comic Vine and
Hardcover API response health, current Google Images result parsing and stale
provider-warning reset, targeted single-provider metadata/cover
searches, general CBR/CBZ publisher-series-issue filename parsing, exact
Comic Vine issue retrieval, the clickable screen-bounded large-cover viewer,
and the renamed **Metadata & Covers** navigation item,
consistent two-pixel pressed feedback across shared and dashboard button
styles, compact cover layout,
scan preview/apply and
cancellation, multi-folder selection, combined preview of all enabled watched
folders, sequential protected Apply All, confirmed source-specific catalogue
removal, network-source
safeguards, exact duplicate quarantine/restore,
deterministic health with bounded affected-item previews on every issue card,
approved plugin refusal, Calibre inspection, backups,
restore, retention, audit, Undo, and thread lifecycle.

The filename search fallback was also exercised against 1,268 sample eBooks:
1,265 supplied embedded metadata, three required filename-only extraction,
680 searches used an ISBN, 588 used title/author terms, and none produced an
empty search. `Wizard Squared - K. E. Mills.epub` correctly produced the
search terms `Wizard Squared` and `K. E. Mills`.

## Native Windows visual smoke

Seven pages were captured through the native Windows Qt platform at 1180 × 760
and Metadata was also captured at 900 × 600:

- Home
- Library
- Metadata & Cover Art
- Library Health
- Plugins & Integrations
- Duplicate Review
- Metadata & Cover Art compact view

Result: **Passed visual inspection**. The right-side actions remain visible,
forms resize, metadata details and covers share one result page, the cover
preview doubles at 1600 × 900 while remaining unclipped at 900 × 600, the main
pages do not require outer page scrolling, and the simplified
navigation/footer match the Beta design.

## Clean archive validation

The final archive is validated after creation by
`tools/validate_release_zip.py`. It recompiles and reruns the complete suite
from a new temporary extraction and requires seven UI smoke captures.

Result:

- **Passed from a clean temporary extraction**
- 207 release entries
- Python compilation passed
- **245 passed, 0 failed, 0 skipped** in the extracted test suite
- extracted test elapsed time: 22.52 seconds
- 7 UI smoke captures produced
- version verified as `R4 Beta 2`
- release name verified as `Reliability and Performance Test Package`

## Manual acceptance

The user completed the guided Beta 2 schedule and accepted the final pending
Plugins Version/provider check on 30 July 2026. The guide records **142 passed,
0 failed, 0 pending, and 0 skipped**.

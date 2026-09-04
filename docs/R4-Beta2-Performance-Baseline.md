# Twano R4 Beta 2 Performance Baseline

**Date:** 30 July 2026  
**Environment:** Windows, Python 3.14.6  
**Tool:** `tools/validate_rc6_6_scan.py`

These are observations from one development computer, not guarantees for every
disk, NAS, ebook collection or Windows configuration. The synthetic files are
small, so real embedded-metadata extraction may take longer.

## Accepted Beta 1 baseline

| Books | First Preview | First protected Apply | Unchanged Preview | Changed Preview | Changed Apply |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 413 ms | 244 ms | 724 ms | 745 ms | 262 ms |
| 5,000 | 1,942 ms | 931 ms | 3,469 ms | 3,431 ms | 985 ms |
| 10,000 | 4,145 ms | 1,746 ms | 7,061 ms | 7,567 ms | 2,531 ms |

## Beta 2 path-resolution optimisation

The scan comparison previously resolved each supported Windows path more than
once and resolved existing catalogue paths again while classifying missing
items. Beta 2 resolves each discovered or existing path once and reuses the
normalised result. Unsupported files are rejected before path resolution.

No file, catalogue, metadata, backup, integrity, cancellation or final Apply
safety check was removed.

| Books | First Preview | First protected Apply | Unchanged Preview | Changed Preview | Changed Apply |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 237 ms | 222 ms | 433 ms | 431 ms | 238 ms |
| 5,000 | 1,431 ms | 918 ms | 1,883 ms | 1,906 ms | 952 ms |
| 10,000 | 2,410 ms | 1,748 ms | 3,852 ms | 3,832 ms | 1,897 ms |

## Largest measured improvements

- 10,000-book unchanged Preview: **7.06 s → 3.85 s** (45% faster).
- 10,000-book changed Preview: **7.57 s → 3.83 s** (49% faster).
- 10,000-book first Preview: **4.14 s → 2.41 s** (42% faster).
- 10,000-book changed protected Apply: **2.53 s → 1.90 s** (25% faster).

Protected Apply remains dominated by required metadata/file rechecks and the
verified catalogue backup. Beta 2 now changes the progress bar from completed
file counts to a live 0–100% verified-backup phase, including the SQLite
integrity and checksum stages, so the application no longer appears stuck
after all books have been processed.

## Commands

```powershell
.\.venv\Scripts\python.exe tools\validate_rc6_6_scan.py --book-count 1000
.\.venv\Scripts\python.exe tools\validate_rc6_6_scan.py --book-count 5000
.\.venv\Scripts\python.exe tools\validate_rc6_6_scan.py --book-count 10000
```

Each run verifies:

- first Preview and protected Apply;
- unchanged and changed Preview;
- changed Apply with final vanished/reappeared-file checks;
- cancellation without false missing results;
- unavailable source protection;
- final active/total counts and scan history.

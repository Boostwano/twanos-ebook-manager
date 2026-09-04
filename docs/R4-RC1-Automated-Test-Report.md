# Twano R4 RC1 Automated Test Report

**Date:** 1 August 2026  
**Environment:** Windows, Python 3.14.6, PySide6 6.11.1, pytest 9.1.1

## Source validation

Commands:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests tools
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe tools\check_github_readiness.py
```

Results:

- compilation passed;
- **273 passed, 0 failed, 0 skipped** in 27.57 seconds;
- GitHub publication audit passed;
- the Windows build PowerShell script passed parser validation.

The current source suite includes provider regression coverage for structured
Open Library, Google Books, Hardcover and Amazon series metadata, the exact
`Inca Gold (Dirk Pitt Adventures Book 12)` title pattern, cache migration and
provider-conflict review guidance.
The provider suite also proves that independent online metadata providers begin
concurrently, while Metadata UI coverage confirms that cover previews return
control after the selected image is checked instead of downloading every
possible cover before the user can continue.
It also covers the current Amazon result-card markup, discards unrelated Apple
Books search results, verifies compact Metadata controls remain aligned and
inside their panel, and keeps the maximised review fields immediately beneath
the possible-match selector. The responsive sidebar remains visible with the
warm book mark and centred **Twano's / eBook Manager** identity.
It also covers the cancellable multi-book metadata preparation worker,
attention-only queue selection, manual prepared-result handoff, persisted
automatic-next preference, and the rule that Apply remains disabled until a
fresh per-book preview is reviewed.
Metadata-result UI coverage also verifies that a usable title and author
automatically select protected file organisation, series matches target
Author/Series, and standalone matches clear stale series fields before
targeting the Author folder.
The Metadata page now also verifies the complete read-only original file path,
clean Manual Review button text, and conservative recovery of a missing series
order from an explicit leading filename prefix such as `01 -`.
Series lookup coverage also verifies that explicit embedded metadata shaped
like `Series Name 1 - Book Title` searches using the clean book title and
fills a provider's otherwise blank series and reading-order fields.
Duplicate Review coverage verifies two consecutive exact-copy quarantines:
the refreshed table rebinds its selection to the next group and never leaves
an action attached to the already moved file.
EPUB duplicate coverage also confirms that copies whose readable ZIP entries
match exactly, but where one contains only Apple's `iTunesMetadata.plist`, are
treated as confirmed content copies and enable recoverable quarantine.

## Autonomous Windows acceptance cycle

The cycle used an isolated `%LOCALAPPDATA%` equivalent and eight copied EPUBs
under `.test-runtime`; no original ebook or normal Twano catalogue was changed.

- the first isolated scan catalogued all eight copied books;
- the repeat scan reported **0 applicable changes**, **8 unchanged items** and
  no duplicate catalogue rows;
- one exact-copy duplicate group was detected;
- the watched source reported **Available**;
- the real `launcher.bat` started Twano against a separate fresh profile and
  left no application process running after the check;
- all 14 internal routes rendered at **900 x 600** and **1600 x 900** with no
  visible action button outside the window;
- the splash rendered at **630 x 358**;
- the compact Metadata page keeps Title, Author, Series and Series number
  visible, retains a readable cover preview and keeps every action inside its
  panel; secondary fields return automatically at larger sizes.

## Live provider acceptance

Live checks used fixed public test titles and did not transmit local filenames
or library content.

- Open Library returned correct Inca Gold metadata, description and a cover;
- one Amazon run returned **Inca Gold**, **Clive Cussler**, series
  **Dirk Pitt Adventures**, number **12**, and a cover using the repaired
  current-layout parser;
- later Amazon calls received a non-book/block response, which Twano correctly
  reported as **Provider Update Needed** rather than accepting unsafe data;
- cover-only lookup for Thieves of Blood returned only candidates with covers
  from Open Library and Apple Books; an earlier run also returned Amazon;
- Apple Books no longer returned unrelated Wizard Squared matches;
- the isolated Google Books profile had no user key and received a readable
  rate-limit message;
- Google Images currently reports **Provider Update Needed** because its live
  response did not contain recognised image-result data.

Clean extracted-source-package results are recorded after packaging.

## Clean source-candidate validation

- 237 release entries, including the guided `launcher.bat`;
- no nested ZIP files;
- compilation passed from a fresh temporary extraction;
- **269 passed, 0 failed, 0 skipped** in 25.07 seconds;
- seven native Qt UI smoke captures produced;
- application version verified as **R4 RC1**;
- release name verified as **Production Release Candidate**.

## Windows binary validation

**Status: build completed; manual launch acceptance pending.**

- PyInstaller **6.21.0** completed the one-folder Windows build;
- Inno Setup **7.0.2 x64** completed the per-user installer;
- the approved splash and sidebar book assets were found in the packaged
  application;
- packaged-path simulations loaded and rendered both approved assets from
  PyInstaller's `_MEIPASS` directory;
- the splash remains visible for five seconds and uses a 650-millisecond
  opacity animation to fade smoothly into the main window;
- the packaged banner resolver loaded the photographic hero assets from
  PyInstaller's `_MEIPASS` directory instead of using the fallback scene;
- the packaged splash uses the approved compact crop with an opaque, crisp
  four-pixel square cyan frame, no rounded mask, and no outer artwork;
- responsive Home banner renders preserve source proportions at restored and
  maximized widths, with separately anchored title and scene regions joined
  by a matching flexible centre and soft fades;
- PyInstaller and Inno Setup embedded the approved warm book icon, and the
  installer uses **Twano's eBook Manager** for its visible product identity;
- Windows version resources report **R4 RC1**, **Twano's eBook Manager**, and
  **Twano**;
- portable ZIP SHA256:
  `5F7CAC021CBC4D1D5D9FA1DB189A80204DCDFD80001CEBF8A99F64BA7B0E8680`;
- installer SHA256:
  `3FC9D656BE8AA38C4540F36E31672FF020D9FB2807DB6B94809E4E2E2AD3BC70`.

Artifacts:

- `2026-07-31-2311-Twano-R4-RC1-Windows-Portable.zip`;
- `Twano's eBook Manager Setup.exe`.

Both are in
`C:\Twano\Builds\2026-07-31-2311-Twano-R4-RC1-Windows`.
The installer is currently unsigned and must complete the guided manual RC1
acceptance checks before release.

## Current portable testing delivery

Installer builds are paused while application acceptance testing continues.
The current delivery is a timestamped source-based portable ZIP: extract it,
then run `launcher.bat`. It does not include or require a setup executable.
The launcher creates or updates Twano's private `.venv` on first run and starts
the application. Installer, uninstall, shortcut, and signing checks remain
deferred until the final installable release is explicitly requested.

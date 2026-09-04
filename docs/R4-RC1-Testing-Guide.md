# Twano R4 RC1 Testing Guide

Use only the exact timestamped portable ZIP and installer supplied for RC1.
Mark each item `[PASS]`, `[FAIL]`, or `[SKIP]` and attach the exact message and
a screenshot to every failure.

## 1. Artifact identity

- Portable ZIP:
  `2026-07-31-182608-Twanos-eBook-Manager-R4-RC1-Windows-Portable.zip`
- Expected SHA256:
  `BAE9730A897732558DC8172926A3933924AC996E6708054DAC7765083F0FD515`
- Installer: `Twano's eBook Manager Setup.exe`
- Expected SHA256:
  `791C64B7A0B2952732D7BEB10BBF3F1DBCDBF6E2243B1C25F62F503BF0D71822`

- [ ] Verify the SHA256 of the portable ZIP.
- [ ] Verify the SHA256 of the installer.
- [ ] Confirm Windows file properties and About show **R4 RC1**.
- [ ] Confirm the release name is **Production Release Candidate**.
- [ ] Record whether the artifacts are signed or unsigned.

## 2. Clean portable test

- [ PASS] Extract the portable ZIP to a new folder with spaces in its name.
- [PASS ] Start `Twano eBook Manager.exe` without installing Python or pytest.
- [ PASS] Confirm the approved blue Twano splash appears before the main window,
      includes the warm open leather-book logo, remains visible for five
      seconds as a compact window, has an even four-pixel cyan frame with no
      dark outer rim or embedded version number, and fades smoothly into the
      main application.
- [PASS ] Confirm the selected photographic Home hero banner appears instead of
      the abstract painted fallback.
- [PASS ] Confirm the complete banner is visible, including its transparent gold
      title overlay, and the live controls do not cover or duplicate it.
- [PASS ] Select each of the eight banners and confirm its gold title has no
      visible blue rectangle or hard-edged background behind it.
- [PASS ] Resize and maximize the window. Confirm the title remains proportional
      at left, the artwork remains proportional at right, and the flexible
      navy centre and fades have no visible seam or stretching.
- [ PASS] Confirm the sidebar uses the same warm book identity and the title/About
      wording says **Your Library, Beautifully Organised**.
- [ PASS] Confirm Home, Library, Scan, Metadata & Covers, Library Health, Plugins,
      Settings, User Guide, What's New and About open correctly.
- [PASS ] Close and reopen Twano without an error or QThread warning.

## 3. Clean installer test

- [ ] Install for the current Windows account.
- [ ] Confirm Start-menu and optional desktop shortcuts open Twano.
- [ ] Confirm Installed Apps/Control Panel, the installation folder and
      shortcuts display **Twano's eBook Manager**.
- [ ] Confirm the warm open-book icon appears for the application, installer
      and uninstall entry.
- [ ] Confirm the installer does not request administrator access.
- [ ] Confirm the installed program contains no test catalogue or API keys.

## 4. Upgrade from accepted Beta 2

- [PASS ] Back up `%LOCALAPPDATA%\Twano` before testing.
- [ PASS] Record watched folders, book count, settings, provider states and history.
- [ ] Install RC1 over the supported Beta installation.
- [ ] Confirm catalogue, settings, API-key state, covers, backups, history and
      quarantine records remain available.
- [ ] Run a repeat scan and confirm no duplicate catalogue entries appear.

## 5. Core recovery checks

- [PASS ] Create two separate exact-copy groups. Quarantine one copy from the
      first group and confirm the refreshed page selects the second group,
      enables **Quarantine Exact Copy**, and successfully quarantines its
      selected copy without reopening Duplicate Review.
- [ PASS] Compare two EPUB copies where one contains only an additional
      `iTunesMetadata.plist` entry. Confirm Twano labels them **Exact copy**,
      enables recoverable quarantine, and explains that the readable EPUB
      contents match while vendor metadata differs.
- [ PASS] Search `01 - Thieves of Blood - Tim Waggoner.epub` and confirm Twano
      searches for **Thieves of Blood** by **Tim Waggoner**, not title `01`.
- [PASS] Search **Inca Gold** by **Clive Cussler**. Confirm an Amazon result named
      `Inca Gold (Dirk Pitt Adventures Book 12)` is presented as title
      **Inca Gold**, series **Dirk Pitt Adventures**, series number **12**. The
      parser and a successful live result passed; Amazon may still temporarily
      block later requests and Twano must explain that provider failure.
- [PASS] Confirm a provider result labelled `Dirk Pitt Series Volume 12` fills
      the series and series-number fields rather than leaving them blank. The
      deterministic provider regression passed; the live Open Library record
      tested on 1 August did not itself publish a series value.
- [PASS] Select a correct metadata result without a cover, choose **Find Covers
      Only**, and confirm cover options are added without changing the
      reviewed metadata fields. The live check returned cover-bearing choices
      from Open Library and Apple Books; an earlier run also returned Amazon.
- [ ] Apply one copied-book metadata change and confirm backup/Undo evidence.
- [PASS ] Confirm the read-only **Original file** row shows the selected ebook's
      complete current folder, filename, and extension.
- [PASS ] Test `01 - Thieves of Blood - Tim Waggoner.epub` with a result that
      identifies the series but omits its order. Confirm Twano fills series
      number **1**, Preview succeeds, and Apply moves it only after approval.
- [PASS] Search `1st to Die - James Patterson.epub`. Confirm the embedded
      `Womans Murder Club 1 - 1st To Die` value is searched as title
      **1st To Die** and the reviewed result shows series
      **Womans Murder Club**, number **1** when the provider omits them.
- [ PASS] Force or reproduce any Preview/Apply error and confirm a visible dialog
      explains the failure instead of the button appearing to do nothing.
- [ ] Confirm an expired metadata preview displays **Preview Refreshed**,
      creates a new exact preview, and requires review before Apply rather
      than appearing to do nothing or applying the old plan.
- [ ] Tick **Automatically search the next book after Apply**, safely apply a
      copied-book change, and confirm the next attention book is selected and
      searched without changing it automatically.
- [ ] Confirm a completed book is absent from the normal Metadata & Covers
      opening queue, then choose **Recheck All Books**. Verify the confirmation
      states the exact number of catalogue books and the completed book is
      included in the prepared results.
- [ ] While rechecking is running, choose **Cancel Recheck** and
      confirm it stops safely after the current book while retaining completed
      results.
- [ ] Run the full scan again and confirm its clickable list includes ready,
      no-match, and failed books. Click several rows and confirm the correct
      metadata and cover candidates appear below.
- [ ] Choose **Reject Result** and confirm the row becomes rejected, Twano moves
      to the next unreviewed row, and no catalogue or ebook change occurs.
- [ ] Choose **Accept Selection** for a correct candidate and confirm it creates
      the protected Preview but does not Apply automatically.
- [ ] Select a result supported by the filename and more than one provider.
      Confirm the green **Evidence** line names the independent sources.
- [ ] Select or reproduce a low-confidence/conflicting result. Confirm an amber
      **Manual review recommended** evidence line appears and no change is
      accepted automatically.
- [ ] Copy `Hounded.epub`, review title **Hounded**, author **Kevin Hearne**,
      series **Iron Druid Chronicles**, and series number **1**. Confirm
      **Organise file into Author / shared -=Series=- folders when applying** is selected
      automatically when the result is chosen.
- [ ] Preview and confirm the exact destination ends in
      `Series\Iron Druid Chronicles\01 - Hounded - Kevin Hearne.epub`.
- [ ] Apply and confirm the original file moved to that destination, the ebook
      still opens, and Library details show the new path.
- [ ] Repeat with series number **2**. Filter Library to the series, choose
      **Series & sequence** ascending, and confirm 01 appears before 02.
- [ ] Choose a standalone result with a title and author. Confirm organisation
      is selected automatically, its Series fields are empty, and Apply names
      it `Title - Author.epub` directly in the author folder.
- [ ] Create a file at a proposed destination and confirm Preview refuses the
      collision without changing or overwriting either file.
- [ ] Confirm selecting a new book turns the organisation option off until a
      usable metadata result is chosen.
- [ ] Close and reopen Twano, then perform Undo.
- [ ] Create and verify a catalogue backup.
- [ ] Restore that backup and confirm the catalogue reopens correctly.
- [ ] Disconnect and reconnect a mapped or UNC source if available.

## 6. Paths and Windows integration

- [ ] Test a watched-folder path containing spaces.
- [ ] Test a copied ebook with non-ASCII characters in its path and filename.
- [ ] Test Open Book with the chosen Windows reader.
- [ ] Test Open Folder from the Library.
- [ ] Confirm Windows security software does not quarantine Twano.

## 7. Portable test package

- [ ] Extract the timestamped portable ZIP into a new folder.
- [ ] Run `launcher.bat`; confirm it performs any required local setup and
      opens Twano without a separate setup executable.
- [ ] Confirm `%LOCALAPPDATA%\Twano` and every ebook file remain untouched
      when the extracted test folder is removed.
- [ ] Defer installer, uninstall, shortcut, and installed-name testing until
      the application is approved for its final installable release.

## Acceptance

RC1 can progress only when there is no release-blocking defect, the exact
portable hash is recorded, the clean portable launch passes, and all ebook and
catalogue data remain safe. Installer, upgrade, uninstall, and signing checks
are final-release gates and are intentionally deferred during portable
testing.

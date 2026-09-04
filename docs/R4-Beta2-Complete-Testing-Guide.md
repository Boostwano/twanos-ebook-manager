# Twano R4 Beta 2 Complete Testing Guide

This is the guided acceptance test for the complete Beta 2 package. Work from
top to bottom. A typical pass takes 60–90 minutes, plus scan time.

## Safety before testing

**Use copies of ebooks for duplicate quarantine and recovery tests. Do not use
the only copy of an important book.**

Stop testing and report the issue immediately if:

- Twano changes an ebook during Safe Preview;
- a metadata change occurs before Preview and Apply;
- an offline library is treated as deleted;
- a quarantined file cannot be restored;
- Restore damages both the catalogue and its recovery copy;
- the application crashes repeatedly at startup.

## Test result key

Mark each item:

- `[PASS]` worked as described
- `[FAIL]` did not work
- `[SKIP]` not available on this computer

Attach a screenshot and the exact message to every failure.

## 1. Fresh start and layout — important

- [PASS ] Extract the ZIP to a new folder.
- [ PASS] Run `launcher.bat`. On a clean extraction, confirm it reports successful
      setup and then starts Twano without requiring a second batch file.
- [ PASS] Confirm Twano opens with **0 books** and does not display the previous
      development catalogue.
- [ PASS] Confirm the old catalogue under
      `%USERPROFILE%\.twanos_ebook_manager` still exists if you had one.
- [ PASS] Check Home, Library, Scan, Metadata, Library Health, Plugins, Settings,
      User Guide, What's New, and About are the visible navigation choices.
- [PASS ] Confirm the bottom bar shows library, book count, `R4 Beta 2`, update
      button, and green ready dot.
- [ PASS] Test maximised and restored window sizes, including about 900 × 600.
- [ PASS] Confirm pages fit the window, fields resize, and no important right-side
      action is clipped. Internal tables may scroll; the whole page should not.
- [ PASS] Confirm the Home hero and three centre cards resemble the accepted design.
- [ PASS] Press buttons on Home and the bottom update bar. Confirm each enabled
      button visibly depresses and releases without moving the surrounding
      layout.

## 2. Scan and protected Apply — **critical**

Create two small test folders with at least two supported ebooks in total.

- [PASS ] In Scan > Sources, choose **Add Folders**, add both folders to the
      selection list, and save them together.
- [ PASS] Test the connection.
- [PASS ] Choose **Preview All Watched Folders** without highlighting each source.
- [PASS ] Confirm the combined Preview identifies which watched folder contains
      each proposed change.
- [PASS ] Confirm the Library count is unchanged before Apply.
- [ PASS] Review new, changed, missing, unreadable, and skipped counts.
- [ PASS] Apply all previews in Standard mode with the single confirmation.
- [ PASS] Confirm each watched folder receives a verified backup and Undo history
      entry before its catalogue changes.
- [ PASS] Confirm the new books appear once, with no duplicates after a repeat scan.
- [PASS ] Temporarily rename one expendable test file, preview again, and confirm it
      is clearly listed as missing before Apply.
- [PASS ] Put the file back and confirm a later scan recognises its return.
- [PASS ] Cancel a preview once and confirm no catalogue changes occur.
- [PASS ] Using an expendable test source, choose Remove Watch. Confirm the prompt
      states the exact associated book count, that ebook files will not be
      changed, and that no other source is affected.
- [ PASS] Choose No once and confirm nothing changes.
- [PASS ] Confirm removal once. Verify that source's books disappear from the Twano
      Library while the actual folder and ebook files remain on disk.
- [PASS ] If another source is configured, confirm all of its books remain.

## 3. Library actions and responsive behaviour

- [ PASS] Search by title and author.
- [ PASS] Change between grid and list.
- [ PASS] Try format, author, series, collection, location, and metadata filters.
- [PASS ] Change sort order and cover density.
- [PASS ] Select a book and confirm each action has its own visual colour.
- [PASS ] Open Book and confirm the actual book opens in your reader.
- [PASS ] Open Folder and confirm the containing folder opens.
- [PASS ] View Metadata and confirm the selected book is already selected.
- [ PASS] Review Issues and Manage Collections.
- [ PASS] Press actions on Library and Scan and confirm the same visible
      depress-and-release feedback.
- [ PASS] Repeat these checks in a restored, non-maximised window.

## 4. Metadata and cover art — **critical**

Use one test book with incomplete metadata.

- [ PASS] On Plugins, install and enable **Open Library Metadata & Covers** and
      **Google Books Metadata & Covers**.
- [ PASS] Confirm the Plugins **API Key** column shows **None Required** for Open
      Library, **Not Added** before a Google key is saved, and **API Key
      Added** immediately after it is saved. Confirm no key text is displayed.
- [ PASS] In Settings > Metadata & Privacy, confirm Open Library is enabled.
- [PASS ] Confirm the left navigation calls the page **Metadata & Covers**.
- [ PASS] Select a comic, choose **Comic Vine Metadata & Covers only** under
      **Search provider**, and run **Find Metadata & Covers**. Confirm the
      bottom status lists Comic Vine as the only searched provider.
- [ PASS] Test `(Frew) Phantom 1048.cbr`. Confirm the result is for **The Phantom
      #1048**, not a generic Phantom volume, and that **Series** is The Phantom
      and **Series no.** is 1048.
- [ PASS] Repeat with a different publisher and series named as
      `(Publisher) Series 001.cbr` or `[Publisher] Series 001.cbz`. Confirm
      Twano uses that series, publisher and exact issue number without
      renaming the file.
- [ PASS] Select the book in Metadata & Covers and choose
      **Find Metadata & Covers**.
- [ PASS] Use a file named `Wizard Squared - K. E. Mills.epub` whose embedded
      title is `03 Wizard Squared`. Confirm lookup finds `Wizard Squared` and
      shows `K. E. Mills` without renaming or changing the ebook file.
- [ PASS] Confirm candidates show a confidence and understandable match reasons.
- [ PASS] Choose a Google Books or Open Library result that has a synopsis. Confirm
      **Description** is populated, readable (not raw HTML), selectable, and is
      not written until the protected Preview and Apply steps.
- [ PASS] Confirm the same search also fills **Found covers** without opening a
      browser, starting Calibre, or requiring a second search.
- [ PASS] Confirm the bottom status lists every active cover provider that was
      searched and identifies which providers returned covers.
- [ PASS] Repeat a previously cached Wizard Squared search and confirm the current
      lookup refreshes old cache data and converts ISBN `1841497290` to
      `9781841497297` before later providers are searched.
- [ PASS] With Open Library, Google Books, Apple Books, ISBNdb, Hardcover, and
      Comic Vine all active, confirm all six appear after **Searched:**. A
      provider may legitimately return no matching cover, but it must still be
      listed as searched.
- [PASS ] Wait for cover verification to finish. Confirm **Found covers** contains
      only images that can be previewed; broken provider images are removed
      automatically.
- [ PASS] Confirm an unrelated low-confidence Comic Vine result is not offered as
      the cover for an ordinary book.
- [ PASS] Confirm the first found cover appears as a readable image automatically.
- [ PASS] Maximize the application and confirm the cover preview grows to the
      large 2× size. Restore the window and confirm the page still fits
      without scrolling or clipping the cover controls.
- [ PASS] Click a loaded cover preview and confirm it opens in a separate, larger
      viewer that fits the screen. Close it and confirm the selected metadata
      and cover are unchanged.
- [ PASS] Focus the cover preview with the keyboard and press Enter or Space.
      Confirm the same large viewer opens.
- [PASS ] Choose another found cover and confirm its image replaces the preview.
- [ PASS] Select **Use Cover** and confirm the displayed image is selected
      for the change plan.
- [PASS ] Confirm there is no separate Cover Art tab, cover-search source menu, or
      website-search button.
- [PASS ] Choose only two or three fields and, if available, a cover.
- [PASS ] Preview changes and confirm no field changes before Apply.
- [ PASS] Confirm the plan names every old and new value.
- [PASS ] Apply and confirm a verified catalogue backup is recorded.
- [ PASS] Return to Library and confirm only the selected fields changed.
- [PASS ] Repeat using a local cover image.
- [PASS ] Disable Open Library in Settings and confirm Open Library is skipped
      while other active metadata and cover providers remain usable.
- [ PASS] Press buttons on Metadata, Plugins, and Settings and confirm each enabled
      button visibly depresses before its action runs.
- [ PASS] Search for an obscure or misspelled book and confirm “no result” remains
      usable rather than crashing.

### 4A. Optional API-key providers

If you do not want to create provider accounts, mark these items `[SKIP]`.

- [ PASS] Select **Google Books Metadata & Covers** and confirm it can remain
      Active without an API key.
- [PASS ] Confirm **Configure API Key** is available for Google Books and explains
      that its key is optional.
- [ PASS] Add a Books API key, repeat the Wizard Squared search, and confirm Google
      Books no longer appears after **Unavailable:**.
- [PASS ] Remove the optional Google key and confirm Google Books remains Active.
- [ PASS] Install and enable **Apple Books Metadata & Covers**. Confirm the API
      Key column says **None Required** and Apple joins the normal search.
- [PASS ] Install **ISBNdb Metadata & Covers**. Confirm it remains **Setup
      required** until a user-owned ISBNdb key is saved.
- [PASS ] Add an ISBNdb trial or subscription key, enable it, and confirm an exact
      ISBN search can contribute a description, publication details and cover.
- [PASS ] Install **Hardcover Metadata & Covers**. Confirm its status becomes
      **Setup required**, Configure API Key is enabled, and Enable is disabled.
- [PASS ] Open **Configure API Key**. Confirm the field is masked and the guide link
      opens `https://hardcover.app/account/api`.
- [PASS ] Paste your Hardcover token, save it, then enable the plugin. Confirm its
      status becomes **Active**.
- [PASS ] Run **Find Metadata & Covers**. Confirm the Hardcover provider name,
      match reason, and any available cover appear in the same results.
- [ PASS] Reopen Configure API Key and confirm the saved token is never displayed.
- [ PASS] Install **Comic Vine Metadata & Covers** and confirm the setup window
      clearly states its personal/non-commercial requirement.
- [PASS ] Add your Comic Vine API key, enable the plugin, and test a known comic or
      graphic novel.
- [ PASS] Return to Plugins after the search and confirm Comic Vine's **Provider
      Check** changes from **Not Checked Yet** to **Working**, or shows a clear
      key/service failure.
- [ PASS] Choose **Remove Saved Key** for either provider. Confirm the key is
      removed and the plugin is disabled.

## 5. Duplicate quarantine and restore — **critical**

Copy one expendable ebook twice so the files are byte-for-byte identical.

- [PASS ] Scan and apply both copies.
- [PASS ] Open Library Health and follow the duplicate card.
- [PASS ] Confirm the group says **Exact copy** and explains the evidence.
- [PASS ] Confirm similar title/ISBN groups are labelled **Possible editions** and
      cannot use exact-copy quarantine.
- [PASS ] Quarantine one of the two exact copies.
- [ PASS] Confirm one usable copy remains in the original folder.
- [PASS ] Confirm the quarantined item appears on the Quarantine tab.
- [PASS ] Restore it and confirm it returns to its exact original path.
- [PASS ] Mark a non-destructive test group as intentional and confirm it hides
      from the default duplicate list.

## 6. Library Health

- [ PASS] Confirm the score is stable when Refresh is clicked without changes.
- [ PASS] Check cards for metadata, covers, missing files, sources, and duplicates.
- [PASS ] Select every visible card and confirm it opens a relevant filtered page.
- [PASS ] Confirm warnings include an action and do not require technical knowledge.

## 7. Protection, backup, Restore, and Undo — **critical**

- [PASS ] Select the safety card at the bottom of the left navigation.
- [PASS ] Create and verify two catalogue backups.
- [PASS ] Close and reopen Twano; confirm backups and operation history remain.
- [ PASS] Preview a reversible empty-collection test operation, approve, and Apply.
- [PASS ] Confirm Undo is offered and works after restarting Twano.
- [ PASS] Select a verified backup and read the Restore warning.
- [PASS ] Restore it and confirm Twano first creates a recovery backup.
- [PASS ] Confirm Library, Home, Health, and footer counts refresh afterward.
- [PASS ] Set backup retention to `0` and confirm it means Keep All.
- [ PASS] Review old backups and confirm unrelated or unverified files are excluded.

## 8. Calibre and network sources

- [ PASS] Open Plugins > Calibre & Network Libraries.
- [ PASS] Detect Calibre and confirm its path/version if installed.
- [ PASS] Select a copied Calibre library containing `metadata.db`.
- [ PASS] Inspect/open it and confirm Calibre opens that library.
- [PASS ] Add it as a Twano scan source; confirm no automatic import occurs before
      Safe Preview and Apply.
- [PASS ] Add a mapped drive or UNC path if available.
- [PASS ] Test it while online.
- [PASS ] Disconnect it temporarily and confirm Twano reports **Unavailable** rather
      than marking the whole source missing/deleted.
- [PASS ] Reconnect and confirm a retry works.

Mark Calibre or network-only items `[SKIP]` if you do not have that setup.

## 9. Approved plugins and provider safety

- [ PASS] Retest the fixed list and confirm it shows publisher, source, version,
      status, and capability.
- [ PASS] Change **Sort plugins** between **Name A–Z** and **Name Z–A**. Confirm
      the rows reverse alphabetically while the selected and checked plugins
      remain selected.
- [PASS ] Select an Available Open Library plugin. Confirm only Install is active.
- [PASS ] Install it. Confirm its status becomes Disabled, the same row remains
      selected, and Enable becomes active.
- [PASS ] Enable it. Confirm its status becomes Active and only Disable is active.
- [ PASS] Disable and re-enable it; confirm every status and message remains visible.
- [PASS ] Try selecting an arbitrary renamed ZIP as a `.twano-plugin`.
- [ PASS] Confirm Twano refuses it because it is not in the approved-source
      catalogue.
- [PASS ] Confirm no plugin is allowed a file-modification capability.
- [ PASS] Restart after disabling a provider and confirm Twano still opens.

## 10. Settings, accessibility, and guidance

- [ PASS] Change the Home banner and test rotate-on-startup versus fixed selection.
- [PASS ] Change the reader choice and test Open Book.
- [PASS ] Enable and disable check-for-updates on startup.
- [ PASS] Test text scale choices and restart.
- [PASS ] Navigate the main controls using Tab, Shift+Tab, Enter, and Space.
- [PASS ] Confirm the focused control is always visible.
- [PASS ] Confirm important status is explained in text, not by colour alone.
- [PASS ] Review User Guide, What's New, and About for accuracy.
- [ PASS] Confirm About shows user-data and privacy information.

## 11. Update and packaging

- [ PASS] Select the small **Check for Updates** button in the bottom bar.
- [ PASS] Confirm the current build/status message is clear and does not silently
      download or replace the running application.
- [ PASS] Close Twano normally and launch it again with `launcher.bat`.
- [ PASS] Confirm settings, source list, catalogue, history, and quarantine records
      persist.
- [PASS ] Move a fresh copy of the source ZIP to another folder and repeat the
      setup/launch smoke test.

## Defect report template

```text
Test section:
Result: FAIL
What I clicked:
What I expected:
What happened:
Exact message:
Window size: Maximised / Restored (size if known)
Library type: Local / Calibre / Mapped / UNC
Can it be repeated: Always / Sometimes / Once
Screenshot:
```

## Acceptance summary

**Accepted by the user on 30 July 2026.** All 142 guided checks passed with
no failures, pending items, or skips. The accepted candidate is
`2026-07-30-2332-Twano-R4-Beta2-Outstanding-Errors-Fixed-Test-Package.zip`.

Beta 2 is ready to progress only when:

- every **critical** item passes;
- there is no known data-loss or startup defect;
- skipped Calibre/network checks are recorded;
- layout remains usable at maximised and restored sizes;
- any remaining issue has clear reproduction steps.

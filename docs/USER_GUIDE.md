# Twano R4 RC1 User Guide

Twano helps you scan, browse, repair, and protect an ebook collection without
requiring technical knowledge. It does not include an ebook reader; **Open
Book** uses your normal Windows reader or Calibre's ebook viewer.

## Start Twano

1. Double-click `launcher.bat`.
2. On the first run, it creates Twano's private environment, installs the
   required packages, reports that setup completed, and starts Twano.
3. The compact, light-blue-framed Twano splash remains visible for five
   seconds while the main window is prepared, then fades smoothly into the
   application.
   closes automatically when the application is ready.
4. Twano starts with an empty catalogue. Your ebook files are not moved or
   changed when Twano scans them.

The lower bar shows the current library name, number of books, version, and a
small update-check button.

## Home

Home is the simple starting point:

- **Find a Book** searches the catalogue.
- **Scan Library** opens the Scan page.
- **Open Library Folder** opens the selected library location.
- **Last Scan Summary** shows the most recent scan.
- **Recent Activity** shows recent protected work.
- **Quick Links** provide shortcuts without adding more navigation items.

The eight banners can be selected or rotated at startup in
**Settings > Home**. Each uses a continuous title-free scene background with
its matching gold title placed above it as a transparent layer.

## Add and scan a library

1. Open **Scan**.
2. On **Sources**, choose **Add Folders**. Add one or several local folders,
   mapped drives, or network shares to the list, then save them together.
3. Choose **Test Connection** for a selected network source when needed.
4. Choose **Preview All Watched Folders** to scan every enabled source without
   highlighting them individually. Disabled sources are left out.
5. Review the combined proposed new, changed, missing, unreadable, and skipped
   items. Each row identifies its watched source.
6. Choose **Apply All Previews** only when the combined summary is correct.

Preview does not change the catalogue. Apply All safely processes the watched
folders one at a time; every source is rechecked and receives its own verified
catalogue backup and Undo history entry. It never edits ebook files. You can
still select one source and use **Preview Scan** when you only want that folder.

If a NAS or mapped drive is offline, Twano reports the source as unavailable
instead of assuming every book was deleted.

**Remove Watch** first shows how many associated books will be removed from the
Twano Library. If confirmed, Twano removes that watched source and its catalogue
entries. It does not delete, move, rename, or modify the folder or ebook files,
and it does not affect other library sources. Add and scan the folder again if
you later want those books back in Twano.

## Browse the Library

Library supports grid and list views, search, filters, sorting, and details.
Open **Format** to tick one or several file types, such as EPUB and CBZ. Open
**Website rating** to tick one or several downloaded star-rating bands,
including **No website rating**. Ratings supplied by supported providers such
as Google Books and Apple Books are shown during metadata review and saved by
the same protected Apply action. Twano shows the provider and rating count in
Book Details; these ratings are not entered or edited by the user.

On **Metadata & Cover Art**, enable **Automatically search the next book after
Apply** to continue through the Library without pressing Find for every book.
After a successful protected Apply, Twano selects the next book not already
applied in that automatic session and starts its read-only search. Every result
still requires manual review, Preview, and Apply.
Selecting a book enables these clearly coloured actions:

- **Open Book** opens the file in the configured reader.
- **Open Folder** opens the folder containing that book.
- **View Metadata** opens the selected book in Metadata & Cover Art.
- **Review Issues** opens the review workflow.
- **Manage Collections** changes Twano-only collection membership.

Missing files and missing covers are shown calmly and do not prevent browsing.
The **Open Manual Review Folder** button at the bottom opens the review folder
for the selected watched library. If more than one watched library has one,
Twano asks which folder to open. The folder appears after the first book is
moved there.

## Metadata & Cover Art

After a reviewed Apply has supplied the title, author, description, and cover
and organised the ebook into its correct Author or shared `-=Series=-` folder
and filename, Twano marks that book complete. If the book belongs to a series,
both its series name and series number are required so reading order is
preserved. ISBN is useful when a provider supplies it, but it is optional.
Completed books remain visible in Library but no longer clutter the Metadata &
Cover Art queue. If the ebook file later changes, its completion marker is
cleared automatically so it can be reviewed again.

Metadata and cover lookup are one deliberately manual workflow:

1. Open **Metadata & Covers** and select a book.
2. Leave **Search provider** on **All active providers**, or choose one active
   provider such as **Comic Vine Metadata & Covers only** for a targeted
   lookup.
3. Choose **Find Metadata & Covers**.
4. Twano searches the selected provider, or every active direct provider, for
   book details and covers at the same time. Independent providers run in
   parallel after any Open Library ISBN enrichment, so one slow direct
   provider does not hold up every provider behind it.
   A live elapsed-time message confirms that Twano is still working and that
   no book files are being changed. The completed status lists every
   provider searched and which providers supplied covers. It does not open a
   browser or require a second search. Optional Amazon, Google Images, and
   Edelweiss providers read their public catalogue pages inside Twano and
   require no API key.
   Australian catalogues are preferred where a provider supports regions:
   Amazon checks Australia before its other English marketplaces, Apple Books
   uses the Australian storefront, and Google Books requests Australian
   English and uses Google's location-aware official Books API. Global results
   remain available as fallbacks so uncommon and older editions are not lost.
   If Google Books returns only weak possibilities for an ISBN, Twano
   automatically retries with the clean title and author during the same
   search instead of requiring **Find Covers** and a second lookup.
   If every normal result is 60% or lower, Twano can read a short opening
   excerpt from the local EPUB and use only that bounded text fingerprint for
   one Google Books check. The ebook is not uploaded. A result is offered only
   when its author also matches the book's known author.
   Twano also retries the tightly bounded older-series title variants **The
   Mystery of...** and **The Secret of...** when the first search is weak. This
   is not a general fuzzy-title search. When the complete alternate title is an
   exact match, Twano keeps the book's known pen name if the catalogue instead
   credits the underlying author or series creator.
   Open Library, Google Books and Hardcover structured series values are
   retained. Amazon titles written as `Title (Series Name Book 12)` are split
   into the correct title, series and reading number. When a provider omits
   structured series fields but explicitly states both the order and named
   series in its description, such as `book three in ... series, The
   Chronicles of Narnia`, Twano also offers those values for review. General
   or ambiguous mentions of a series are not used to organise files.
   Some retail collections have a series-like label but no reading order.
   Twano does not automatically move these into `-=Series=-`; confirm a genuine
   series number first so a store category cannot become a misleading folder.
5. If the filename follows `Title - Author.epub`, `Author - Title.epub`, or a
   numbered `01 - Title - Author.epub` pattern, Twano uses the clean title and
   author when embedded details are messy. Lookup alone never renames a file.
6. Select a candidate and review the provider, confidence, and match reason.
   Twano can fill a provider's blank description, ISBN, publisher, language,
   date or series from another strong match for the same title. Every value
   remains reviewable and can be included or excluded.
   The result list shows each provider's series and sequence. If strong
   providers disagree, Twano asks you to choose the result you trust instead
   of silently replacing one provider's series with another.
   The **Description** field grows to show the wrapped summary when the window
   has room. Exceptionally long descriptions scroll inside that field so the
   complete Metadata page remains screen-bounded.
7. Twano displays the first found cover automatically. Choose another item in
   **Found covers** to check and display that image without opening a website.
   Low-confidence results are left out. A missing or broken image is removed
   automatically when Twano checks it, without delaying the whole metadata
   search to download every possible cover first.
   Click the displayed cover, or focus it and press Enter or Space, to open a
   larger cover viewer. The viewer scales the full cached image to the current
   screen and can be closed without changing the selected cover.
8. A successfully displayed online cover is selected automatically. One
   **Preview Selected Changes** and **Apply Reviewed Changes** operation applies
   the checked metadata and that cover together. Choose another **Found
   covers** result to replace it, use **Use Cover** to retry the current result,
   or choose **Cover File** to use an image from your computer.
   If the metadata match has no cover, or its first cover link cannot be
   displayed, Twano automatically follows with the broader cover-provider
   search using the title, author and ISBN currently shown. If that exact
   edition has no image, Twano retries the same active providers with the
   confirmed title and author but without restricting the lookup to that ISBN.
   This does not
   replace the reviewed metadata fields. **Find Covers** remains available
   when you want to repeat that cover search manually after editing a field.
9. Check **Original file** and **New file** directly below the selected book.
   These read-only boxes show the complete current path and the path that
   Apply will use. **New file** updates as you review the title, author,
   series, series number, and organisation option.
10. Tick only the fields and cover you want to change.
    In a compact 900 x 600 window Twano prioritises Title, Author, Series,
    Series number and the cover controls so every action remains reachable
    without scrolling the whole page. Maximise or enlarge the window to review
    ISBN, publisher, language, published date and description together.
11. When a metadata result contains a usable title and author, Twano
    automatically ticks **Organise file into Author / shared -=Series=- folders when
    applying**. A standalone book goes directly into its author folder. A
    series book goes into its shared series folder and requires a reviewed
    series number. If a provider identifies the series but omits its order,
    Twano can use an explicit leading filename number such as `01 -` as the
    reviewed series number. It does not guess from an unnumbered filename.
    Untick the option if you want to update only the catalogue.
12. Select **Preview Selected Changes**. For organisation, the preview shows
    the exact original and destination paths before anything changes.
    A Preview belongs only to the book for which it was created. Selecting a
    different book clears the summary and disables Apply until you create and
    review a new Preview for that book. Twano also verifies this ownership
    immediately before Apply as an additional safety check.
13. Read the plan, then approve and apply it.
    The first Apply confirmation includes **Don't show this confirmation
    again**. Selecting it hides only that final reminder; Preview, verified
    backup creation, protected Apply and Undo remain active. To restore the
    reminder, open **Settings > Metadata & Privacy**, enable **Show
    confirmation before applying reviewed metadata**, and save Settings.
    A preview expires after 30 minutes so an old plan cannot change a library
    that may have changed since it was reviewed. If you apply an expired
    preview, Twano visibly creates a fresh preview from the fields currently
    shown. Review its updated summary, then choose **Apply Reviewed Changes**
    again.
14. For a continuous manual workflow, tick **Automatically search the next
    book after Apply**. After a successful protected Apply, Twano selects the
    next book needing attention and starts its read-only lookup. The result is
    never accepted automatically.
15. To deliberately check the complete catalogue, choose **Recheck All
    Books**. This includes books already marked complete; the normal Metadata
    & Covers opening queue continues to show only unfinished books. Confirm the
    displayed total, then leave Twano to search each catalogue book
    sequentially in the background. To recheck a particular folder instead,
    choose **Scan Folder** and select that folder. Both actions prepare a
    manual review queue only; they never change or move a file automatically.
    The progress bar shows the current book. Choose **Cancel Recheck** to stop
    safely after the current lookup. Completed results remain available for
    the current session and use the normal cache-retention setting.
16. The **Full scan results** list includes every completed book, including
    ready matches, no matches, and failed searches. Click a row to inspect its
    candidates and cover choices. Choose **Reject Result** to leave that book
    unchanged for this session, or **Accept Selection** to create the normal
    protected Preview from the selected candidate and checked fields. Any
    successfully displayed found cover is included with the metadata.
    Apply remains unavailable until the exact Preview has been created and
    reviewed.
17. When a possible match is selected, read the **Evidence** line below it.
    Twano compares the filename, existing embedded/catalogue values, and the
    independent active providers that returned results. A green line records
    supporting sources. An amber **Manual review recommended** line means the
    evidence conflicts or is not strong enough to accept without checking.

### Author folders, series folders and filenames

When organisation is selected, Twano keeps the ebook inside its existing
watched-library root and uses this structure:

```text
Kevin Hearne\
  Oberon's Bathtime Stories - Kevin Hearne.epub
  The Hermit Next Door - Kevin Hearne.epub
-=Series=-\
  Iron Druid Chronicles\
    01 - Hounded - Kevin Hearne.epub
    02 - Hexed - Kevin Hearne.epub
```

Standalone books are placed directly in the author folder. Series books from
every author are placed together under `-=Series=- / Series Name` and receive a
zero-padded sequence prefix so
Windows and Twano's **Series & sequence** Library sort show the reading order.
For a series inside a larger universe, enter **Series group** and optionally
**Group no.**. Twano then uses `-=Series=- / Series Group / Series Name` while
retaining the ordinary series number for the book's position inside its
sub-series. Books without a group keep the simpler path. Verified David Eddings
relationships are recognised automatically: **The Belgariad**, **The
Malloreon**, and **Belgariad Prequels** share **Belgariad Universe**; **The
Elenium** and **The Tamuli** share **Sparhawk Universe**. Other nested
relationships can be reviewed in the same two fields without changing the
immediate series or its reading order.

Some catalogues use overlapping names for one reading sequence. Twano
normalises the verified **Assiti Shards**, **1632 Universe**, **Ring of Fire
Main Line Novels**, and **Ring of Fire series** labels to the single **Ring of
Fire** folder. Known books also receive their broad-series reading number, so
later searches cannot recreate separate folders for those aliases.

Fractional sequence values such as `1.5` are preserved. Twano replaces Windows
filename characters such as `:` or `?` with `-` and does not rewrite the
ebook's internal contents. If an organised filename already belongs to another
catalogued edition with a different ISBN, Twano keeps both and labels the new
edition `[ISBN number]`. That qualified filename remains stable during later
metadata searches. Unknown collisions and books with the same ISBN remain
blocked, so an existing ebook is never overwritten. A verified catalogue
backup is created before Apply. If the catalogue transaction fails after the
move, Twano restores the original file path.

Twano also recognises an explicit embedded title shaped like
`Series Name 1 - Book Title`. It searches providers using only `Book Title`
and retains `Series Name` and order `1` when an otherwise matching provider
omits those fields. For example, `Womans Murder Club 1 - 1st To Die` is
   reviewed as title `1st To Die`, series `Womans Murder Club`, number `1`.

   A separated publication-year prefix such as
   `2006 - The Smelliest Day at the Zoo - Alan Rusbridger.epub` is removed
   from the online search title. A year that is part of the title, such as
   `2066 Election Day`, is retained.

   When one strong provider discovers an ISBN but omits the series, Twano
   checks the exact Open Library edition and can fill its structured series
   value into matching results. If that exact edition confirms a series but
   omits its position, Twano can use an exact-title public Wikipedia article
   only when it explicitly states the book's numbered position in a series.
   Twano does not invent a series number when neither source publishes a
   trustworthy reading order.

### Comic series and issue numbers

For CBR and CBZ files, Twano recognises common numeric issue patterns:

- `(Publisher) Series 001.cbr`
- `[Publisher] Series 001.cbz`
- `Series #001.cbr`

When Comic Vine is selected, Twano separates the publisher, series and issue
number, finds the matching Comic Vine volume, and then requests that exact
issue. Leading zeroes may remain in the filename for correct file sorting;
Comic Vine receives the normalised issue number. For example,
`(Frew) Phantom 1048.cbr` is searched as **The Phantom**, publisher
**Frew Publications**, issue **1048**. The reviewed result can include the
issue title, writer credits, date, description, series, series number and
issue-specific cover. Twano never renames the comic file during lookup. It is
renamed only when organisation is explicitly selected and its Preview applied.
17. After a successful apply, Twano selects the next book in library order
    that still has missing or weak metadata. It skips books with no listed
    metadata issues. If no other book needs attention, the current book stays
    selected and Twano says the review queue is complete.

If a search finds no useful metadata or cover because the selected file is not
a valid book, choose **Move to Manual Review** at the bottom of the page.
Twano first confirms the physical move, then:

- creates `To be manually reviewed` inside that book's watched-library root
- moves the ebook file there without changing its contents
- preserves an existing same-named file by adding `(2)`, `(3)`, and so on
- removes the moved item from the active Twano catalogue
- excludes the manual-review folder from later scans
- selects the next book with metadata issues

The file is not deleted. Use **Open Manual Review Folder** at the bottom of
Library when you want to inspect or relocate it manually.

Twano creates and verifies a catalogue backup before applying metadata. A
provider result is never written automatically. Disable Open Library in
**Settings > Metadata & Privacy** when you do not want searches sent to that
provider; other active plugins remain available.
The combined search is independent of Calibre and works with any ebook reader.

Every enabled button gives visible press feedback when clicked: its contents
move slightly down and right and its background/border darken. A disabled
button remains subdued and does not perform an action.

## Duplicate Books

Open **Library Health**, then choose the duplicate card.

- **Exact copy** means either the complete files have the same SHA256
  fingerprint, or two EPUBs have identical readable archive contents and
  differ only by recognised Apple `iTunesMetadata.plist` catalogue metadata.
- **Possible editions** means identifiers or title/author are similar; the
  files may be legitimate different editions or formats.
- **Keep as Intentional** hides a reviewed group.
- **Quarantine Exact Copy** moves one confirmed exact copy to Twano's
  recoverable quarantine. It does not permanently delete it.
- After quarantine, Twano refreshes the groups and selects the next available
  duplicate automatically so you can continue reviewing without reopening the
  page.
- **Restore** returns a quarantined file to its original location if that path
  is free.

Twano never automatically deletes duplicate files.

## Library Health

Library Health is directly below **Library** in the left navigation so the
collection and its quality checks stay together.

Library Health provides a transparent score and actionable cards for:

- missing titles or authors, metadata reviews not yet completed, and books
  changed after an earlier completed review
- missing covers
- missing files
- unavailable or stale sources
- probable duplicate groups

Each card shows up to four affected books or locations followed by the number
of additional results. This keeps the page readable while still explaining
what its count represents. Select the action at the bottom of a card to open
the full page where every result can be reviewed. The score is a guide, not a
judgement about your collection.

## Plugins, Calibre, and network libraries

### Automatic provider location checks

At startup, Twano immediately applies the last validated provider-location
manifest and checks the trusted `Boostwano/twano-updates` manifest in a
background thread. This check never delays the application window. Only HTTPS
search/API locations for built-in providers and their approved website domains
can change; the manifest cannot install or run program code. If a website has
changed its page layout rather than its address, Twano will continue to show
**Provider Update Needed** until a normal application update supplies a tested
parser fix.

When ordinary title and author searches produce no result above 60%, EPUB files
can also be compared with first-sentence information returned by Open Library.
This is a bounded author search and is used only when the author is known and
the opening text provides a strong phrase match.

For short stories catalogued under a story title rather than their containing
book, Twano can use Wikipedia's public search API as a bounded work resolver.
It accepts a containing title only when the result evidence contains both the
complete local story title and the author's surname. The resolved title is then
looked up through the active book and cover providers in the normal way.

Use **Sort plugins** above the approved-plugin list to arrange providers by
name from **A–Z** or **Z–A**. Changing the order keeps the current row and any
checked plugins selected.

The Plugins page intentionally uses a controlled catalogue.

The **API Key** column shows only credential state:

- **API Key Added** means the protected key is ready for that provider.
- **Not Added** means an optional or required provider key has not been saved.
- **Needs Re-entry** means encrypted data exists but Windows cannot unlock it.
- **None Required** means the provider works without an API key.

The key itself is never displayed in the table.

The **Provider Check** column reports the most recent enabled search:

- **Working** means the provider responded in the format Twano expects.
- **Access Blocked** means the site displayed a bot check, CAPTCHA, access
  denial, or request limit. Try again later.
- **Provider Update Needed** means the site responded but changed the page
  structure Twano reads. Report that provider name and status to Twano support
  so its built-in reader can be updated.
- **Temporarily Unavailable** means the connection or provider failed.
- **Not Checked Yet** means no search has tested that provider in this
  installation.

A provider failure is never reported as simply “no matching book.” The same
plain-language reason appears at the bottom of Metadata & Cover Art. Twano
stores only the provider, status, check time, and safe diagnostic—not the
searched title, API key, or returned page.

- Tick the checkbox beside one or more plugins to manage them together. With
  no boxes checked, the buttons continue to act on the highlighted row.
- Choose **Install Selected**, then **Enable Selected**. Every eligible
  checked provider changes status; providers needing an API key remain at
  **Setup required** until their key is configured.
- **Disable Selected** turns off every checked active plugin.
- **Uninstall Selected** returns approved built-in providers to
  **Available** without deleting their saved API keys. Twano's required
  embedded-metadata reader cannot be uninstalled.
- **Delete Selected Package** is available only for downloaded external
  plugin packages. It asks for confirmation and permanently removes the
  package and its saved key. Approved built-in providers cannot be deleted.
- A provider that needs an API key changes to **Setup required** after
  installation. Choose **Configure API Key**, follow its in-app guide, save the
  key, then choose **Enable Selected**.
- For an Active plugin, **Disable Selected** is available and Enable is greyed
  out. For a Disabled plugin, **Enable Selected** is available and Disable is
  greyed out.
- External `.twano-plugin` files are accepted only when their SHA256 is in
  Twano's approved catalogue.
- File-modifying plugin capabilities are refused.
- A broken external plugin can be disabled or quarantined without preventing
  Twano from starting.

### Getting provider API keys

**Google Books (optional)**

Google Books normally works without a key. If Metadata & Cover Art reports
**Unavailable: Google Books**, an API key can provide request identification
and a separate quota:

1. Sign in to [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project and
   [enable Books API](https://console.cloud.google.com/apis/library/books.googleapis.com).
3. Open **APIs & Services > Credentials** and create an API key.
4. Restrict the key to **Books API**.
5. In Twano, select **Google Books Metadata & Covers**, choose **Configure API
   Key**, paste the key, and save it.

Google Books can remain Active without a key. Removing this optional key does
not disable the provider.

The complete current testing-key list and removal checklist is in
`docs/API-Keys-for-Testing.md`.

**Apple Books**

Apple Books does not require a key. Install and enable **Apple Books Metadata
& Covers** to include its regional ebook catalogue in the normal search.
Availability and edition details can differ by country. Twano uses the
Australian storefront first, uses the result inside the review workflow, and
never opens Apple Books automatically.

**ISBNdb**

1. Create an [ISBNdb account](https://isbndb.com/) and select a suitable API
   trial or subscription.
2. Copy the API key from the ISBNdb account.
3. In Twano, install **ISBNdb Metadata & Covers**, choose **Configure API
   Key**, paste the key, and save it.
4. Choose **Enable**. ISBNdb now contributes ISBNs, descriptions, publication
   details and available covers to the combined search.

**Hardcover**

1. Create or sign in to a free [Hardcover account](https://hardcover.app/).
2. Open [Hardcover Account > API](https://hardcover.app/account/api).
3. Generate or copy the API token shown for your account.
4. In Twano, install **Hardcover Metadata & Covers**, choose **Configure API
   Key**, paste the token, and save it.
5. Choose **Enable**. Hardcover now joins the normal metadata and automatic
   cover search.

Use a read-only or scoped token if Hardcover makes one available. A token may
be pasted with or without the `Bearer` prefix.

**Comic Vine**

1. Create or sign in to a [Comic Vine account](https://comicvine.gamespot.com/).
2. Open the [Comic Vine API page](https://comicvine.gamespot.com/api/) and read
   its terms.
3. Copy the API key displayed for your account.
4. In Twano, install **Comic Vine Metadata & Covers**, choose **Configure API
   Key**, paste the key, and save it.
5. Choose **Enable**. Use this provider for comics and graphic novels.

Comic Vine states that its API is for personal, non-commercial use and applies
rate limits. Do not enable it if your use does not meet those terms.
Run **Find Metadata & Covers** for a comic to perform a real provider check.
Return to Plugins afterward; a successful Comic Vine response is shown as
**Working**, while a rejected key or unavailable service is explained there.

Twano automatically excludes Comic Vine from EPUB, PDF, and other non-comic
metadata and cover searches. Comic Vine results are shown only for CBR and CBZ
comic files.

**Amazon, Google Images, Edelweiss, Project Gutenberg, Harvard LibraryCloud,
and Crossref**

These providers display **None Required**:

- **Amazon Metadata & Covers** searches public Amazon Australia first, then
  the US, UK and Canada book catalogues. Results identify the marketplace that
  supplied them. If one marketplace is unavailable, the remaining searches
  continue. Amazon may sometimes require a bot check; Twano then marks the
  provider **Access Blocked** only when none of the marketplaces can complete
  the search, instead of claiming no cover exists.
- **Google Images Book Covers** is a cover-only fallback. Results still pass
  Twano's image validation and must be selected with **Use Cover**. Provider
  version 1.1 recognises current Google image-result markup; after updating,
  run a Metadata & Covers search to record a fresh **Working** check.
- **Edelweiss Metadata & Covers** searches publisher catalogue records. A
  changed catalogue/card layout is shown as **Provider Update Needed**.
- **Project Gutenberg Metadata & Covers** searches public-domain classics
  through the open Gutendex catalogue. It can return summaries and covers
  where the catalogue contains them, but it is not useful for modern
  commercial books.
- **Harvard LibraryCloud Metadata** searches open Harvard bibliographic
  records by ISBN, title or author. It usually improves identifiers,
  publication details and descriptions rather than cover choices.
- **Crossref Academic Book Metadata** searches DOI-registered academic books,
  textbooks and book chapters. Crossref normally provides bibliographic data,
  not cover artwork.

Install and enable only the catalogues useful for your library. A provider
without a usable cover can still enrich missing metadata, but it will not be
shown in the cover chooser.

The Approved Plugins list shows each provider's publisher, version, purpose,
status, API-key state, last provider check and reputable source. Use the
**Version** value when reporting a provider problem.

**Big Book API**

1. Review the [Big Book API plans](https://bigbookapi.com/pricing).
2. Create an account and obtain an API key.
3. In Twano, install **Big Book API Metadata & Covers**, choose **Configure
   API Key**, paste the key, and save it.
4. Choose **Enable**.

The current free plan is limited to 50 requests per day, requires attribution,
and is for non-commercial use. Twano retrieves details for at most three
matches per search to conserve that allowance.

**OpenWeb Ninja**

1. Create an account from the
   [OpenWeb Ninja Books API page](https://www.openwebninja.com/api/real-time-books-data).
2. Create an API key in the provider dashboard.
3. In Twano, install **OpenWeb Ninja Books Metadata & Covers**, choose
   **Configure API Key**, paste the key, and save it.
4. Choose **Enable**.

The current free plan has a hard limit of 100 requests per month. Its book
results come from Google Books, so it is best used as an optional fallback
rather than enabled alongside a working direct Google Books connection.

Twano masks keys while they are entered and encrypts them for the current
Windows account before saving them. Keys are never shown again, copied into
the normal plugin state file, or included in diagnostics. Use **Configure API
Key > Remove Saved Key** to remove one. Providers that require a key are
disabled when it is removed; Google Books can continue without its optional
key. Apple Books, Open Library, Project Gutenberg, Harvard LibraryCloud and
Crossref display **None Required**.

The **Calibre & Network Libraries** tab can detect Calibre, validate a Calibre
library, open it through Calibre's supported command line, or add its folder as
a Twano scan source. Twano does not write directly to Calibre's database.
Calibre is never required for metadata or cover searching.

## Protection, backups, and Undo

Select the safety card at the bottom of the left navigation to open
**Backups & Restore**.

- Significant supported changes create a verified catalogue backup.
- **Restore Backup** replaces the catalogue only after re-verification and
  first creates a recovery copy of the current catalogue.
- **Activity & Undo** explains protected operations and offers Undo when the
  recorded operation is fully reversible.
- **Review Old Backups** removes only expired, verified, Twano-owned
  backup/manifest pairs after showing a summary.
- Set retention to `0` days to keep all backups.

Read-Only mode prevents catalogue changes. Standard mode is required to apply
scan previews, metadata updates, or supported Undo operations.

## Settings

- **General:** update reminder and first-use guidance.
- **Home:** hero banner and startup rotation.
- **Reading:** choose how ebook files open.
- **Metadata & Privacy:** enable or disable Open Library and set cache duration.
- **Accessibility:** text size, reduced motion, and visible focus.
- **Protection:** read-only/standard mode, backup folder, and retention.

Settings are validated before saving and persist after restart.

## Help pages

- **User Guide** is the in-app summary of these workflows.
- **What's New** describes the current release.
- **About** shows the version, release name, data locations, and privacy notes.

## Data locations

Beta 1 stores its catalogue and settings under:

```text
%LOCALAPPDATA%\Twano
```

This separation keeps user data outside the source or installed program folder.
The earlier development catalogue under
`%USERPROFILE%\.twanos_ebook_manager` is not deleted or overwritten.

## If something goes wrong

1. Stop before approving another change.
2. Record the page, action, and exact message.
3. Take a screenshot.
4. Keep the catalogue, backup, and quarantine folders unchanged.
5. Use the defect template in
   `docs/R4-RC1-Testing-Guide.md`.

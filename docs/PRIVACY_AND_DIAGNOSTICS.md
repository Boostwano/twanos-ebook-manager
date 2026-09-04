# Privacy and Diagnostics

## Local data

Twano stores its catalogue, preferences, backups, downloaded covers, controlled
plugins, and recoverable quarantine under `%LOCALAPPDATA%\Twano` or a backup
folder selected by the user. Ebook files remain in the user's chosen library
locations unless the user explicitly quarantines a confirmed exact duplicate.
Found cover previews are cached separately from selected covers. Displaying a
preview does not add it to the catalogue; **Use Cover** and the protected Apply
workflow are still required.

## Internet access

Twano does not need an account. Internet use is limited to actions the user
starts or enables:

- Open Library metadata and cover lookup sends the entered title, author, or
  ISBN to Open Library.
- Google Books metadata and automatic cover search sends the selected book's
  title, author, or ISBN to Google Books.
- Optional Amazon, Google Images, and Edelweiss providers send the selected
  title, author, or ISBN to those public catalogue/search pages. They do not
  open a browser or require a user API key.
- When enabled, Hardcover sends the requested title, author, or ISBN to its
  GraphQL API using the user's saved token.
- When enabled, Comic Vine sends a comic title and the user's API key to its
  API. Comic Vine's personal/non-commercial terms and rate limits apply.
- The combined Metadata & Cover search runs inside Twano. Enabled public-page
  providers retrieve only the result page needed for the search.
- When a filename clearly follows `Title - Author.ext` or
  `Author - Title.ext`, Twano may use those terms instead of incomplete
  embedded metadata for a search you start.
- Check for Updates currently displays local release status and does not
  download an update.
- Opening a plugin source link uses the normal web browser.

Open Library can be disabled in **Settings > Metadata & Privacy**. Other active
providers remain available.

## Plugin API keys

Google Books, Hardcover, and Comic Vine keys are encrypted with Windows Data
Protection API for the current Windows account and stored separately from
ordinary plugin state. Twano masks them in the setup window, does not display
them after they are saved, and does not include them in diagnostics. The
Google Books key is optional; removing it leaves that provider Active.
Removing a required Hardcover or Comic Vine key disables that provider.

## Calibre and network folders

Twano validates Calibre and network locations without writing to Calibre's
database. Scanned paths and extracted book metadata are stored in the local
Twano catalogue. An unavailable network source remains unavailable rather than
being treated as mass deletion. Cover search does not call or require Calibre.

## Diagnostics and defect reports

Automated logs and reports should not include ebook contents. Before sharing a
screenshot or report, review it for private titles, author names, usernames,
folder names, network server names, and paths. Only share the smallest
information needed to reproduce a defect.

Public-page provider checks are saved in
`%LOCALAPPDATA%\Twano\provider-health.json`. Each entry contains only the
provider ID, health category, check time, and a bounded parser diagnostic.
Search terms, returned HTML, ebook contents, and credentials are not stored.
The categories distinguish a genuine empty result from access blocking,
temporary connection failure, and a provider page layout that requires a
Twano code update.

## Removal and recovery

Program files and user data are deliberately separate. Removing the application
does not automatically erase `%LOCALAPPDATA%\Twano`, verified backups, ebook
libraries, or the older `%USERPROFILE%\.twanos_ebook_manager` development data.

# Twano API Keys for Testing

This list covers the providers implemented in the current R4 Beta 2 build.
Never paste an API key into source code, documentation, screenshots, bug
reports, Git, or a release ZIP.

## Keys used by the current build

| Provider | Needed for testing? | Where to obtain it | Twano behaviour |
|---|---|---|---|
| Open Library | No key | [Open Library developer information](https://openlibrary.org/developers/api) | Install and enable the provider. |
| Google Books | Optional but recommended for live testing | [Enable Books API and create a Google API key](https://console.cloud.google.com/apis/library/books.googleapis.com) | Public searches may work without a key. The key must belong to a project with Books API enabled. Restrict it to Books API; do not apply an HTTP website-referrer restriction to this Windows application. |
| Apple Books | No key | [Apple Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/) | Install and enable the provider. Results vary by regional Apple catalogue. |
| Amazon | No key | [Amazon Books](https://www.amazon.com/books-used-books-textbooks/b) | Uses public book-result pages. A bot check is reported as **Access Blocked**, not as no result. |
| Google Images | No key | [Google Images](https://images.google.com/) | Cover-only fallback. Page changes are reported as **Provider Update Needed**. |
| Edelweiss | No key | [Edelweiss](https://www.edelweiss.plus/) | Uses public publisher-catalogue pages. Page/card changes are reported separately from no match. |
| ISBNdb | Required | [ISBNdb account](https://isbndb.com/) | A personal trial or subscription key is required. Paste the key, then enable the provider. |
| Hardcover | Required | [Hardcover account API page](https://hardcover.app/account/api) | Paste the account API token, then enable the provider. |
| Comic Vine | Required | [Comic Vine API page](https://comicvine.gamespot.com/api/) | Paste the personal API key, then enable the provider. Comic Vine is intended for comic and graphic-novel results. |
| Project Gutenberg via Gutendex | No key | [Gutendex project and API](https://github.com/garethbjohnson/gutendex) | Install and enable the provider. It is limited to public-domain Project Gutenberg books. |
| Harvard LibraryCloud | No key | [Harvard LibraryCloud API](https://harvardwiki.atlassian.net/wiki/spaces/LibraryStaffDoc/pages/43287734/LibraryCloud+APIs) | Install and enable the provider. It primarily supplies bibliographic records rather than covers. |
| Crossref | No key | [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | Install and enable the provider for DOI-registered academic books and chapters. |
| Big Book API | Required | [Big Book API pricing and signup](https://bigbookapi.com/pricing) | The free plan currently permits 50 requests per day, requires a backlink, and is for non-commercial use. Twano limits detail lookups to conserve quota. |
| OpenWeb Ninja | Required | [OpenWeb Ninja Books API](https://www.openwebninja.com/api/real-time-books-data) | The free plan currently permits 100 requests per month. This is a Google Books-derived fallback. |
| Embedded Book Metadata | No key | Included locally | Reads information already stored in the ebook. |

## Providers that do not currently accept a key in Twano

- ReadAnyBook is not an implemented metadata provider. Its website is not
  queried, so Twano cannot download its descriptions or covers.
- Goodreads and Book Cover Archive are not active providers in the current
  build.
- Do not obtain or pay for credentials for those services for this Beta test.

## Applying a test key

1. Open **Plugins**.
2. Select the installed provider.
3. Choose **Configure API Key**. Apple Books and other no-key providers skip
   this step.
4. Paste the key and choose **Save**.
5. Confirm the **API Key** column says **API Key Added**, not **Needs
   Re-entry**.
6. Enable the provider if it is disabled.
7. Run **Find Metadata & Covers** and read the provider result at the bottom.

Twano encrypts these values with Windows Data Protection for the current
Windows account. A key saved under another Windows account or security context
may not be unlockable. Re-enter it while running Twano normally if the Plugins
page reports **Needs Re-entry**. Providers that do not use a key display
**None Required**.

## Removing test keys before release

API keys are kept under `%LOCALAPPDATA%\Twano\plugin-credentials.json`; they
are not stored in the project and are excluded from release ZIP files. They do
not become part of the installer merely because they were used for testing.

At the end of live-provider testing:

1. Open **Plugins**.
2. Select Google Books, ISBNdb, Hardcover, Comic Vine, Big Book API and
   OpenWeb Ninja in turn.
3. Choose **Configure API Key** and then **Remove Saved Key**.
4. Confirm required-key providers become disabled.
5. Confirm the production package contains no `plugin-credentials.json`.

For a public release, each user supplies their own optional or required
provider credentials. Twano must never ship a developer or tester key.

# Twano R4 RC1 Release Notes

**Release name:** Production Release Candidate  
**Baseline:** Accepted R4 Beta 2 package from 30 July 2026

RC1 freezes the accepted feature set and concentrates on Windows distribution,
version consistency, clean installation, upgrade safety, uninstall behaviour,
checksums, legal notices and release evidence.

## Included application behaviour

- New approved Twano identity with a warm open leather-book mark, ivory
  wordmark and the tagline **Your Library, Beautifully Organised**.
- A compact branded startup splash uses a four-pixel cyan frame matching its
  tagline, transparent outer corners and no embedded release number. It
  remains visible for five seconds and then fades smoothly into the main
  window.
- Installed Apps, Control Panel, shortcuts and the installer use the full
  **Twano's eBook Manager** name and approved warm book icon.
- Packaged Home banners resolve from the installed application so the selected
  photographic banner is shown instead of the emergency painted fallback.
- Home preserves each authored banner title as a separate transparent PNG
  overlay; live controls remain in a separate upper-left area without
  duplicating or obscuring the artwork's wording.
- Added **By the light of a warm Fire**, a cosy library-and-fireplace banner
  with the title artwork rendered in matching full-height capitals.
- Home banners preserve their original proportions. Wide windows anchor the
  title at left and artwork at right, joined by a matching flexible navy
  centre and soft fades instead of stretching the image or exposing a
  rectangular title-image background.
- Complete accepted Beta 2 library, scan, metadata and cover, health, plugin,
  backup, restore, duplicate and guidance workflows.
- Numbered `01 - Title - Author` filenames now retain the real title and
  author during online lookup. Metadata review also includes a separate
  **Find Covers** action that preserves the reviewed metadata fields and
  gathers every confident, usable cover from every enabled cover provider.
- Metadata lookup now imports structured series names and reading order from
  Open Library, Google Books and Hardcover, and safely recognises Amazon
  titles written as `Title (Series Name Book 12)`. Provider-specific values
  remain visible for review when sources disagree, and older cached results
  are refreshed automatically.
- Updated Amazon parsing for its current linked-heading result cards and
  rejected unrelated Apple Books results that do not contain the requested
  title words. Provider blocking remains visible instead of being mistaken for
  a valid empty search.
- Regional providers now prefer Australia: Amazon checks AU before its other
  English marketplaces, Apple Books uses the AU storefront, and Google Books
  requests Australian English and ranks AU editions first while preserving
  global fallbacks.
- At 900 x 600 the Metadata page prioritises Title, Author, Series, Series
  number and cover actions; secondary fields return at larger sizes. Buttons
  and fields remain inside the window without whole-page scrolling.
- Metadata Apply now offers an explicit protected organisation option. Its
  Preview shows the exact source and destination before creating author and
  optional series folders, naming standalone books `Title - Author`, and
  prefixing series books with their zero-padded reading sequence. Existing
  files are never overwritten and a failed catalogue commit restores the
  ebook to its original path.
- Application and Windows version information aligned to **R4 RC1**.
- A repeatable PyInstaller portable build with timestamp-first output names.
- Optional Inno Setup installer generation when Inno Setup is installed.
- SHA256 files generated beside every portable ZIP and installer.
- Existing catalogue, settings, covers, backups and quarantine data remain
  under `%LOCALAPPDATA%\Twano` and outside the installed program directory.

## Release boundary

RC1 permits only release-blocking, security, data-integrity, documentation and
packaging corrections. It is not the final public release and must be tested
using `R4-RC1-Testing-Guide.md`.

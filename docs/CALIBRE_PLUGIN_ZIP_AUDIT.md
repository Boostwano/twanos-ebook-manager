# Calibre Plugin ZIP Audit

Audit date: 30 July 2026  
Source folder: `C:\Twano\Twano-R4-RC6.4\zip`

## Safety decision

Twano does not import or execute these Calibre ZIPs. Every inspected ZIP imports
Calibre modules, so none can work safely when Calibre is absent. Some also
contain copyleft code, lack a clear licence, scrape websites, bundle anti-bot
code, or modify files through Calibre-specific interfaces.

Where a source was suitable, Twano received a small native provider or browser
helper written for Twano's service layer. This keeps Calibre optional and
preserves Twano's plugin controls, review flow, backups, and privacy wording.

## Native Twano options built from the audit

| ZIP reviewed | Twano option | Result |
|---|---|---|
| `Comicvine.zip` | Comic Vine Metadata & Covers | Native API provider. Requires the user's API key. Personal/non-commercial terms and rate limits are shown. |
| `Hardcover.zip` | Hardcover Metadata & Covers | Native GraphQL provider. Requires the user's Hardcover token. No code was copied from the unlicensed ZIP. |
Google Books Metadata & Covers is also available as a native provider. It can
search without a key, while allowing the user to save an optional restricted
Books API key if anonymous requests are unavailable or rate limited. It was
already part of Twano's independent provider work and does not come from a
Calibre ZIP.

Browser-only shortcuts from the earlier prototype are not included in the
everyday Metadata workflow. One **Find Metadata & Covers** action now uses
direct providers and does not open Amazon, Goodreads, Wikidata, ISFDB, or
other cover-search websites.

## ZIPs not transplanted

| ZIP | Reason |
|---|---|
| `Barnes & Noble.zip` | Calibre-only website scraper with no clear bundled licence. |
| `Beam Ebooks.zip` | Calibre-only niche website provider with no clear bundled licence. |
| `Biblioman.zip` | Calibre-only website provider with no clear bundled licence. |
| `Fantastic Fiction Adults.zip` | Calibre-only website scraper with no clear bundled licence. |
| `Fantastic Fiction.zip` | Calibre-only website scraper with no clear bundled licence. |
| `FictionDB.zip` | Calibre-only website scraper with no clear bundled licence. |
| `Kobo Metadata.zip` | Bundles anti-bot/captcha behaviour and is too fragile for an approved provider. |
| `Skoob Books.zip` | Calibre-only website provider with no clear bundled licence. |
| `Smashwords Metadata.zip` | Calibre-only website provider with no clear bundled licence. |
| `StoryGraph.zip` | Bundles anti-bot/Turnstile behaviour and is not suitable for a reputable direct integration. |
| `xTrance.zip` | Calibre-only website provider with no clear bundled licence. |

## Calibre utilities outside the provider scope

| ZIP | Reason |
|---|---|
| `Book List Plus.zip` | Calibre library GUI/reporting utility, not a metadata or cover provider. |
| `Create Hardcover.zip` | Calibre-specific image/file creation tool; any Twano equivalent must use the protected change workflow. |
| `Prettify Cover.zip` | Image-modifying Calibre utility; not safe to transplant into read-only lookup. |
| `Quality Check.zip` | Large Calibre library maintenance utility that duplicates or exceeds Twano's simpler Library Health scope. |

## API-key storage

Google Books, Hardcover, and Comic Vine keys are encrypted with Windows Data
Protection API for the current Windows account. They are stored separately
from normal plugin state, masked during entry, never shown again, and omitted
from diagnostics. Removing a required key disables that provider; removing the
optional Google Books key leaves Google Books Active.

See [USER_GUIDE.md](USER_GUIDE.md#getting-provider-api-keys) for setup steps and
[R4-Beta2-Complete-Testing-Guide.md](R4-Beta2-Complete-Testing-Guide.md#4a-optional-api-key-providers)
for the full test schedule.

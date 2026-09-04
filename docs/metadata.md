# Metadata

## Current Local Extraction

`src/core/metadata.py` validates the path and handles EPUB files as ZIP archives. It locates the OPF package through `META-INF/container.xml`, parses Dublin Core elements, collapses whitespace, joins multiple creators with commas, and normalises ISBN-10 or ISBN-13 candidates.

Confirmed statuses are:

- `embedded`: at least one supported field was extracted
- `unavailable`: no supported metadata was found
- `missing`: the path is not an existing file
- `unsupported`: the file is not an EPUB
- `invalid`: the EPUB package document cannot be located
- `error`: the EPUB cannot be read or parsed
- `pending`: database default before processing

## Supported Formats

Scanning discovers EPUB, MOBI, AZW, AZW3, PDF, FB2, DJVU, CBZ, CBR, and TXT files. Embedded metadata extraction is implemented only for EPUB. Discovery support is not metadata-extraction support.

## Current Fields

The local extractor and provider-neutral result support title, author, ISBN, publisher, language, published date, and extraction status. `MetadataResult` additionally records confidence and provider name.

## Provider Framework

The current metadata engine defines:

- `MetadataResult`, an immutable UI-independent result
- `MetadataProvider`, the abstract `name`, `supports()`, and `extract()` contract
- `ProviderManager`, which executes providers in order and merges useful fields
- `metadata.providers.LocalMetadataProvider`, which wraps existing extraction
- `metadata.providers.OpenLibraryProvider`, which performs optional external enrichment
- provider-aware metadata and scan services

Local extraction is always registered first. Open Library is enabled by setting `TWANOS_OPEN_LIBRARY_ENABLED=true`; it defaults off to avoid disclosing library identifiers or titles without opt-in. There is no settings screen or API key.

## Confidence and Provider Precedence

Confidence ranges from `0.0` through `1.0`. The local adapter assigns `1.0` to `embedded` results and `0.0` otherwise. Open Library assigns `1.0` for an exact normalised ISBN, `0.85` for an exact normalised title and author, and `0.70` for an exact normalised title of at least eight characters when no author is available. Case, whitespace, and harmless punctuation differences are ignored; unrelated results and short title-only matches are rejected.

Merging is field-by-field. Empty incoming fields never erase values. Missing local fields are enriched. A strictly higher-confidence result may replace populated lower-confidence values; equal or lower-confidence values preserve populated local fields.

## Open Library Networking

The provider uses the official Search API:

- `GET https://openlibrary.org/search.json?isbn=...` first for valid ISBNs
- `GET https://openlibrary.org/search.json?title=...&author=...` after no acceptable ISBN result
- title-only search when no author is available

Requests select only supported fields, use a 10-second timeout and identifiable user agent, and do not retry. HTTP errors, timeouts, connection errors, invalid JSON, incomplete documents, and no matches produce a clean no-result. Identical queries are cached in memory for the provider's scan-session lifetime, including no-results and failures. Provider execution is sequential in the existing scan worker, so requests do not burst or run on the GUI thread.

No HTTP dependency was added; the implementation uses Python's standard-library `urllib.request`. Google Books, covers, persistent caching, and review UI remain future work.

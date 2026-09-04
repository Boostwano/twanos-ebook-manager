# Calibre Integration

Calibre support is optional. Twano detects Calibre only for users who want to
open a Calibre library or use Calibre as a reader. A user can otherwise choose
any Windows ebook reader.

Twano does not:

- require Calibre at startup;
- use Calibre for metadata or cover searches;
- load Calibre plugin ZIP files;
- write directly to a Calibre `metadata.db` file.

Metadata & Cover Art uses Twano's own direct provider services. One action
searches Open Library, Google Books, and any other active direct providers for
book details and covers together. The everyday workflow does not open browser
search websites.

Calibre plugin source code may be reviewed as implementation reference only
when its licence permits that use. Any Twano provider must remain independent
of Calibre's Python runtime and plugin API.

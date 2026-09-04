"""Tests for embedded eBook metadata extraction."""

import zipfile
from pathlib import Path

from core.metadata import (
    extract_epub_opening_excerpt,
    extract_metadata,
    normalise_isbn,
)


CONTAINER_XML = """<?xml version="1.0"?>
<container
    version="1.0"
    xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile
            full-path="OEBPS/content.opf"
            media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>
"""

PACKAGE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<package
    xmlns="http://www.idpf.org/2007/opf"
    version="3.0"
    unique-identifier="book-id">
    <metadata
        xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier id="book-id">
            urn:isbn:9780261103344
        </dc:identifier>
        <dc:title>The Hobbit</dc:title>
        <dc:creator>J. R. R. Tolkien</dc:creator>
        <dc:publisher>Example Publisher</dc:publisher>
        <dc:language>en</dc:language>
        <dc:date>1937-09-21</dc:date>
    </metadata>
</package>
"""


def create_test_epub(epub_path: Path) -> None:
    """Create a minimal EPUB archive for testing."""
    with zipfile.ZipFile(epub_path, "w") as archive:
        archive.writestr(
            "mimetype",
            "application/epub+zip",
        )
        archive.writestr(
            "META-INF/container.xml",
            CONTAINER_XML,
        )
        archive.writestr(
            "OEBPS/content.opf",
            PACKAGE_XML,
        )


def test_extract_epub_metadata(tmp_path: Path) -> None:
    epub_path = tmp_path / "the_hobbit.epub"
    create_test_epub(epub_path)

    metadata = extract_metadata(epub_path)

    assert metadata.title == "The Hobbit"
    assert metadata.author == "J. R. R. Tolkien"
    assert metadata.isbn == "9780261103344"
    assert metadata.publisher == "Example Publisher"
    assert metadata.language == "en"
    assert metadata.published_date == "1937-09-21"
    assert metadata.extraction_status == "embedded"


def test_normalise_isbn() -> None:
    assert normalise_isbn("ISBN 978-0-261-10334-4") == "9780261103344"
    assert normalise_isbn("0-261-10334-2") == "0261103342"
    assert normalise_isbn("6766468014821") is None
    assert normalise_isbn("Not an ISBN") is None


def test_extract_epub_opening_excerpt_is_short_and_skips_headings(
    tmp_path: Path,
) -> None:
    epub_path = tmp_path / "story.epub"
    package = """<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf">
      <manifest><item id="chapter" href="chapter.xhtml"
        media-type="application/xhtml+xml"/></manifest>
      <spine><itemref idref="chapter"/></spine>
    </package>"""
    chapter = """<html><body><h1>BOOK ONE</h1>
      <p>The spaceship resumed humming around Sweeney without his noticing
      the change. The captain called again from the wall speaker.</p>
    </body></html>"""
    with zipfile.ZipFile(epub_path, "w") as archive:
        archive.writestr("META-INF/container.xml", CONTAINER_XML)
        archive.writestr("OEBPS/content.opf", package)
        archive.writestr("OEBPS/chapter.xhtml", chapter)

    excerpt = extract_epub_opening_excerpt(epub_path, max_characters=120)

    assert excerpt.startswith("The spaceship resumed humming")
    assert "BOOK ONE" not in excerpt
    assert len(excerpt) <= 120

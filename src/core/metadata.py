"""Embedded metadata and bounded opening-text extraction for eBooks."""

import html
import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


CONTAINER_PATH = "META-INF/container.xml"

CONTAINER_NAMESPACE = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
}

OPF_NAMESPACE = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": "http://www.idpf.org/2007/opf",
}


@dataclass(frozen=True)
class BookMetadata:
    """Metadata extracted from an eBook file."""

    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    language: str | None = None
    published_date: str | None = None
    extraction_status: str = "unavailable"


def clean_text(value: str | None) -> str | None:
    """Remove excess whitespace from extracted metadata."""
    if value is None:
        return None

    cleaned = " ".join(value.split())
    return cleaned or None


def normalise_isbn(value: str | None) -> str | None:
    """Return a checksum-valid normalised ISBN-10 or ISBN-13 value."""
    if not value:
        return None

    candidate = re.sub(r"[^0-9Xx]", "", value).upper()

    if len(candidate) in (10, 13):
        return candidate if _is_valid_isbn(candidate) else None

    isbn_match = re.search(
        r"(?:ISBN(?:-1[03])?\s*:?\s*)?"
        r"((?:97[89][\s-]?)?[0-9][0-9Xx\s-]{8,16})",
        value,
        flags=re.IGNORECASE,
    )

    if isbn_match is None:
        return None

    candidate = re.sub(
        r"[^0-9Xx]",
        "",
        isbn_match.group(1),
    ).upper()

    return (
        candidate
        if len(candidate) in (10, 13) and _is_valid_isbn(candidate)
        else None
    )


def _is_valid_isbn(value: str) -> bool:
    """Validate ISBN check digits so unrelated numeric IDs are ignored."""
    if len(value) == 13 and value.isdigit():
        total = sum(
            int(character) * (1 if index % 2 == 0 else 3)
            for index, character in enumerate(value)
        )
        return total % 10 == 0
    if len(value) == 10 and value[:9].isdigit():
        check_value = 10 if value[-1] == "X" else (
            int(value[-1]) if value[-1].isdigit() else -1
        )
        if check_value < 0:
            return False
        total = sum(
            (10 - index) * int(character)
            for index, character in enumerate(value[:9])
        )
        return (total + check_value) % 11 == 0
    return False


def extract_metadata(file_path: str | Path) -> BookMetadata:
    """Extract embedded metadata from a supported eBook file."""
    path = Path(file_path)

    if not path.exists() or not path.is_file():
        return BookMetadata(extraction_status="missing")

    if path.suffix.lower() == ".epub":
        return extract_epub_metadata(path)

    return BookMetadata(extraction_status="unsupported")


def extract_epub_metadata(file_path: str | Path) -> BookMetadata:
    """Extract metadata from an EPUB package document."""
    path = Path(file_path)

    try:
        with zipfile.ZipFile(path, "r") as epub_archive:
            package_path = _find_package_document(epub_archive)

            if package_path is None:
                return BookMetadata(extraction_status="invalid")

            package_data = epub_archive.read(package_path)
            package_root = ElementTree.fromstring(package_data)

            title = _first_element_text(
                package_root,
                ".//dc:title",
            )

            authors = _all_element_text(
                package_root,
                ".//dc:creator",
            )

            identifiers = _all_element_text(
                package_root,
                ".//dc:identifier",
            )

            publisher = _first_element_text(
                package_root,
                ".//dc:publisher",
            )

            language = _first_element_text(
                package_root,
                ".//dc:language",
            )

            published_date = _first_element_text(
                package_root,
                ".//dc:date",
            )

            isbn = None

            for identifier in identifiers:
                isbn = normalise_isbn(identifier)

                if isbn:
                    break

            author = ", ".join(authors) if authors else None

            has_metadata = any(
                (
                    title,
                    author,
                    isbn,
                    publisher,
                    language,
                    published_date,
                )
            )

            return BookMetadata(
                title=title,
                author=author,
                isbn=isbn,
                publisher=publisher,
                language=language,
                published_date=published_date,
                extraction_status="embedded" if has_metadata else "unavailable",
            )

    except (
        KeyError,
        OSError,
        UnicodeDecodeError,
        zipfile.BadZipFile,
        ElementTree.ParseError,
    ):
        return BookMetadata(extraction_status="error")


def extract_epub_opening_excerpt(
    file_path: str | Path,
    *,
    max_characters: int = 240,
) -> str:
    """Return a short prose excerpt from the start of a local EPUB.

    The excerpt is deliberately bounded because it is intended only as a
    search fingerprint when normal bibliographic searches return weak matches.
    """
    path = Path(file_path)
    if path.suffix.casefold() != ".epub" or not path.is_file():
        return ""
    limit = max(80, min(int(max_characters), 400))
    try:
        with zipfile.ZipFile(path, "r") as epub_archive:
            package_path = _find_package_document(epub_archive)
            if package_path is None:
                return ""
            package_root = ElementTree.fromstring(
                epub_archive.read(package_path)
            )
            manifest = {
                item.attrib.get("id", ""): item.attrib.get("href", "")
                for item in package_root.findall(".//{*}manifest/{*}item")
                if item.attrib.get("id") and item.attrib.get("href")
            }
            spine_paths = [
                manifest.get(item.attrib.get("idref", ""), "")
                for item in package_root.findall(".//{*}spine/{*}itemref")
            ]
            package_folder = posixpath.dirname(package_path)
            for relative_path in spine_paths:
                if not relative_path:
                    continue
                content_path = posixpath.normpath(
                    posixpath.join(package_folder, relative_path)
                )
                try:
                    document = epub_archive.read(content_path).decode(
                        "utf-8", errors="replace"
                    )
                except KeyError:
                    continue
                excerpt = _first_prose_excerpt(document, limit)
                if excerpt:
                    return excerpt
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError):
        return ""
    return ""


def _first_prose_excerpt(document: str, limit: int) -> str:
    """Extract the first substantial paragraph from one XHTML document."""
    cleaned_document = re.sub(
        r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>",
        " ",
        document,
        flags=re.IGNORECASE | re.DOTALL,
    )
    paragraphs = re.findall(
        r"<p\b[^>]*>(.*?)</p>",
        cleaned_document,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for paragraph in paragraphs:
        text = html.unescape(re.sub(r"<[^>]+>", " ", paragraph))
        text = " ".join(text.split())
        if len(text) < 60:
            continue
        sentence_match = re.match(
            r"(.{60,%d}?[.!?](?:[\"'\u201d\u2019])?)\s" % limit,
            text + " ",
        )
        excerpt = sentence_match.group(1) if sentence_match else text[:limit]
        return excerpt.strip()
    return ""


def _find_package_document(
    epub_archive: zipfile.ZipFile,
) -> str | None:
    """Locate the OPF package document inside an EPUB archive."""
    try:
        container_data = epub_archive.read(CONTAINER_PATH)
    except KeyError:
        return None

    container_root = ElementTree.fromstring(container_data)

    rootfile = container_root.find(
        ".//container:rootfile",
        CONTAINER_NAMESPACE,
    )

    if rootfile is None:
        return None

    full_path = rootfile.attrib.get("full-path")
    return clean_text(full_path)


def _first_element_text(
    root: ElementTree.Element,
    expression: str,
) -> str | None:
    """Return the cleaned text of the first matching XML element."""
    element = root.find(expression, OPF_NAMESPACE)

    if element is None:
        return None

    return clean_text(element.text)


def _all_element_text(
    root: ElementTree.Element,
    expression: str,
) -> list[str]:
    """Return cleaned text from all matching XML elements."""
    values: list[str] = []

    for element in root.findall(expression, OPF_NAMESPACE):
        value = clean_text(element.text)

        if value:
            values.append(value)

    return values

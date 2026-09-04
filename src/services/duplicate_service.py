"""Explainable duplicate detection and recoverable quarantine actions."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from database.database import DatabaseManager


@dataclass(frozen=True)
class DuplicateBook:
    book_id: int
    title: str
    author: str
    isbn: str
    file_format: str
    file_size: int
    file_path: str
    cover_path: str


@dataclass(frozen=True)
class DuplicateGroup:
    group_key: str
    evidence: tuple[str, ...]
    confidence: str
    books: tuple[DuplicateBook, ...]
    ignored: bool = False

    @property
    def exact_copy(self) -> bool:
        return bool(
            {"Exact file contents", "Same ebook contents"}
            & set(self.evidence)
        )


class DuplicateService:
    """Find likely duplicates without deleting ebook files."""

    def __init__(self, database: DatabaseManager | None = None) -> None:
        self.database = database or DatabaseManager()

    def find_groups(
        self,
        *,
        include_intentional: bool = False,
    ) -> tuple[DuplicateGroup, ...]:
        rows = self.database.get_books(include_missing=False)
        books = tuple(self._book(row) for row in rows)
        ignored_keys = set(self.database.list_duplicate_exception_keys())
        evidence_by_ids: dict[frozenset[int], set[str]] = {}

        self._add_value_groups(
            evidence_by_ids,
            books,
            value=lambda book: _normalise_isbn(book.isbn),
            evidence="Same ISBN",
        )
        self._add_value_groups(
            evidence_by_ids,
            books,
            value=lambda book: (
                _normalise(book.title) + "\x1f" + _normalise(book.author)
                if _normalise(book.title) and _normalise(book.author)
                else ""
            ),
            evidence="Same title and author",
        )
        for ids in self._exact_content_groups(books):
            evidence_by_ids.setdefault(ids, set()).add("Exact file contents")
        for ids in self._equivalent_epub_content_groups(books):
            evidence_by_ids.setdefault(ids, set()).add("Same ebook contents")

        by_id = {book.book_id: book for book in books}
        groups: list[DuplicateGroup] = []
        for ids, evidence in evidence_by_ids.items():
            group_books = tuple(
                by_id[book_id] for book_id in sorted(ids) if book_id in by_id
            )
            if len(group_books) < 2:
                continue
            group_key = self._group_key(group_books)
            ignored = group_key in ignored_keys
            if ignored and not include_intentional:
                continue
            exact = bool(
                {"Exact file contents", "Same ebook contents"} & evidence
            )
            groups.append(
                DuplicateGroup(
                    group_key=group_key,
                    evidence=tuple(sorted(evidence)),
                    confidence="Exact copy" if exact else "Possible editions",
                    books=group_books,
                    ignored=ignored,
                )
            )
        return tuple(
            sorted(
                groups,
                key=lambda group: (
                    not group.exact_copy,
                    -len(group.books),
                    group.books[0].title.casefold(),
                ),
            )
        )

    def mark_intentional(
        self,
        group_key: str,
        *,
        intentional: bool = True,
    ) -> None:
        self.database.set_duplicate_exception(
            group_key,
            intentional=intentional,
        )

    def quarantine_exact_copy(
        self,
        group: DuplicateGroup,
        book_id: int,
    ) -> Path:
        """Move one confirmed exact copy into Twano's recoverable quarantine."""
        if not group.exact_copy:
            raise ValueError(
                "Only files with identical contents can be quarantined."
            )
        if len(group.books) < 2:
            raise ValueError("At least one other exact copy must remain.")
        selected = next(
            (book for book in group.books if book.book_id == int(book_id)),
            None,
        )
        if selected is None:
            raise ValueError("The selected book is not in this duplicate group.")
        source = Path(selected.file_path)
        if not source.is_file():
            raise FileNotFoundError(
                "The selected ebook file is not currently available."
            )
        folder = (
            self.database.database_path.parent
            / "quarantine"
            / (
                datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                + "-"
                + uuid4().hex[:8]
            )
        )
        folder.mkdir(parents=True, exist_ok=False)
        target = folder / source.name
        try:
            shutil.move(str(source), str(target))
            quarantine_id = self.database.record_quarantine_item(
                book_id=selected.book_id,
                original_path=str(source),
                quarantine_path=str(target),
            )
            manifest = {
                "schema_version": 1,
                "quarantine_id": quarantine_id,
                "book_id": selected.book_id,
                "title": selected.title,
                "original_path": str(source),
                "quarantine_path": str(target),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            (folder / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except Exception:
            if target.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(source))
            raise
        return target

    def list_quarantine(self) -> tuple[dict[str, object], ...]:
        return tuple(dict(row) for row in self.database.list_quarantine_items())

    def restore_quarantined(self, quarantine_id: int) -> Path:
        rows = self.database.list_quarantine_items()
        row = next(
            (item for item in rows if int(item["id"]) == int(quarantine_id)),
            None,
        )
        if row is None:
            raise ValueError("That quarantine item is no longer available.")
        source = Path(str(row["quarantine_path"]))
        destination = Path(str(row["original_path"]))
        if not source.is_file():
            raise FileNotFoundError("The quarantined ebook file is missing.")
        if destination.exists():
            raise FileExistsError(
                "A file already exists at the original location."
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(source), str(destination))
            self.database.mark_quarantine_restored(
                int(row["id"]),
                book_id=int(row["book_id"]),
            )
        except Exception:
            if destination.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
            raise
        return destination

    @staticmethod
    def _book(row) -> DuplicateBook:
        return DuplicateBook(
            book_id=int(row["id"]),
            title=str(row["title"] or row["file_name"] or "Untitled"),
            author=str(row["author"] or "Unknown"),
            isbn=str(row["isbn"] or ""),
            file_format=str(row["file_format"] or ""),
            file_size=int(row["file_size"] or 0),
            file_path=str(row["file_path"] or ""),
            cover_path=str(row["cover_path"] or ""),
        )

    @staticmethod
    def _add_value_groups(
        target: dict[frozenset[int], set[str]],
        books: tuple[DuplicateBook, ...],
        *,
        value,
        evidence: str,
    ) -> None:
        buckets: dict[str, set[int]] = {}
        for book in books:
            key = value(book)
            if key:
                buckets.setdefault(key, set()).add(book.book_id)
        for ids in buckets.values():
            if len(ids) > 1:
                target.setdefault(frozenset(ids), set()).add(evidence)

    @staticmethod
    def _exact_content_groups(
        books: tuple[DuplicateBook, ...],
    ) -> tuple[frozenset[int], ...]:
        size_buckets: dict[int, list[DuplicateBook]] = {}
        for book in books:
            if book.file_size > 0:
                size_buckets.setdefault(book.file_size, []).append(book)
        hash_buckets: dict[str, set[int]] = {}
        for candidates in size_buckets.values():
            if len(candidates) < 2:
                continue
            for book in candidates:
                path = Path(book.file_path)
                if not path.is_file():
                    continue
                try:
                    digest = _sha256(path)
                except OSError:
                    continue
                hash_buckets.setdefault(digest, set()).add(book.book_id)
        return tuple(
            frozenset(ids)
            for ids in hash_buckets.values()
            if len(ids) > 1
        )

    @staticmethod
    def _equivalent_epub_content_groups(
        books: tuple[DuplicateBook, ...],
    ) -> tuple[frozenset[int], ...]:
        """Find EPUB copies that differ only by known vendor metadata."""
        candidate_buckets: dict[str, list[DuplicateBook]] = {}
        for book in books:
            if book.file_format.casefold() != "epub":
                continue
            identity = _normalise(book.title) + "\x1f" + _normalise(
                book.author
            )
            if identity.strip("\x1f"):
                candidate_buckets.setdefault(identity, []).append(book)

        groups: list[frozenset[int]] = []
        for candidates in candidate_buckets.values():
            if len(candidates) < 2:
                continue
            digest_buckets: dict[str, set[int]] = {}
            for book in candidates:
                try:
                    digest = _epub_content_digest(Path(book.file_path))
                except (BadZipFile, OSError, ValueError):
                    continue
                digest_buckets.setdefault(digest, set()).add(book.book_id)
            groups.extend(
                frozenset(ids)
                for ids in digest_buckets.values()
                if len(ids) > 1
            )
        return tuple(groups)

    @staticmethod
    def _group_key(books: tuple[DuplicateBook, ...]) -> str:
        payload = "|".join(
            str(book.book_id) for book in sorted(books, key=lambda item: item.book_id)
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _epub_content_digest(path: Path) -> str:
    """Hash an EPUB while excluding harmless Apple catalogue metadata."""
    digest = hashlib.sha256()
    included = 0
    with ZipFile(path) as archive:
        entries = sorted(
            (
                entry
                for entry in archive.infolist()
                if not entry.is_dir()
                and Path(entry.filename).name.casefold()
                != "itunesmetadata.plist"
            ),
            key=lambda entry: entry.filename.replace("\\", "/").casefold(),
        )
        for entry in entries:
            encoded_name = entry.filename.replace("\\", "/").encode(
                "utf-8",
                errors="surrogatepass",
            )
            digest.update(len(encoded_name).to_bytes(4, "big"))
            digest.update(encoded_name)
            with archive.open(entry) as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
            included += 1
    if not included:
        raise ValueError("The EPUB archive contains no readable files.")
    return digest.hexdigest()


def _normalise(value: str) -> str:
    return " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in value.casefold()
        ).split()
    )


def _normalise_isbn(value: str) -> str:
    return "".join(
        character for character in value.upper() if character.isdigit() or character == "X"
    )

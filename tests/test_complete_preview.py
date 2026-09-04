"""Production-preview coverage for the consolidated user-facing workflows."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox

from core.scanner import BookFile
from database.database import DatabaseManager
from main_window import MainWindow
from preferences import (
    AccessibilityPreferences,
    GeneralPreferences,
    MetadataPreferences,
    PreferencesStore,
    ProtectionMode,
)
from services.dashboard_service import DashboardService
from services.duplicate_service import DuplicateService
from services.integration_service import IntegrationService
from services.library_health_service import LibraryHealthService
from services.library_service import LibraryService
from services.metadata_studio_service import (
    MetadataCandidate,
    MetadataStudioService,
)
from services.plugin_service import PluginService
from services.protection_models import OperationStatus, PlanConfirmation
from services.protection_service import (
    ProtectedExecutionError,
    ProtectionService,
)
from services.scan_service import ScanService
from ui.library_health_page import LibraryHealthPage, VerifyLibraryDialog
from ui.duplicate_page import DuplicatePage
from ui.plugin_page import PluginPage
from ui.sidebar import PRIMARY_NAVIGATION
import services.metadata_studio_service as metadata_module


def _book(path: Path) -> BookFile:
    return BookFile(
        name=path.stem,
        extension=path.suffix.removeprefix(".").upper(),
        size_bytes=path.stat().st_size,
        path=path,
    )


def test_complete_preferences_round_trip(tmp_path: Path) -> None:
    store = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    store.save_metadata_preferences(
        MetadataPreferences(False, 90, True, False)
    )
    store.save_accessibility_preferences(
        AccessibilityPreferences(125, True, True)
    )
    store.save_general_preferences(GeneralPreferences(True, False))
    store.sync()

    assert store.load_metadata_preferences() == MetadataPreferences(
        False,
        90,
        True,
        False,
    )
    assert store.load_accessibility_preferences() == (
        AccessibilityPreferences(125, True, True)
    )
    assert store.load_general_preferences() == GeneralPreferences(True, False)


def test_open_library_search_maps_explainable_cover_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(
                {
                    "docs": [
                        {
                            "key": "/works/OL1W",
                            "title": "The Hobbit",
                            "author_name": ["J. R. R. Tolkien"],
                            "isbn": ["9780261103344"],
                            "publisher": ["HarperCollins"],
                            "language": ["eng"],
                            "first_publish_year": 1937,
                            "cover_i": 12345,
                            "first_sentence": [
                                "A reluctant hobbit begins an unexpected journey."
                            ],
                        }
                    ]
                }
            ).encode()

    monkeypatch.setattr(
        metadata_module,
        "urlopen",
        lambda *_args, **_kwargs: Response(),
    )
    service = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db")
    )
    candidates = service.search_candidates(
        title="The Hobbit",
        author="J. R. R. Tolkien",
        isbn="9780261103344",
    )

    assert len(candidates) == 1
    assert candidates[0].confidence == 100
    assert candidates[0].confidence_reason == "Exact ISBN match"
    assert "/12345-L.jpg" in candidates[0].cover_url
    assert candidates[0].description == (
        "A reluctant hobbit begins an unexpected journey."
    )

    def unexpected_network(*_args, **_kwargs):
        raise AssertionError("Persistent cache was not used")

    monkeypatch.setattr(metadata_module, "urlopen", unexpected_network)
    cached_service = MetadataStudioService(
        DatabaseManager(tmp_path / "library.db")
    )
    assert cached_service.search_candidates(
        title="The Hobbit",
        author="J. R. R. Tolkien",
        isbn="9780261103344",
        cache_days=30,
    ) == candidates
    cache_payload = json.loads(
        (tmp_path / "metadata-cache.json").read_text(encoding="utf-8")
    )
    assert cache_payload["_schema_version"] == 7


def test_metadata_update_uses_plan_verified_backup_and_atomic_apply(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    path = folder / "Example.epub"
    path.write_bytes(b"example")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(path)])
    book_id = int(database.get_books()[0]["id"])
    protection = ProtectionService(database)

    plan = protection.build_metadata_update_plan(
        book_id,
        {
            "title": "Reviewed Example",
            "author": "A. Reader",
            "publisher": "Twano Press",
            "cover_path": str(tmp_path / "cover.jpg"),
            "provider_rating": 4.4,
            "rating_count": 1250,
            "rating_source": "Google Books",
        },
    )
    preview = protection.record_change_plan(plan)
    approved = protection.approve_change_plan(
        preview.operation_id,
        PlanConfirmation(
            plan_token=plan.plan_token,
            approved=True,
            confirmer="test",
        ),
        current_basis_token=protection.current_basis_token(preview),
    )
    applied = protection.apply_approved_operation(
        approved.operation_id,
        protection.build_policy(tmp_path / "backups", 0),
        ProtectionMode.STANDARD,
    )

    assert applied.status == OperationStatus.APPLIED
    assert Path(applied.backup_identity).is_file()
    updated = database.get_book_by_id(book_id)
    assert updated["title"] == "Reviewed Example"
    assert updated["author"] == "A. Reader"
    assert updated["provider_rating"] == 4.4
    assert updated["rating_count"] == 1250
    assert updated["rating_source"] == "Google Books"
    assert updated["metadata_status"] == "external"


def test_metadata_apply_organises_series_in_reading_order(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    path = folder / "messy 2.epub"
    path.write_bytes(b"hexed")
    cover = tmp_path / "hexed-cover.jpg"
    cover.write_bytes(b"cover")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(path)])
    book_id = int(database.get_books()[0]["id"])
    protection = ProtectionService(database)

    plan = protection.build_metadata_update_plan(
        book_id,
        {
            "title": "Hexed",
            "author": "Kevin Hearne",
            "description": "A reviewed description.",
            "series": "Iron Druid Chronicles",
            "series_number": 2,
            "cover_path": str(cover),
        },
        organise_file=True,
    )
    expected = (
        folder
        / "-=Series=-"
        / "Iron Druid Chronicles"
        / "02 - Hexed - Kevin Hearne.epub"
    ).resolve()
    assert plan.file_changes[0].before_summary == str(path.resolve())
    assert plan.file_changes[0].after_summary == str(expected)

    preview = protection.record_change_plan(plan)
    approved = protection.approve_change_plan(
        preview.operation_id,
        PlanConfirmation(
            plan_token=plan.plan_token,
            approved=True,
            confirmer="test",
        ),
        current_basis_token=protection.current_basis_token(preview),
    )
    applied = protection.apply_approved_operation(
        approved.operation_id,
        protection.build_policy(tmp_path / "backups", 0),
        ProtectionMode.STANDARD,
    )

    assert applied.status == OperationStatus.APPLIED
    assert expected.read_bytes() == b"hexed"
    assert not path.exists()
    updated = database.get_book_by_id(book_id)
    assert Path(updated["file_path"]) == expected
    assert updated["file_name"] == expected.name
    assert updated["series_number"] == 2
    assert updated["metadata_workflow_complete"] == 1
    assert MetadataStudioService(database).list_books() == ()

    database.set_metadata_workflow_complete(book_id, False)
    studio = MetadataStudioService(database)
    assert studio.list_books() == ()
    assert database.get_book_by_id(book_id)["metadata_workflow_complete"] == 1

    expected.write_bytes(b"a changed ebook")
    database.save_scan_results(folder, [_book(expected)])

    refreshed = database.get_book_by_id(book_id)
    assert refreshed["metadata_workflow_complete"] == -1
    assert len(MetadataStudioService(database).list_books()) == 1


def test_metadata_preview_organises_unnumbered_collection_without_blocking(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    path = folder / "ramen.epub"
    path.write_bytes(b"ramen")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(path)])
    book_id = int(database.get_books()[0]["id"])

    protection = ProtectionService(database)
    reviewed = {
        "title": "101 Things to Do with Ramen Noodles",
        "author": "Toni Patrick",
        "series": "101 Things To Do With",
        "series_number": "",
    }
    plan = protection.build_metadata_update_plan(
        book_id,
        reviewed,
        organise_file=True,
    )

    expected = (
        folder
        / "-=Series=-"
        / "101 Things To Do With"
        / "101 Things to Do with Ramen Noodles - Toni Patrick.epub"
    ).resolve()
    assert plan.file_changes[0].after_summary == str(expected)
    assert protection.preview_metadata_destination(book_id, reviewed) == expected
    assert (
        MetadataStudioService(database).proposed_file_path(
            book_id,
            reviewed,
            organise_file=True,
        )
        == expected
    )
    assert path.exists()
    assert not expected.exists()


def test_metadata_preview_organises_nested_series_group(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    path = folder / "pawn.epub"
    path.write_bytes(b"pawn")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(path)])
    book_id = int(database.get_books()[0]["id"])

    protection = ProtectionService(database)
    reviewed = {
        "title": "Pawn of Prophecy",
        "author": "David Eddings",
        "series": "The Belgariad",
        "series_number": 1,
        "series_group": "Belgariad Universe",
        "series_group_number": 1,
    }

    expected = (
        folder
        / "-=Series=-"
        / "Belgariad Universe"
        / "The Belgariad"
        / "01 - Pawn of Prophecy - David Eddings.epub"
    ).resolve()
    assert protection.preview_metadata_destination(book_id, reviewed) == expected

    plan = protection.build_metadata_update_plan(
        book_id,
        reviewed,
        organise_file=True,
    )
    assert plan.file_changes[0].after_summary == str(expected)


def test_metadata_preview_canonicalises_ring_of_fire_provider_alias(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    path = folder / "eastern-front.epub"
    path.write_bytes(b"book")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(path)])
    book_id = int(database.get_books()[0]["id"])

    reviewed = {
        "title": "1635: The Eastern Front",
        "author": "Eric Flint",
        "series": "Ring of Fire Main Line Novels",
        "series_number": 4,
    }
    protection = ProtectionService(database)
    plan = protection.build_metadata_update_plan(
        book_id,
        reviewed,
        organise_file=True,
    )

    expected = (
        folder
        / "-=Series=-"
        / "Ring of Fire"
        / "10 - 1635- The Eastern Front - Eric Flint.epub"
    ).resolve()
    assert plan.file_changes[0].after_summary == str(expected)
    changed = json.loads(plan.database_changes[0].after_summary)
    assert changed["series"] == "Ring of Fire"
    assert changed["series_number"] == 10.0


def test_metadata_apply_organises_standalone_directly_under_author(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    path = folder / "unknown.epub"
    path.write_bytes(b"standalone")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(path)])
    book_id = int(database.get_books()[0]["id"])
    protection = ProtectionService(database)

    plan = protection.build_metadata_update_plan(
        book_id,
        {
            "title": "The Hermit Next Door",
            "author": "Kevin Hearne",
        },
        organise_file=True,
    )

    assert plan.file_changes[0].after_summary == str(
        (
            folder
            / "Kevin Hearne"
            / "The Hermit Next Door - Kevin Hearne.epub"
        ).resolve()
    )


def test_metadata_organisation_refuses_collision(tmp_path: Path) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    source = folder / "unknown.epub"
    source.write_bytes(b"source")
    collision = folder / "Kevin Hearne" / "Hounded - Kevin Hearne.epub"
    collision.parent.mkdir()
    collision.write_bytes(b"existing")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(source)])
    book_id = int(database.get_books()[0]["id"])

    with pytest.raises(ValueError, match="already exists"):
        ProtectionService(database).build_metadata_update_plan(
            book_id,
            {"title": "Hounded", "author": "Kevin Hearne"},
            organise_file=True,
        )

    assert source.read_bytes() == b"source"
    assert collision.read_bytes() == b"existing"


def test_metadata_organisation_keeps_distinct_catalogued_isbn_editions(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    source = folder / "unknown.epub"
    source.write_bytes(b"second edition")
    collision = (
        folder
        / "-=Series=-"
        / "Space Odyssey"
        / "03 - 2061- Odyssey Three - Arthur C. Clarke.epub"
    )
    collision.parent.mkdir(parents=True)
    collision.write_bytes(b"first edition")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(source), _book(collision)])
    database.update_book_metadata(
        collision,
        title="2061: Odyssey Three",
        author="Arthur C. Clarke",
        isbn="9780586203194",
        publisher="Grafton",
        language="en",
        published_date="1988",
        metadata_status="external",
    )
    book_id = int(database.get_book_by_file_path(source)["id"])
    reviewed = {
        "title": "2061: Odyssey Three",
        "author": "Arthur C. Clarke",
        "isbn": "9780345358790",
        "series": "Space Odyssey",
        "series_number": 3,
    }
    protection = ProtectionService(database)

    destination = protection.preview_metadata_destination(book_id, reviewed)
    plan = protection.build_metadata_update_plan(
        book_id,
        reviewed,
        organise_file=True,
    )

    expected = collision.with_name(
        "03 - 2061- Odyssey Three - Arthur C. Clarke "
        "[ISBN 9780345358790].epub"
    ).resolve()
    assert destination == expected
    assert Path(plan.file_changes[0].after_summary) == expected
    assert source.read_bytes() == b"second edition"
    assert collision.read_bytes() == b"first edition"


def test_metadata_organisation_keeps_existing_isbn_qualified_filename(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    collision = (
        folder
        / "-=Series=-"
        / "Space Odyssey"
        / "03 - 2061- Odyssey Three - Arthur C. Clarke.epub"
    )
    collision.parent.mkdir(parents=True)
    collision.write_bytes(b"first edition")
    source = collision.with_name(
        "03 - 2061- Odyssey Three - Arthur C. Clarke "
        "[ISBN 9780345358790].epub"
    )
    source.write_bytes(b"second edition")
    cover = folder / "odyssey-cover.jpg"
    cover.write_bytes(b"cover")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(collision), _book(source)])
    database.update_book_metadata(
        collision,
        title="2061: Odyssey Three",
        author="Arthur C. Clarke",
        isbn="9780586203194",
        publisher="Grafton",
        language="en",
        published_date="1988",
        metadata_status="external",
    )
    database.update_book_metadata(
        source,
        title="2061: Odyssey Three",
        author="Arthur C. Clarke",
        isbn="9780345358790",
        publisher="Del Rey",
        language="en",
        published_date="1989",
        metadata_status="external",
    )
    book_id = int(database.get_book_by_file_path(source)["id"])
    with database.connection() as connection:
        connection.execute(
            """
            UPDATE books
            SET series = ?, series_number = ?, cover_path = ?, description = ?
            WHERE id = ?
            """,
            (
                "Space Odyssey",
                3,
                str(cover),
                "A reviewed description.",
                book_id,
            ),
        )
    reviewed = {
        "title": "2061: Odyssey Three",
        "author": "Arthur C. Clarke",
        "isbn": "9780345358790",
        "publisher": "Del Rey",
        "language": "en",
        "published_date": "1989-04-13",
        "series": "Space Odyssey",
        "series_number": 3,
    }
    protection = ProtectionService(database)

    destination = protection.preview_metadata_destination(book_id, reviewed)
    plan = protection.build_metadata_update_plan(
        book_id,
        reviewed,
        organise_file=True,
    )

    assert destination == source.resolve()
    assert plan.file_changes == ()
    assert source.read_bytes() == b"second edition"
    assert collision.read_bytes() == b"first edition"

    database.set_metadata_workflow_complete(book_id, False)
    unfinished = MetadataStudioService(database).list_books()
    assert all(record.book_id != book_id for record in unfinished)
    assert database.get_book_by_id(book_id)["metadata_workflow_complete"] == 1


def test_metadata_organisation_restores_file_when_catalogue_apply_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    source = folder / "unknown.epub"
    source.write_bytes(b"recover me")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(source)])
    book_id = int(database.get_books()[0]["id"])
    protection = ProtectionService(database)
    plan = protection.build_metadata_update_plan(
        book_id,
        {"title": "Hounded", "author": "Kevin Hearne"},
        organise_file=True,
    )
    destination = Path(plan.file_changes[0].after_summary)
    preview = protection.record_change_plan(plan)
    approved = protection.approve_change_plan(
        preview.operation_id,
        PlanConfirmation(
            plan_token=plan.plan_token,
            approved=True,
            confirmer="test",
        ),
        current_basis_token=protection.current_basis_token(preview),
    )

    monkeypatch.setattr(
        database,
        "apply_metadata_update_operation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("forced database failure")
        ),
    )
    with pytest.raises(ProtectedExecutionError):
        protection.apply_approved_operation(
            approved.operation_id,
            protection.build_policy(tmp_path / "backups", 0),
            ProtectionMode.STANDARD,
        )

    assert source.read_bytes() == b"recover me"
    assert not destination.exists()
    assert database.get_book_by_id(book_id)["file_path"] == str(
        source.resolve()
    )


def test_exact_duplicate_quarantine_is_recoverable(tmp_path: Path) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    first = folder / "Copy One.epub"
    second = folder / "Copy Two.epub"
    first.write_bytes(b"identical ebook")
    second.write_bytes(b"identical ebook")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(first), _book(second)])
    service = DuplicateService(database)

    group = next(group for group in service.find_groups() if group.exact_copy)
    selected_id = next(
        book.book_id for book in group.books if book.file_path == str(second.resolve())
    )
    quarantine_path = service.quarantine_exact_copy(group, selected_id)

    assert quarantine_path.is_file()
    assert not second.exists()
    quarantine = service.list_quarantine()
    restored = service.restore_quarantined(int(quarantine[0]["id"]))
    assert restored == second.resolve()
    assert second.is_file()
    assert database.count_books() == 2


def test_epubs_differing_only_by_itunes_metadata_are_confirmed_copies(
    tmp_path: Path,
) -> None:
    _application = QApplication.instance() or QApplication([])
    folder = tmp_path / "books"
    folder.mkdir()
    clean = folder / "Clean Copy.epub"
    apple = folder / "Apple Copy.epub"
    shared_entries = {
        "mimetype": b"application/epub+zip",
        "META-INF/container.xml": b"<container />",
        "EPUB/chapter.xhtml": b"<p>The same readable book.</p>",
    }
    with ZipFile(clean, "w") as archive:
        for name, content in shared_entries.items():
            archive.writestr(name, content)
    with ZipFile(apple, "w") as archive:
        for name, content in shared_entries.items():
            archive.writestr(name, content)
        archive.writestr("iTunesMetadata.plist", b"vendor metadata")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(clean), _book(apple)])
    for path in (clean, apple):
        database.update_book_metadata(
            path,
            title="4.50 From Paddington",
            author="Agatha Christie",
            isbn=None,
            publisher=None,
            language="en",
            published_date=None,
            metadata_status="embedded",
        )

    service = DuplicateService(database)
    group = next(
        group
        for group in service.find_groups()
        if "Same ebook contents" in group.evidence
    )
    page = DuplicatePage(service)
    page._scan_completed((group,))

    assert group.exact_copy
    assert "Exact file contents" not in group.evidence
    assert page.quarantine_button.isEnabled()
    page.close()


def test_duplicate_page_rebinds_next_group_after_quarantine(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    folder = tmp_path / "books"
    folder.mkdir()
    paths = (
        folder / "Alpha One.epub",
        folder / "Alpha Two.epub",
        folder / "Beta One.epub",
        folder / "Beta Two.epub",
    )
    paths[0].write_bytes(b"first exact group")
    paths[1].write_bytes(b"first exact group")
    paths[2].write_bytes(b"second exact group with another size")
    paths[3].write_bytes(b"second exact group with another size")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(path) for path in paths])
    page = DuplicatePage(DuplicateService(database))
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    monkeypatch.setattr(
        page,
        "refresh",
        lambda: page._scan_completed(page.service.find_groups()),
    )
    page.refresh()
    assert page.group_table.rowCount() == 2

    page._quarantine()

    assert page.group_table.rowCount() == 1
    displayed_group = page.group_table.item(0, 0).data(
        Qt.ItemDataRole.UserRole
    )
    assert page.current_group == displayed_group
    assert page._selected_book_id() in {
        book.book_id for book in displayed_group.books
    }
    assert page.quarantine_button.isEnabled()

    page._quarantine()

    assert page.group_table.rowCount() == 0
    assert page.current_group is None
    assert page.quarantine_table.rowCount() == 2
    page.close()


def test_library_health_is_actionable_and_deterministic(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    path = folder / "Needs Help.epub"
    path.write_bytes(b"book")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(path)])
    report = LibraryHealthService(database).get_report()

    issue_ids = {issue.issue_id for issue in report.issues}
    assert report.total_books == 1
    assert {"metadata", "covers"}.issubset(issue_ids)
    assert all(issue.destination for issue in report.issues)
    assert all(issue.preview_items for issue in report.issues)
    assert report.score < 100

    book_id = int(database.get_books()[0]["id"])
    database.update_book_metadata(
        path,
        title="Reviewed title",
        author="Reviewed author",
        isbn=None,
        publisher=None,
        language=None,
        published_date=None,
        metadata_status="external",
    )
    with database.connection() as connection:
        connection.execute(
            "UPDATE books SET description = ? WHERE id = ?",
            ("A reviewed description.", book_id),
        )
    database.set_metadata_workflow_complete(book_id, True)
    reviewed_report = LibraryHealthService(database).get_report()
    assert "metadata" not in {
        issue.issue_id for issue in reviewed_report.issues
    }


def test_library_health_cards_show_bounded_issue_previews(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "books"
    folder.mkdir()
    paths = []
    for index in range(6):
        path = folder / f"Missing Cover {index + 1}.epub"
        path.write_bytes(b"book")
        paths.append(path)
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(folder, [_book(path) for path in paths])
    service = LibraryHealthService(database)

    report = service.get_report()
    cover_issue = next(
        issue for issue in report.issues if issue.issue_id == "covers"
    )
    assert cover_issue.count == 6
    assert len(cover_issue.preview_items) == 4
    assert cover_issue.preview_items[0].startswith("Missing Cover 1")

    application = QApplication.instance() or QApplication([])
    page = LibraryHealthPage(service, LibraryService(database))
    preview_texts = [
        label.text()
        for label in page.findChildren(QLabel, "healthIssuePreview")
    ]
    assert any("Missing Cover 1" in text for text in preview_texts)
    assert any("and 2 more" in text for text in preview_texts)
    page.deleteLater()
    application.processEvents()


def test_verify_library_dialog_lists_entries_and_reports_checked_ids(
    tmp_path: Path,
) -> None:
    from services.library_service import MissingFileEntry

    application = QApplication.instance() or QApplication([])
    entries = (
        MissingFileEntry(
            book_id=1,
            title="Gone Book",
            author="Some Author",
            file_path=str(tmp_path / "gone.epub"),
        ),
        MissingFileEntry(
            book_id=2,
            title="Also Gone",
            author="",
            file_path=str(tmp_path / "also-gone.epub"),
        ),
    )

    dialog = VerifyLibraryDialog(entries)
    assert dialog.list_widget.count() == 2
    assert dialog.selected_book_ids() == ()

    dialog.list_widget.item(0).setCheckState(Qt.CheckState.Checked)
    assert dialog.selected_book_ids() == (1,)

    dialog.deleteLater()
    application.processEvents()


def test_verify_library_removes_checked_books_and_emits_catalogue_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watched = tmp_path / "Watched"
    watched.mkdir()
    gone = watched / "Gone Book.epub"
    gone.write_bytes(b"data")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(watched, [_book(gone)])
    book_id = int(database.get_books()[0]["id"])
    gone.unlink()

    application = QApplication.instance() or QApplication([])
    library_service = LibraryService(database)
    page = LibraryHealthPage(
        LibraryHealthService(database), library_service
    )

    def auto_check_and_accept(self) -> int:
        for row in range(self.list_widget.count()):
            self.list_widget.item(row).setCheckState(
                Qt.CheckState.Checked
            )
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(VerifyLibraryDialog, "exec", auto_check_and_accept)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    changed_signals: list[bool] = []
    page.catalogue_changed.connect(lambda: changed_signals.append(True))

    page._verify_library()

    assert database.get_book_by_id(book_id) is None
    assert changed_signals == [True]
    page.deleteLater()
    application.processEvents()


def test_verify_library_shows_confirmation_when_nothing_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watched = tmp_path / "Watched"
    watched.mkdir()
    present = watched / "Present Book.epub"
    present.write_bytes(b"data")
    database = DatabaseManager(tmp_path / "library.db")
    database.save_scan_results(watched, [_book(present)])

    application = QApplication.instance() or QApplication([])
    library_service = LibraryService(database)
    page = LibraryHealthPage(
        LibraryHealthService(database), library_service
    )

    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, text: messages.append(text),
    )

    page._verify_library()

    assert messages and "found" in messages[0]
    page.deleteLater()
    application.processEvents()


def test_plugin_catalog_installs_only_approved_builtins(
    tmp_path: Path,
) -> None:
    service = PluginService(
        tmp_path / "plugins",
        tmp_path / "state.json",
    )
    available = next(
        plugin
        for plugin in service.list_plugins()
        if plugin.plugin_id == "open_library_metadata"
    )
    assert not available.installed

    installed = service.install_builtin("open_library_metadata")
    assert installed.installed and not installed.enabled

    guarded_metadata = MetadataStudioService(
        DatabaseManager(tmp_path / "catalogue.db"),
        plugin_service=service,
    )
    try:
        guarded_metadata.search_candidates(title="The Hobbit")
    except Exception as error:
        assert "Open Library Metadata & Covers is not enabled" in str(error)
    else:
        raise AssertionError("Disabled metadata provider was used")

    unapproved = tmp_path / "unknown.twano-plugin"
    unapproved.write_bytes(b"not approved")
    try:
        service.install_package(unapproved, approved_hashes={})
    except ValueError as error:
        assert "approved-source catalogue" in str(error)
    else:
        raise AssertionError("Unapproved plugin package was accepted")


def test_plugin_page_actions_preserve_selection_and_show_active_status(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    service = PluginService(
        tmp_path / "plugins",
        tmp_path / "state.json",
    )
    page = PluginPage(service, IntegrationService())
    page.show()
    application.processEvents()

    row = next(
        index
        for index, plugin in enumerate(page.plugins)
        if plugin.plugin_id == "open_library_metadata"
    )
    page.plugin_table.selectRow(row)
    application.processEvents()
    assert page.install_button.isEnabled()
    assert not page.enable_button.isEnabled()
    assert not page.disable_button.isEnabled()

    page.install_button.click()
    application.processEvents()
    assert page._selected_plugin().plugin_id == "open_library_metadata"
    assert page.plugin_table.item(row, 4).text() == "Disabled"
    assert "installed successfully" in page.status_label.text()
    assert not page.install_button.isEnabled()
    assert page.enable_button.isEnabled()
    assert not page.disable_button.isEnabled()

    page.enable_button.click()
    application.processEvents()
    assert page.plugin_table.item(row, 4).text() == "Active"
    assert "now Active" in page.status_label.text()
    assert not page.enable_button.isEnabled()
    assert page.disable_button.isEnabled()

    page.disable_button.click()
    application.processEvents()
    assert page.plugin_table.item(row, 4).text() == "Disabled"
    assert "now Disabled" in page.status_label.text()
    assert page.enable_button.isEnabled()
    assert not page.disable_button.isEnabled()
    page.close()
    application.processEvents()


def test_calibre_and_network_checks_are_non_destructive(tmp_path: Path) -> None:
    calibre_library = tmp_path / "Calibre Library"
    calibre_library.mkdir()
    (calibre_library / "metadata.db").write_bytes(b"read-only marker")
    service = IntegrationService()

    result = service.inspect_calibre_library(calibre_library)
    assert result.valid
    assert "will not write directly" in result.message
    assert service.network_path_shape(r"\\NAS\Books") == (
        True,
        "Windows network (UNC) location",
    )


def test_main_window_has_calm_navigation_and_global_status_footer(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    database_path = tmp_path / "window.db"
    database = DatabaseManager(database_path)
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    window = MainWindow(
        library_service=LibraryService(database),
        dashboard_service=DashboardService(database),
        preferences=preferences,
        scan_service_factory=lambda: ScanService(
            DatabaseManager(database_path)
        ),
        protection_service_factory=lambda: ProtectionService(
            DatabaseManager(database_path)
        ),
    )
    window.resize(900, 600)
    window.show()
    application.processEvents()

    assert window.sidebar.page_ids == (
        "home",
        "library",
        "library_health",
        "scan",
        "metadata",
        "plugins",
        "settings",
        "user_guide",
        "whats_new",
        "about",
    )
    assert next(
        entry.label
        for entry in PRIMARY_NAVIGATION
        if entry.page_id == "metadata"
    ) == "Metadata & Covers"
    assert window.status_update_button.isVisible()
    assert window.status_book_count_label.text() == "0 books"
    assert window.metadata_page.book_combo.count() == 0
    assert "empty" in window.metadata_page.status_label.text().casefold()
    assert window.metadata_page.lookup_button.text() == (
        "Find Metadata && Covers"
    )
    assert window.metadata_page.lookup_button.accessibleName() == (
        "Find Metadata & Covers"
    )
    assert window.metadata_page.find_covers_button.text() == (
        "Find Covers"
    )
    assert (
        window.metadata_page.provider_combo.objectName()
        == "metadataProviderSelector"
    )
    assert window.metadata_page.provider_combo.currentData() == ""
    assert (
        window.metadata_page.provider_combo.currentText()
        == "All active providers"
    )
    assert not hasattr(window.metadata_page, "tabs")
    assert not hasattr(window.metadata_page, "cover_search_button")
    assert window.metadata_page.cover_result_combo.parent() is not None

    library = tmp_path / "Wizard Library"
    library.mkdir()
    ebook = library / "Wizard Squared - K. E. Mills.epub"
    ebook.write_bytes(b"test ebook")
    database.save_scan_results(library, [_book(ebook)])
    database.update_book_metadata(
        ebook,
        title="03 Wizard Squared",
        author="Mills, K.E.",
        isbn=None,
        publisher=None,
        language=None,
        published_date=None,
        metadata_status="embedded",
    )
    window.metadata_page.refresh()

    metadata_candidate = MetadataCandidate(
        title="Wizard Squared",
        author="K. E. Mills",
        isbn="9780316035439",
        publisher="Orbit",
        language="en",
        published_date="2010",
        cover_id=None,
        work_key="open-library-wizard",
        confidence=95,
        confidence_reason="Exact title and author match",
        provider_name="Open Library",
    )
    unrelated_cover = MetadataCandidate(
        title="K-A-E 29th Secret",
        author="Unknown",
        isbn="",
        publisher="",
        language="en",
        published_date="",
        cover_id=None,
        work_key="comic-vine-unrelated",
        confidence=60,
        confidence_reason="Provider result",
        provider_name="Comic Vine",
        remote_cover_url="https://comicvine.gamespot.com/unrelated.jpg",
    )
    candidate = MetadataCandidate(
        title="Wizard Squared",
        author="K. E. Mills",
        isbn="9780316035439",
        publisher="Orbit",
        language="en",
        published_date="2010",
        cover_id=None,
        work_key="google-wizard",
        confidence=90,
        confidence_reason="Exact title and author match",
        provider_name="Google Books",
        remote_cover_url="https://books.google.com/wizard.jpg",
    )
    window._show_page("metadata")
    application.processEvents()
    assert abs(
        window.metadata_page.find_covers_button.geometry().center().y()
        - window.metadata_page.cover_result_combo.geometry().center().y()
    ) <= 5
    assert (
        window.metadata_page.download_cover_button.geometry().top()
        > window.metadata_page.find_covers_button.geometry().top()
    )
    window.metadata_page._populate_fields(
        {"title": "Reviewed title", "author": "Reviewed author"}
    )
    window.metadata_page._cover_lookup_completed((candidate,))
    assert window.metadata_page.field_editors["title"].text() == (
        "Reviewed title"
    )
    assert window.metadata_page.field_editors["author"].text() == (
        "Reviewed author"
    )
    assert window.metadata_page.cover_result_combo.count() == 1
    assert "metadata was not changed" in (
        window.metadata_page.status_label.text()
    )
    window.metadata_page._lookup_completed(
        (metadata_candidate, unrelated_cover, candidate)
    )
    preview_path = tmp_path / "wizard-preview.png"
    preview_pixmap = QPixmap(60, 90)
    preview_pixmap.fill(QColor("#315f88"))
    assert preview_pixmap.save(str(preview_path))
    window.metadata_page._cover_preview_downloaded(str(preview_path))
    application.processEvents()

    assert window.metadata_page.results_list.count() == 3
    assert window.metadata_page.cover_result_combo.count() == 1
    assert window.metadata_page.cover_result_combo.currentData() == candidate
    assert window.metadata_page.pending_cover_candidate is None
    assert "Showing Google Books" in (
        window.metadata_page.status_label.text()
    )
    assert window.metadata_page.download_cover_button.isEnabled()
    assert window.metadata_page.download_cover_button.text() == "Use Cover"
    assert window.metadata_page.cover_preview.text() == ""
    assert not window.metadata_page.cover_preview.pixmap().isNull()
    assert window.metadata_page.cover_preview.width() >= 64
    QTest.mouseClick(
        window.metadata_page.cover_preview,
        Qt.MouseButton.LeftButton,
    )
    application.processEvents()
    assert window.metadata_page.cover_viewer is not None
    assert window.metadata_page.cover_viewer.isVisible()
    assert (
        window.metadata_page.cover_viewer.image_label.pixmap().height()
        > preview_pixmap.height()
    )
    window.metadata_page.cover_viewer.close()
    application.processEvents()
    cover_button = window.metadata_page.download_cover_button
    assert cover_button.width() >= (
        cover_button.fontMetrics().horizontalAdvance(cover_button.text()) + 24
    )
    assert cover_button.geometry().bottom() <= (
        cover_button.parentWidget().contentsRect().bottom()
    )
    cover_preview = window.metadata_page.cover_preview
    assert cover_preview.geometry().bottom() <= (
        cover_preview.parentWidget().contentsRect().bottom()
    )
    window.resize(1600, 900)
    application.processEvents()
    results_bottom = window.metadata_page.results_list.mapTo(
        window.metadata_page,
        window.metadata_page.results_list.rect().bottomLeft(),
    ).y()
    title_top = window.metadata_page.field_editors["title"].mapTo(
        window.metadata_page,
        window.metadata_page.field_editors["title"].rect().topLeft(),
    ).y()
    assert 0 <= title_top - results_bottom <= 36
    window.metadata_page.description_edit.setPlainText(
        "A long description should be readable without being trapped in a "
        "two-line field. It may contain several wrapped sentences about the "
        "book, its setting, its characters, and the events that begin the "
        "story. The editor should grow until this text is comfortably shown."
    )
    application.processEvents()
    assert window.metadata_page.description_edit.height() > 58
    assert window.metadata_page.description_edit.height() <= 200
    assert window.metadata_page.cover_preview.size().width() == 156
    assert window.metadata_page.cover_preview.size().height() == 200
    assert window.metadata_page.cover_preview.pixmap().height() >= 188
    assert window.metadata_page.cover_preview.geometry().bottom() <= (
        window.metadata_page.cover_preview.parentWidget()
        .contentsRect()
        .bottom()
    )

    alternate_cover = MetadataCandidate(
        title="Wizard Squared",
        author="K. E. Mills",
        isbn="9780316035439",
        publisher="Orbit",
        language="en",
        published_date="2010",
        cover_id=None,
        work_key="hardcover-wizard",
        confidence=88,
        confidence_reason="Exact title and author match",
        provider_name="Hardcover",
        remote_cover_url="https://hardcover.app/wizard.jpg",
    )
    window.metadata_page._lookup_completed((candidate, alternate_cover))
    window.metadata_page._cover_preview_failed(
        "Google Books returned no usable cover."
    )

    assert window.metadata_page.cover_result_combo.count() == 1
    assert (
        window.metadata_page.cover_result_combo.currentData()
        == alternate_cover
    )
    assert window.metadata_page.pending_cover_candidate == alternate_cover
    assert "unavailable option was removed" in (
        window.metadata_page.status_label.text()
    )

    window.metadata_page._cover_preview_failed(
        "Hardcover returned no usable cover."
    )

    assert window.metadata_page.cover_result_combo.count() == 0
    assert window.metadata_page.pending_cover_candidate is None
    assert window.metadata_page.cover_preview.text() == "No cover\nfound"
    assert window.metadata_page.pending_cover_fallback
    assert "Checking every other active cover provider" in (
        window.metadata_page.status_label.text()
    )

    window.metadata_page.pending_cover_fallback = False
    window.metadata_page.cover_fallback_attempted = True
    window.metadata_page._cover_preview_failed(
        "The broader cover search returned no usable cover."
    )
    assert not window.metadata_page.pending_cover_fallback
    assert "No usable online cover was found" in (
        window.metadata_page.status_label.text()
    )

    window.metadata_page._lookup_completed((candidate, alternate_cover))
    window.metadata_page._cover_preview_downloaded(str(preview_path))

    assert window.metadata_page.pending_cover_candidate is None
    assert (
        candidate.cover_url
        in window.metadata_page.validated_cover_paths
    )
    assert window.metadata_page.cover_result_combo.count() == 2
    assert "applied with the reviewed metadata" in (
        window.metadata_page.status_label.text()
    )
    assert window.metadata_page.cover_path_edit.text() == str(preview_path)
    assert window.metadata_page.field_checks["cover_path"].isChecked()

    window.metadata_page._lookup_completed((metadata_candidate,))

    assert window.metadata_page.cover_path_edit.text() == str(preview_path)
    assert window.metadata_page.field_checks["cover_path"].isChecked()
    assert window.metadata_page.cover_result_combo.count() == 1
    assert not window.metadata_page.cover_preview.pixmap().isNull()
    assert "kept the cover already selected" in (
        window.metadata_page.status_label.text()
    )
    window.close()
    application.processEvents()

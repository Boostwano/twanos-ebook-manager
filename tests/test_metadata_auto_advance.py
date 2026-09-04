"""Metadata review should continue with the next actionable book."""

from dataclasses import replace
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from preferences import PreferencesStore
from services.library_service import LibraryRecord
from services.metadata_studio_service import (
    MetadataCandidate,
    ProviderSearchReport,
)
from ui.metadata_studio import MetadataStudioPage
from workers.metadata_lookup_worker import MetadataBatchLookupWorker


def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = monotonic() + timeout
    application = QApplication.instance()
    while monotonic() < deadline:
        application.processEvents()
        if predicate():
            return
        sleep(0.01)
    raise AssertionError("Timed out waiting for metadata worker")


def _record(
    book_id: int,
    title: str,
    issue_count: int,
) -> LibraryRecord:
    return LibraryRecord(
        title=title,
        author="A. Reader",
        isbn="9780000000000",
        publisher="Twano Press",
        published_date="2026",
        language="en",
        file_format="EPUB",
        file_size=100,
        metadata_status="external",
        file_path=f"C:/Books/{title}.epub",
        book_id=book_id,
        metadata_issues=(
            ("Missing cover",) if issue_count else ()
        ),
        metadata_issue_count=issue_count,
    )


class _BookListService:
    def __init__(self, records: tuple[LibraryRecord, ...]) -> None:
        self.records = records

    def list_books(self) -> tuple[LibraryRecord, ...]:
        return self.records


class _BatchBookListService(_BookListService):
    def __init__(self, records: tuple[LibraryRecord, ...]) -> None:
        super().__init__(records)
        self.last_search_report = ProviderSearchReport(
            searched_providers=("Test Books",),
        )

    def search_enabled_candidates(self, **values):
        return (
            MetadataCandidate(
                title=str(values["title"]),
                author=str(values["author"]),
                isbn="9780000000000",
                publisher="Test Books",
                language="en",
                published_date="2026",
                cover_id=None,
                work_key=f"/{values['title']}",
                confidence=90,
                confidence_reason="Exact test match",
            ),
        )


def test_batch_lookup_cancels_between_books_without_losing_results() -> None:
    service = _BatchBookListService(
        (
            _record(1, "First", 1),
            _record(2, "Second", 1),
        )
    )
    worker = MetadataBatchLookupWorker(service, service.records)
    ready: list[int] = []
    cancelled: list[tuple[int, int]] = []
    worker.result_ready.connect(
        lambda book_id, _candidates, _report: ready.append(book_id)
    )
    worker.cancelled.connect(
        lambda processed, matched: cancelled.append((processed, matched))
    )
    original_search = service.search_enabled_candidates

    def search_then_cancel(**values):
        result = original_search(**values)
        worker.request_cancel()
        return result

    service.search_enabled_candidates = search_then_cancel

    worker.run()

    assert ready == [1]
    assert cancelled == [(1, 1)]


def test_metadata_match_automatically_selects_correct_file_organisation(
    tmp_path: Path,
) -> None:
    _application = QApplication.instance() or QApplication([])
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    page = MetadataStudioPage(
        _BookListService((_record(1, "Unsorted Book", 1),)),
        preferences,
        lambda: None,
    )
    series_match = MetadataCandidate(
        title="Hexed",
        author="Kevin Hearne",
        isbn="",
        publisher="",
        language="en",
        published_date="",
        cover_id=None,
        work_key="series-match",
        confidence=95,
        confidence_reason="Exact match",
        series="Iron Druid Chronicles",
        series_number="2",
    )
    standalone_match = MetadataCandidate(
        title="The Hermit Next Door",
        author="Kevin Hearne",
        isbn="",
        publisher="",
        language="en",
        published_date="",
        cover_id=None,
        work_key="standalone-match",
        confidence=95,
        confidence_reason="Exact match",
    )

    page.results_list.clear()
    page.results_list.addItem("Series", series_match)
    page._candidate_changed(0)

    assert page.organise_file_check.isChecked()
    assert page.field_editors["series"].text() == "Iron Druid Chronicles"
    assert page.field_editors["series_number"].text() == "2"
    assert "shared -=Series=-" in page.plan_summary.text()

    page.results_list.clear()
    page.results_list.addItem("Standalone", standalone_match)
    page._candidate_changed(0)

    assert page.organise_file_check.isChecked()
    assert page.field_editors["series"].text() == ""
    assert page.field_editors["series_number"].text() == ""
    assert "Author folder" in page.plan_summary.text()
    page.close()


def test_metadata_page_displays_whole_series_positions_without_decimal(
    tmp_path: Path,
) -> None:
    _application = QApplication.instance() or QApplication([])
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    record = replace(
        _record(1, "Assassin's Quest", 1),
        series="The Farseer Trilogy",
        series_number=3.0,
    )
    page = MetadataStudioPage(
        _BookListService((record,)),
        preferences,
        lambda: None,
    )

    assert page.field_editors["series_number"].text() == "3"

    candidate = MetadataCandidate(
        title="Assassin's Quest",
        author="Robin Hobb",
        isbn="9780553565690",
        publisher="Spectra",
        language="en",
        published_date="1998-01-05",
        cover_id=None,
        work_key="farseer-3",
        confidence=90,
        confidence_reason="Exact match",
        series="The Farseer Trilogy",
        series_number="3.0",
    )
    page.results_list.clear()
    page.results_list.addItem("Candidate", candidate)
    page._candidate_changed(0)

    assert page.field_editors["series_number"].text() == "3"
    page.close()


def test_metadata_page_shows_original_path_and_uses_filename_series_order(
    tmp_path: Path,
) -> None:
    _application = QApplication.instance() or QApplication([])
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    record = replace(
        _record(1, "01 - Thieves of Blood", 1),
        file_name="01 - Thieves of Blood - Tim Waggoner.epub",
        file_path=(
            "C:/EPUB/1-10/01 - Thieves of Blood - Tim Waggoner.epub"
        ),
    )
    page = MetadataStudioPage(
        _BookListService((record,)),
        preferences,
        lambda: None,
    )
    proposed_path = Path(
        "C:/EPUB/1-10/-=Series=-/Blade of the Flame/"
        "01 - Thieves of Blood - Tim Waggoner.epub"
    )
    page.service.proposed_file_path = (
        lambda *_args, **kwargs: (
            proposed_path if kwargs["organise_file"] else Path(record.file_path)
        )
    )
    assert page.new_path_edit.text() == record.file_path
    candidate = MetadataCandidate(
        title="Thieves of Blood",
        author="Tim Waggoner",
        isbn="",
        publisher="",
        language="en",
        published_date="",
        cover_id=None,
        work_key="blade-of-the-flame",
        confidence=95,
        confidence_reason="Exact match",
        series="Blade of the Flame",
        series_number="",
        provider_rating=4.25,
        rating_count=80,
    )

    page.results_list.clear()
    page.results_list.addItem("Series without provider order", candidate)
    page._candidate_changed(0)

    assert page.original_path_edit.text() == record.file_path
    assert page.original_path_edit.toolTip() == record.file_path
    assert page.new_path_edit.text() == str(proposed_path)
    assert page.new_path_edit.toolTip() == str(proposed_path)
    assert page.field_editors["series_number"].text() == "1"
    assert page.field_editors["provider_rating"].text() == "4.25"
    assert page.field_checks["provider_rating"].isChecked()
    assert "80 ratings" in page.rating_details.text()
    assert page.organise_file_check.isChecked()
    assert page.manual_review_button.text() == "Move to Manual Review..."
    page.organise_file_check.setChecked(False)
    assert page.new_path_edit.text() == str(Path(record.file_path))
    page.close()

def test_expired_apply_refreshes_preview_and_explains_next_step(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _application = QApplication.instance() or QApplication([])
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    expired_plan = SimpleNamespace(
        is_expired=lambda: True,
        database_changes=(SimpleNamespace(book_id=1),),
        file_changes=(),
    )
    protection = SimpleNamespace(
        get_operation=lambda _operation_id: SimpleNamespace(
            plan=expired_plan,
        )
    )
    page = MetadataStudioPage(
        _BookListService((_record(1, "Current Book", 1),)),
        preferences,
        lambda: protection,
    )
    page.current_plan_id = 42
    page.apply_button.setEnabled(True)
    messages: list[tuple[str, str]] = []

    def refresh_preview() -> None:
        page.current_plan_id = 43
        page.apply_button.setEnabled(True)
        page.plan_summary.setText("Fresh exact preview")

    monkeypatch.setattr(page, "_preview_changes", refresh_preview)
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    page._apply_changes()

    assert page.current_plan_id == 43
    assert page.apply_button.isEnabled()
    assert page.plan_summary.text() == "Fresh exact preview"
    assert messages and messages[0][0] == "Preview Refreshed"
    assert "Apply Reviewed Changes again" in messages[0][1]
    page.close()


def test_changing_books_discards_visible_preview_and_apply_state(
    tmp_path: Path,
) -> None:
    _application = QApplication.instance() or QApplication([])
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    page = MetadataStudioPage(
        _BookListService(
            (_record(1, "First Book", 1), _record(2, "Second Book", 1))
        ),
        preferences,
        lambda: None,
    )
    page.current_plan_id = 42
    page.apply_button.setEnabled(True)
    page.plan_summary.setText("Stale preview for First Book")

    page.book_combo.setCurrentIndex(1)

    assert page.current_book.book_id == 2
    assert page.current_plan_id is None
    assert not page.apply_button.isEnabled()
    assert "No changes are prepared for this book" in page.plan_summary.text()
    page.close()


def test_apply_refuses_preview_prepared_for_another_book(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _application = QApplication.instance() or QApplication([])
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    wrong_plan = SimpleNamespace(
        database_changes=(SimpleNamespace(book_id=2),),
        file_changes=(),
        is_expired=lambda: False,
    )
    protection = SimpleNamespace(
        get_operation=lambda _operation_id: SimpleNamespace(plan=wrong_plan)
    )
    page = MetadataStudioPage(
        _BookListService((_record(1, "Current Book", 1),)),
        preferences,
        lambda: protection,
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    page.current_plan_id = 42
    page.apply_button.setEnabled(True)

    page._apply_changes()

    assert page.current_plan_id is None
    assert not page.apply_button.isEnabled()
    assert warnings and "different book" in warnings[0]
    page.close()


def test_apply_confirmation_can_be_hidden_and_restored_in_preferences(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _application = QApplication.instance() or QApplication([])
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    page = MetadataStudioPage(
        _BookListService((_record(1, "Current Book", 1),)),
        preferences,
        lambda: None,
    )
    page.plan_summary.setText("Update the reviewed title.")

    def accept_and_hide(dialog: QMessageBox) -> int:
        assert dialog.checkBox() is not None
        dialog.checkBox().setChecked(True)
        return int(QMessageBox.StandardButton.Yes)

    monkeypatch.setattr(QMessageBox, "exec", accept_and_hide)

    assert page._confirm_reviewed_apply()
    assert not preferences.load_metadata_preferences().confirm_reviewed_apply

    monkeypatch.setattr(
        QMessageBox,
        "exec",
        lambda _dialog: (_ for _ in ()).throw(
            AssertionError("A hidden confirmation must not open")
        ),
    )
    assert page._confirm_reviewed_apply()
    preferences.save_metadata_preferences(
        replace(
            preferences.load_metadata_preferences(),
            confirm_reviewed_apply=True,
        )
    )
    assert preferences.load_metadata_preferences().confirm_reviewed_apply
    page.close()


def test_successful_apply_advances_to_next_book_needing_attention(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    service = _BookListService(
        (
            _record(1, "First Book", 1),
            _record(2, "Finished Book", 0),
            _record(3, "Next Book", 1),
        )
    )
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    page = MetadataStudioPage(
        service,
        preferences,
        lambda: None,
    )

    assert page.current_book.book_id == 1
    updated: list[int] = []
    page.book_updated.connect(updated.append)
    page._apply_completed(None)
    application.processEvents()

    assert page.current_book.book_id == 3
    assert updated == [1]
    assert "next book needing attention" in (
        page.status_label.text().casefold()
    )
    page.close()


def test_auto_next_option_starts_lookup_after_successful_apply(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    service = _BookListService(
        (
            _record(1, "First Book", 1),
            _record(2, "Next Book", 1),
        )
    )
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    page = MetadataStudioPage(service, preferences, lambda: None)
    started: list[int] = []
    monkeypatch.setattr(
        page,
        "_start_lookup",
        lambda: started.append(page.current_book.book_id),
    )
    page.auto_next_checkbox.setChecked(True)

    page._apply_completed(None)
    application.processEvents()

    assert page.current_book.book_id == 2
    assert started == [2]
    assert preferences.load_metadata_preferences().auto_lookup_next
    page.close()


def test_auto_next_searches_next_unprocessed_book_even_when_it_is_healthy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    application = QApplication.instance() or QApplication([])
    service = _BookListService(
        (
            _record(1, "First Book", 1),
            _record(2, "Healthy Next Book", 0),
        )
    )
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    page = MetadataStudioPage(service, preferences, lambda: None)
    started: list[int] = []
    monkeypatch.setattr(
        page,
        "_start_lookup",
        lambda: started.append(page.current_book.book_id),
    )
    page.auto_next_checkbox.setChecked(True)

    page._apply_completed(None)
    application.processEvents()

    assert page.current_book.book_id == 2
    assert started == [2]
    assert "starting its metadata and cover search" in (
        page.status_label.text().casefold()
    )
    page.close()


def test_full_scan_searches_all_books_and_shows_clickable_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _application = QApplication.instance() or QApplication([])
    service = _BatchBookListService(
        (
            _record(1, "Needs Review", 1),
            _record(2, "Already Healthy", 0),
            _record(3, "Also Needs Review", 1),
        )
    )
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    page = MetadataStudioPage(service, preferences, lambda: None)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    assert page.prepare_queue_button.isEnabled()
    page.prepare_queue_button.click()
    assert page.batch_thread is not None

    _wait_until(lambda: page.batch_thread is None)
    assert tuple(page.prepared_results) == (1, 2, 3)
    assert page.batch_review_list.count() == 3
    assert page.current_book.book_id == 1
    assert page.current_candidates[0].title == "Needs Review"
    assert "3 with matches" in page.queue_status_label.text()
    assert page.apply_button.isEnabled() is False

    page.batch_review_list.setCurrentRow(1)
    assert page.current_book.book_id == 2
    assert page.current_candidates[0].title == "Already Healthy"

    page.reject_prepared_button.click()
    assert page.prepared_decisions[2] == "rejected"
    assert "REJECTED" in page.batch_review_list.item(1).text()
    assert page.current_plan_id is None

    page.batch_review_list.setCurrentRow(0)

    def create_test_preview() -> None:
        page.current_plan_id = 99

    monkeypatch.setattr(page, "_preview_changes", create_test_preview)
    page.accept_prepared_button.click()
    assert page.prepared_decisions[1] == "accepted"
    assert "ACCEPTED FOR PREVIEW" in page.batch_review_list.item(0).text()
    page.close()


def test_successful_apply_stays_put_when_no_other_book_needs_attention(
    tmp_path: Path,
) -> None:
    _application = QApplication.instance() or QApplication([])
    service = _BookListService(
        (
            _record(1, "Current Book", 1),
            _record(2, "Finished Book", 0),
        )
    )
    preferences = PreferencesStore(
        QSettings(
            str(tmp_path / "preferences.ini"),
            QSettings.Format.IniFormat,
        )
    )
    page = MetadataStudioPage(
        service,
        preferences,
        lambda: None,
    )

    page._apply_completed(None)

    assert page.current_book.book_id == 1
    assert "no other books needing attention" in (
        page.status_label.text().casefold()
    )
    page.close()

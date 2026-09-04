"""Beginner-facing metadata lookup, review, and cover selection page."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from math import ceil
from pathlib import Path
import re

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from preferences import PreferencesStore
from services.library_service import LibraryRecord
from services.metadata_studio_service import (
    clean_published_date,
    MetadataCandidate,
    ProviderSearchReport,
    MetadataStudioService,
)
from services.protection_models import PlanConfirmation
from services.protection_service import ProtectionService
from workers.metadata_lookup_worker import (
    MetadataBatchLookupWorker,
    MetadataLookupWorker,
)
from workers.protection_executor_worker import ProtectionExecutorWorker


class ClickableCoverLabel(QLabel):
    """Small cover preview that opens an accessible larger view."""

    activated = Signal()

    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setAccessibleName("Book cover preview")
        self.setToolTip("Click to view this cover at a larger size.")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in {
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        }:
            self.activated.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class CoverPreviewDialog(QDialog):
    """Screen-bounded, non-destructive large cover viewer."""

    def __init__(
        self,
        pixmap: QPixmap,
        *,
        title: str,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("largeCoverPreviewDialog")
        self.setWindowTitle(f"Cover Preview - {title}")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        screen = parent.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry()
        maximum_width = max(320, int(available.width() * 0.72))
        maximum_height = max(420, int(available.height() * 0.78))
        width_factor = maximum_width / max(1, pixmap.width())
        height_factor = maximum_height / max(1, pixmap.height())
        maximum_factor = min(width_factor, height_factor)
        readable_factor = max(1.0, 600 / max(1, pixmap.height()))
        scale_factor = min(maximum_factor, readable_factor)
        target_width = max(1, round(pixmap.width() * scale_factor))
        target_height = max(1, round(pixmap.height() * scale_factor))

        self.image_label = QLabel()
        self.image_label.setObjectName("largeCoverPreviewImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setPixmap(
            pixmap.scaled(
                target_width,
                target_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        scroll = QScrollArea()
        scroll.setObjectName("largeCoverPreviewScroll")
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(self.image_label)

        close_button = QPushButton("Close")
        close_button.setObjectName("largeCoverPreviewClose")
        close_button.clicked.connect(self.close)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(scroll, 1)
        layout.addLayout(actions)
        self.resize(
            min(available.width() - 40, target_width + 56),
            min(available.height() - 60, target_height + 100),
        )


class MetadataStudioPage(QWidget):
    """Look up metadata first and show only the decisions users need."""

    catalogue_changed = Signal()
    book_updated = Signal(int)
    review_queue_requested = Signal()
    work_stopped = Signal()

    FIELD_LABELS = (
        ("title", "Title"),
        ("author", "Author"),
        ("isbn", "ISBN"),
        ("publisher", "Publisher"),
        ("language", "Language"),
        ("published_date", "Published"),
        ("series", "Series"),
        ("series_number", "Series no."),
        ("series_group", "Series group"),
        ("series_group_number", "Group no."),
        ("description", "Description"),
        ("cover_path", "Cover"),
    )

    def __init__(
        self,
        service: MetadataStudioService,
        preferences: PreferencesStore,
        protection_service_factory: Callable[[], ProtectionService],
    ) -> None:
        super().__init__()
        self.service = service
        self.preferences = preferences
        self.protection_service_factory = protection_service_factory
        self.lookup_thread: QThread | None = None
        self.lookup_worker: MetadataLookupWorker | None = None
        self.apply_thread: QThread | None = None
        self.apply_worker: ProtectionExecutorWorker | None = None
        self.batch_thread: QThread | None = None
        self.batch_worker: MetadataBatchLookupWorker | None = None
        self.current_book: LibraryRecord | None = None
        self.current_plan_id: int | None = None
        self.current_candidates: tuple[MetadataCandidate, ...] = ()
        self.preview_cover_path = ""
        self.preview_cover_candidate: MetadataCandidate | None = None
        self.pending_cover_candidate: MetadataCandidate | None = None
        self.pending_cover_fallback = False
        self.cover_fallback_attempted = False
        self.validated_cover_paths: dict[str, str] = {}
        self.provider_summary = ""
        self.cover_viewer: CoverPreviewDialog | None = None
        self.prepared_results: dict[
            int,
            tuple[MetadataCandidate, ...],
        ] = {}
        self.prepared_reports: dict[int, ProviderSearchReport] = {}
        self.prepared_failures: dict[int, str] = {}
        self.prepared_records: dict[int, LibraryRecord] = {}
        self.prepared_decisions: dict[int, str] = {}
        self.pending_auto_lookup_book_id: int | None = None
        self.auto_lookup_completed_ids: set[int] = set()
        self.lookup_elapsed_seconds = 0
        self.lookup_status_timer = QTimer(self)
        self.lookup_status_timer.setInterval(1000)
        self.lookup_status_timer.timeout.connect(self._update_lookup_elapsed)

        title = QLabel("Metadata & Cover Art")
        title.setObjectName("pageTitle")
        self.title_label = title
        description = QLabel(
            "Find book information and cover art together, compare the "
            "results, and choose exactly what to use."
        )
        description.setObjectName("pageDescription")
        description.setWordWrap(True)
        self.description_label = description

        self.book_combo = QComboBox()
        self.book_combo.setObjectName("metadataBookSelector")
        self.book_combo.setMinimumWidth(0)
        self.book_combo.currentIndexChanged.connect(self._book_changed)
        self.lookup_button = QPushButton("Find Metadata && Covers")
        self.lookup_button.setAccessibleName("Find Metadata & Covers")
        self.lookup_button.setObjectName("metadataLookupAction")
        self.lookup_button.clicked.connect(self._start_lookup)
        self.queue_button = QPushButton("Review Books with Issues")
        self.queue_button.setObjectName("metadataQueueAction")
        self.queue_button.clicked.connect(self.review_queue_requested.emit)
        book_row = QHBoxLayout()
        book_row.addWidget(QLabel("Book"))
        book_row.addWidget(self.book_combo, 1)
        book_row.addWidget(self.queue_button)

        self.original_path_edit = QLineEdit()
        self.original_path_edit.setObjectName("metadataOriginalFilePath")
        self.original_path_edit.setReadOnly(True)
        self.original_path_edit.setMinimumWidth(0)
        self.original_path_edit.setPlaceholderText(
            "The selected book's complete original file path"
        )
        self.new_path_edit = QLineEdit()
        self.new_path_edit.setObjectName("metadataNewFilePath")
        self.new_path_edit.setReadOnly(True)
        self.new_path_edit.setMinimumWidth(0)
        self.new_path_edit.setPlaceholderText(
            "The complete path that Apply will use"
        )
        original_path_row = QHBoxLayout()
        original_path_row.addWidget(QLabel("Original file"))
        original_path_row.addWidget(self.original_path_edit, 1)
        original_path_row.addWidget(QLabel("New file"))
        original_path_row.addWidget(self.new_path_edit, 1)

        self.provider_combo = QComboBox()
        self.provider_combo.setObjectName("metadataProviderSelector")
        self.provider_combo.setMinimumWidth(0)
        self.provider_combo.setToolTip(
            "Search every active provider or restrict this lookup to one."
        )
        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Search provider"))
        provider_row.addWidget(self.provider_combo, 1)
        provider_row.addWidget(self.lookup_button)

        self.auto_next_checkbox = QCheckBox(
            "Automatically search the next book after Apply"
        )
        self.auto_next_checkbox.setObjectName("metadataAutoNextLookup")
        self.auto_next_checkbox.setChecked(
            self.preferences.load_metadata_preferences().auto_lookup_next
        )
        self.auto_next_checkbox.setToolTip(
            "Search is read-only. Every result still requires manual review, "
            "Preview, and Apply."
        )
        self.auto_next_checkbox.toggled.connect(
            self._auto_next_preference_changed
        )
        self.prepare_queue_button = QPushButton("Recheck All Books")
        self.prepare_queue_button.setObjectName("metadataPrepareQueueAction")
        self.prepare_queue_button.setToolTip(
            "Deliberately recheck every catalogued book, including completed "
            "books. Nothing is applied automatically."
        )
        self.prepare_queue_button.clicked.connect(
            self._prepare_or_cancel_review_queue
        )
        self.prepare_folder_button = QPushButton("Scan Folder")
        self.prepare_folder_button.setObjectName(
            "metadataPrepareFolderQueueAction"
        )
        self.prepare_folder_button.setToolTip(
            "Choose a folder and prepare fresh metadata and cover results for "
            "every catalogued book beneath it, including completed books."
        )
        self.prepare_folder_button.clicked.connect(
            self._prepare_folder_review_queue
        )
        self.next_prepared_button = QPushButton("Next Prepared")
        self.next_prepared_button.setObjectName(
            "metadataNextPreparedAction"
        )
        self.next_prepared_button.setEnabled(False)
        self.next_prepared_button.clicked.connect(
            self._select_next_prepared_result
        )
        self.queue_status_label = QLabel("No prepared review queue")
        self.queue_status_label.setObjectName("metadataQueueStatus")
        queue_row = QHBoxLayout()
        queue_row.addWidget(self.auto_next_checkbox)
        queue_row.addStretch(1)
        queue_row.addWidget(self.queue_status_label)
        queue_row.addWidget(self.next_prepared_button)
        queue_row.addWidget(self.prepare_folder_button)
        queue_row.addWidget(self.prepare_queue_button)

        self.batch_review_list = QListWidget()
        self.batch_review_list.setObjectName("metadataBatchReviewList")
        self.batch_review_list.setAccessibleName(
            "Full metadata scan review results"
        )
        self.batch_review_list.setToolTip(
            "Click a book to inspect its metadata and cover findings."
        )
        self.batch_review_list.setMaximumHeight(118)
        self.batch_review_list.currentItemChanged.connect(
            self._batch_review_item_changed
        )
        self.accept_prepared_button = QPushButton("Accept Selection")
        self.accept_prepared_button.setObjectName(
            "metadataAcceptPreparedAction"
        )
        self.accept_prepared_button.setEnabled(False)
        self.accept_prepared_button.setToolTip(
            "Accept the selected candidate for Preview. This does not apply "
            "changes to the catalogue or ebook file."
        )
        self.accept_prepared_button.clicked.connect(
            self._accept_prepared_result
        )
        self.reject_prepared_button = QPushButton("Reject Result")
        self.reject_prepared_button.setObjectName(
            "metadataRejectPreparedAction"
        )
        self.reject_prepared_button.setEnabled(False)
        self.reject_prepared_button.setToolTip(
            "Reject this scan result for the current session. The book and "
            "catalogue are not changed."
        )
        self.reject_prepared_button.clicked.connect(
            self._reject_prepared_result
        )
        batch_review_actions = QHBoxLayout()
        batch_review_actions.addWidget(QLabel("Full scan results"))
        batch_review_actions.addStretch(1)
        batch_review_actions.addWidget(self.reject_prepared_button)
        batch_review_actions.addWidget(self.accept_prepared_button)
        self.batch_review_panel = QFrame()
        self.batch_review_panel.setObjectName("metadataBatchReviewPanel")
        batch_review_layout = QVBoxLayout(self.batch_review_panel)
        batch_review_layout.setContentsMargins(8, 5, 8, 5)
        batch_review_layout.setSpacing(4)
        batch_review_layout.addLayout(batch_review_actions)
        batch_review_layout.addWidget(self.batch_review_list)
        self.batch_review_panel.hide()

        self.review_page = self._build_review_page()

        self.progress = QProgressBar()
        self.progress.setObjectName("metadataProgress")
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.status_label = QLabel(
            "Select a book, then choose Find Metadata & Covers."
        )
        self.status_label.setObjectName("metadataStatus")
        self.status_label.setWordWrap(True)

        self.page_layout = QVBoxLayout(self)
        self.page_layout.setContentsMargins(28, 22, 28, 20)
        self.page_layout.setSpacing(10)
        self.page_layout.addWidget(title)
        self.page_layout.addWidget(description)
        self.page_layout.addLayout(book_row)
        self.page_layout.addLayout(original_path_row)
        self.page_layout.addLayout(provider_row)
        self.page_layout.addLayout(queue_row)
        self.page_layout.addWidget(self.batch_review_panel)
        self.page_layout.addWidget(self.review_page, 1)
        self.page_layout.addWidget(self.progress)
        self.page_layout.addWidget(self.status_label)

        self.refresh()

    def _build_review_page(self) -> QWidget:
        self.results_list = QComboBox()
        self.results_list.setObjectName("metadataCandidateList")
        self.results_list.addItem(
            "Run Find Metadata & Covers to see matches",
            None,
        )
        self.results_list.currentIndexChanged.connect(
            self._candidate_changed
        )

        self.field_checks: dict[str, QCheckBox] = {}
        self.field_editors: dict[str, QWidget] = {}
        form = QGridLayout()
        form.setContentsMargins(12, 10, 12, 8)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(5)
        self.metadata_form_layout = form
        for index, (field, label) in enumerate(self.FIELD_LABELS[:-2]):
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            editor = QLineEdit()
            editor.setMinimumWidth(0)
            self.field_checks[field] = checkbox
            self.field_editors[field] = editor
            if field in {
                "title",
                "author",
                "series",
                "series_number",
                "series_group",
                "series_group_number",
            }:
                checkbox.toggled.connect(self._update_new_file_path)
                editor.textChanged.connect(self._update_new_file_path)
            positions = {
                "title": (0, 0),
                "author": (1, 0),
                "isbn": (2, 0),
                "publisher": (3, 0),
                "language": (0, 2),
                "published_date": (1, 2),
                "series": (2, 2),
                "series_number": (3, 2),
                "series_group": (4, 0),
                "series_group_number": (4, 2),
            }
            row, column = positions[field]
            form.addWidget(checkbox, row, column)
            form.addWidget(editor, row, column + 1)

        self.rating_check = QCheckBox("Website rating")
        self.rating_edit = QLineEdit()
        self.rating_edit.setReadOnly(True)
        self.rating_edit.setPlaceholderText("Not supplied by this provider")
        self.rating_details = QLabel()
        self.rating_details.setObjectName("metadataRatingDetails")
        self.field_checks["provider_rating"] = self.rating_check
        self.field_editors["provider_rating"] = self.rating_edit
        form.addWidget(self.rating_check, 5, 0)
        form.addWidget(self.rating_edit, 5, 1)
        form.addWidget(self.rating_details, 5, 2, 1, 2)

        self.description_check = QCheckBox("Description")
        self.description_check.setChecked(True)
        self.description_edit = QTextEdit()
        self.description_edit.setMinimumHeight(58)
        self.description_edit.setMaximumHeight(58)
        self.description_edit.textChanged.connect(
            lambda: QTimer.singleShot(0, self._resize_description_editor)
        )
        self.field_checks["description"] = self.description_check
        self.field_editors["description"] = self.description_edit
        form.addWidget(self.description_check, 6, 0)
        form.addWidget(self.description_edit, 6, 1, 1, 3)

        self.cover_result_combo = QComboBox()
        self.cover_result_combo.setObjectName("metadataCoverResults")
        self.cover_result_combo.setFixedHeight(38)
        self.cover_result_combo.currentIndexChanged.connect(
            self._cover_candidate_changed
        )
        self.cover_preview = ClickableCoverLabel("No cover\nselected")
        self.cover_preview.setObjectName("metadataCoverPreview")
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_preview.setWordWrap(True)
        self.cover_preview.setFixedSize(78, 100)
        self.cover_preview.activated.connect(self._open_large_cover)

        self.cover_path_edit = QLineEdit()
        self.cover_path_edit.setReadOnly(True)
        self.cover_path_edit.setPlaceholderText(
            "A found cover or an image from this computer"
        )
        self.field_checks["cover_path"] = QCheckBox("Include cover")
        self.field_checks["cover_path"].setChecked(True)
        self.field_editors["cover_path"] = self.cover_path_edit
        self.download_cover_button = QPushButton("Use Cover")
        self.download_cover_button.setObjectName("coverDownloadAction")
        self.download_cover_button.setFixedHeight(38)
        self.download_cover_button.setMinimumWidth(174)
        self.download_cover_button.setEnabled(False)
        self.download_cover_button.clicked.connect(
            self._start_cover_download
        )
        self.find_covers_button = QPushButton("Find Covers")
        self.find_covers_button.setObjectName("coverSearchOnlyAction")
        self.find_covers_button.setFixedHeight(38)
        self.find_covers_button.setMinimumWidth(150)
        self.find_covers_button.setToolTip(
            "Search all active cover providers using the metadata currently "
            "shown above. The selected metadata will not be replaced."
        )
        self.find_covers_button.clicked.connect(self._start_cover_lookup)
        self.local_cover_button = QPushButton("Cover File\u2026")
        self.local_cover_button.setObjectName("coverFileAction")
        self.local_cover_button.setFixedHeight(38)
        self.local_cover_button.setMinimumWidth(174)
        self.local_cover_button.clicked.connect(self._choose_local_cover)

        cover_panel = QFrame()
        cover_panel.setObjectName("metadataCoverPanel")
        cover_panel.setMinimumHeight(110)
        self.cover_panel = cover_panel
        cover_layout = QHBoxLayout(cover_panel)
        cover_layout.setContentsMargins(8, 5, 8, 8)
        cover_layout.setSpacing(8)
        cover_layout.addWidget(self.cover_preview)
        cover_controls = QVBoxLayout()
        cover_controls.setContentsMargins(0, 0, 0, 0)
        cover_controls.setSpacing(6)
        cover_controls.setAlignment(Qt.AlignmentFlag.AlignTop)
        cover_choice_row = QHBoxLayout()
        cover_choice_row.addWidget(QLabel("Found covers"))
        cover_choice_row.addWidget(self.cover_result_combo, 1)
        cover_choice_row.addWidget(self.find_covers_button)
        cover_choice_row.setAlignment(
            self.cover_result_combo,
            Qt.AlignmentFlag.AlignVCenter,
        )
        cover_choice_row.setAlignment(
            self.find_covers_button,
            Qt.AlignmentFlag.AlignVCenter,
        )
        cover_controls.addLayout(cover_choice_row)
        cover_action_row = QHBoxLayout()
        cover_action_row.addWidget(self.field_checks["cover_path"])
        cover_action_row.addStretch(1)
        cover_action_row.addWidget(self.download_cover_button)
        cover_action_row.addWidget(self.local_cover_button)
        cover_controls.addLayout(cover_action_row)
        cover_layout.addLayout(cover_controls, 1)

        form_panel = QFrame()
        form_panel.setObjectName("metadataReviewPanel")
        form_panel_layout = QVBoxLayout(form_panel)
        form_panel_layout.setContentsMargins(0, 0, 0, 0)
        form_panel_layout.setSpacing(4)
        result_row = QFormLayout()
        result_row.setContentsMargins(12, 6, 12, 0)
        result_row.addRow("Possible matches", self.results_list)
        form_panel_layout.addLayout(result_row)
        self.source_assessment_label = QLabel()
        self.source_assessment_label.setObjectName("metadataSourceAssessment")
        self.source_assessment_label.setAccessibleName(
            "Metadata evidence and conflicts"
        )
        self.source_assessment_label.setWordWrap(True)
        self.source_assessment_label.setContentsMargins(12, 0, 12, 2)
        self.source_assessment_label.hide()
        review_content = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        review_content.setContentsMargins(0, 0, 0, 0)
        review_content.setSpacing(8)
        review_content.addLayout(form, 1)
        review_content.addWidget(cover_panel, 1)
        self.review_content_layout = review_content
        # Keep the review fields immediately below Possible matches. Giving
        # this layout the expanding stretch pushed its children to the bottom
        # of the panel in maximised windows and left a large empty void in the
        # middle of the page.
        form_panel_layout.addLayout(review_content)
        form_panel_layout.addWidget(self.source_assessment_label)
        form_panel_layout.addStretch(1)

        self.plan_summary = QLabel(
            "No changes are prepared. Lookup does not change your catalogue."
        )
        self.plan_summary.setObjectName("metadataPlanSummary")
        self.plan_summary.setWordWrap(True)
        self.organise_file_check = QCheckBox(
            "Organise file into Author / shared -=Series=- folders when applying"
        )
        self.organise_file_check.setObjectName("metadataOrganiseFileCheck")
        self.organise_file_check.setToolTip(
            "Preview and safely rename/move this ebook inside its watched "
            "library. Numbered series preserve reading order; unnumbered "
            "collections use a normal title and author filename."
        )
        self.organise_file_check.toggled.connect(
            self._organisation_option_changed
        )
        self.preview_button = QPushButton("Preview Selected Changes")
        self.preview_button.setObjectName("metadataPreviewAction")
        self.preview_button.clicked.connect(self._preview_changes)
        self.apply_button = QPushButton("Apply Reviewed Changes")
        self.apply_button.setObjectName("metadataApplyAction")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_changes)
        self.manual_review_button = QPushButton("Move to Manual Review...")
        self.manual_review_button.setObjectName("metadataManualReviewAction")
        self.manual_review_button.setEnabled(False)
        self.manual_review_button.setToolTip(
            "Move this file out of the active catalogue when it is not a "
            "valid book or no useful metadata can be found."
        )
        self.manual_review_button.clicked.connect(
            self._move_to_manual_review
        )
        self.delete_book_button = QPushButton("Delete Book...")
        self.delete_book_button.setObjectName("metadataDeleteBookAction")
        self.delete_book_button.setEnabled(False)
        self.delete_book_button.setToolTip(
            "Stop Twano checking this book and move its file out of the "
            "active catalogue into a -=deleted=- folder."
        )
        self.delete_book_button.clicked.connect(self._delete_book)
        actions = QHBoxLayout()
        actions.addWidget(self.manual_review_button)
        actions.addWidget(self.delete_book_button)
        actions.addStretch(1)
        actions.addWidget(self.preview_button)
        actions.addWidget(self.apply_button)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(form_panel, 1)
        layout.addWidget(self.organise_file_check)
        layout.addWidget(self.plan_summary)
        layout.addLayout(actions)
        return page

    def resizeEvent(self, event) -> None:
        """Keep the complete review visible in compact restored windows."""
        compact = event.size().width() < 900 or event.size().height() < 650
        large = event.size().width() >= 1200 and event.size().height() >= 850
        self.description_label.setVisible(not compact)
        self.title_label.setVisible(not compact)
        self.queue_status_label.setVisible(not compact)
        self.status_label.setVisible(not compact)
        for field in ("isbn", "publisher", "language", "published_date"):
            self.field_checks[field].setVisible(not compact)
            self.field_editors[field].setVisible(not compact)
        self.description_check.setVisible(not compact)
        self.description_edit.setVisible(not compact)
        self.review_content_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if compact
            else QBoxLayout.Direction.LeftToRight
        )
        self.auto_next_checkbox.setText(
            "Search next after Apply"
            if compact
            else "Automatically search the next book after Apply"
        )
        if compact:
            # Let the two essential metadata rows keep their natural height.
            # Giving the form an equal stretch caused Qt to compress the line
            # edits until their text was visibly clipped at 900 x 600.
            self.review_content_layout.setStretch(0, 0)
            self.review_content_layout.setStretch(1, 1)
            self.page_layout.setContentsMargins(16, 10, 16, 10)
            self.page_layout.setSpacing(5)
            self.metadata_form_layout.setContentsMargins(8, 4, 8, 4)
            self.metadata_form_layout.setVerticalSpacing(2)
            self.description_edit.setFixedHeight(42)
            self.cover_preview.setFixedSize(64, 82)
            # The shared theme gives buttons a 46-pixel polished height even
            # when their nominal fixed height is smaller. Keep enough room
            # for both rows so the action buttons stay inside the panel.
            self.cover_panel.setMinimumHeight(98)
            self.download_cover_button.setMinimumWidth(0)
            self.find_covers_button.setMinimumWidth(0)
            self.local_cover_button.setMinimumWidth(0)
            compact_cover_button_style = (
                "QPushButton { min-height: 18px; padding: 4px 12px; }"
            )
            for button in (
                self.queue_button,
                self.lookup_button,
                self.next_prepared_button,
                self.prepare_folder_button,
                self.prepare_queue_button,
            ):
                button.setStyleSheet(compact_cover_button_style)
            # The compact form is two rows by two field groups. Repositioning
            # Series beside Title and Series number beside Author prevents the
            # four original grid rows from overlapping when space is tight.
            self.metadata_form_layout.addWidget(
                self.field_checks["series"], 0, 2
            )
            self.metadata_form_layout.addWidget(
                self.field_editors["series"], 0, 3
            )
            self.metadata_form_layout.addWidget(
                self.field_checks["series_number"], 1, 2
            )
            self.metadata_form_layout.addWidget(
                self.field_editors["series_number"], 1, 3
            )
            self.metadata_form_layout.addWidget(
                self.field_checks["series_group"], 2, 0
            )
            self.metadata_form_layout.addWidget(
                self.field_editors["series_group"], 2, 1
            )
            self.metadata_form_layout.addWidget(
                self.field_checks["series_group_number"], 2, 2
            )
            self.metadata_form_layout.addWidget(
                self.field_editors["series_group_number"], 2, 3
            )
            self.metadata_form_layout.addWidget(self.rating_check, 3, 0)
            self.metadata_form_layout.addWidget(self.rating_edit, 3, 1)
            self.metadata_form_layout.addWidget(
                self.rating_details, 3, 2, 1, 2
            )
            self.metadata_form_layout.addWidget(self.description_check, 4, 0)
            self.metadata_form_layout.addWidget(
                self.description_edit, 4, 1, 1, 3
            )
            for field in (
                "title",
                "author",
                "series",
                "series_number",
                "series_group",
                "series_group_number",
            ):
                self.field_editors[field].setMinimumHeight(38)
            self.download_cover_button.setStyleSheet(
                compact_cover_button_style
            )
            self.find_covers_button.setStyleSheet(compact_cover_button_style)
            self.local_cover_button.setStyleSheet(compact_cover_button_style)
            self.batch_review_list.setMaximumHeight(76)
        elif large:
            self.review_content_layout.setStretch(0, 1)
            self.review_content_layout.setStretch(1, 1)
            self.page_layout.setContentsMargins(28, 22, 28, 20)
            self.page_layout.setSpacing(10)
            self.metadata_form_layout.setContentsMargins(12, 10, 12, 8)
            self.metadata_form_layout.setVerticalSpacing(5)
            self._resize_description_editor()
            self.cover_preview.setFixedSize(156, 200)
            self.cover_panel.setMinimumHeight(210)
            self.download_cover_button.setMinimumWidth(174)
            self.find_covers_button.setMinimumWidth(150)
            self.local_cover_button.setMinimumWidth(174)
            self.download_cover_button.setStyleSheet("")
            self.find_covers_button.setStyleSheet("")
            self.local_cover_button.setStyleSheet("")
            for button in (
                self.queue_button,
                self.lookup_button,
                self.next_prepared_button,
                self.prepare_folder_button,
                self.prepare_queue_button,
            ):
                button.setStyleSheet("")
            for field in (
                "title",
                "author",
                "series",
                "series_number",
                "series_group",
                "series_group_number",
            ):
                self.field_editors[field].setMinimumHeight(0)
            self.metadata_form_layout.addWidget(
                self.field_checks["series"], 2, 2
            )
            self.metadata_form_layout.addWidget(
                self.field_editors["series"], 2, 3
            )
            self.metadata_form_layout.addWidget(
                self.field_checks["series_number"], 3, 2
            )
            self.metadata_form_layout.addWidget(
                self.field_editors["series_number"], 3, 3
            )
            self.metadata_form_layout.addWidget(
                self.field_checks["series_group"], 4, 0
            )
            self.metadata_form_layout.addWidget(
                self.field_editors["series_group"], 4, 1
            )
            self.metadata_form_layout.addWidget(
                self.field_checks["series_group_number"], 4, 2
            )
            self.metadata_form_layout.addWidget(
                self.field_editors["series_group_number"], 4, 3
            )
            self.metadata_form_layout.addWidget(self.rating_check, 5, 0)
            self.metadata_form_layout.addWidget(self.rating_edit, 5, 1)
            self.metadata_form_layout.addWidget(
                self.rating_details, 5, 2, 1, 2
            )
            self.metadata_form_layout.addWidget(self.description_check, 6, 0)
            self.metadata_form_layout.addWidget(
                self.description_edit, 6, 1, 1, 3
            )
            self.batch_review_list.setMaximumHeight(118)
        else:
            self.review_content_layout.setStretch(0, 1)
            self.review_content_layout.setStretch(1, 1)
            self.page_layout.setContentsMargins(28, 22, 28, 20)
            self.page_layout.setSpacing(10)
            self.metadata_form_layout.setContentsMargins(12, 10, 12, 8)
            self.metadata_form_layout.setVerticalSpacing(5)
            self._resize_description_editor()
            self.cover_preview.setFixedSize(96, 128)
            self.cover_panel.setMinimumHeight(138)
            self.download_cover_button.setMinimumWidth(174)
            self.find_covers_button.setMinimumWidth(150)
            self.local_cover_button.setMinimumWidth(174)
            self.download_cover_button.setStyleSheet("")
            self.find_covers_button.setStyleSheet("")
            self.local_cover_button.setStyleSheet("")
            for button in (
                self.queue_button,
                self.lookup_button,
                self.next_prepared_button,
                self.prepare_folder_button,
                self.prepare_queue_button,
            ):
                button.setStyleSheet("")
            for field in (
                "title",
                "author",
                "series",
                "series_number",
                "series_group",
                "series_group_number",
            ):
                self.field_editors[field].setMinimumHeight(0)
            self.metadata_form_layout.addWidget(
                self.field_checks["series"], 2, 2
            )
            self.metadata_form_layout.addWidget(
                self.field_editors["series"], 2, 3
            )
            self.metadata_form_layout.addWidget(
                self.field_checks["series_number"], 3, 2
            )
            self.metadata_form_layout.addWidget(
                self.field_editors["series_number"], 3, 3
            )
            self.metadata_form_layout.addWidget(
                self.field_checks["series_group"], 4, 0
            )
            self.metadata_form_layout.addWidget(
                self.field_editors["series_group"], 4, 1
            )
            self.metadata_form_layout.addWidget(
                self.field_checks["series_group_number"], 4, 2
            )
            self.metadata_form_layout.addWidget(
                self.field_editors["series_group_number"], 4, 3
            )
            self.metadata_form_layout.addWidget(self.rating_check, 5, 0)
            self.metadata_form_layout.addWidget(self.rating_edit, 5, 1)
            self.metadata_form_layout.addWidget(
                self.rating_details, 5, 2, 1, 2
            )
            self.metadata_form_layout.addWidget(self.description_check, 6, 0)
            self.metadata_form_layout.addWidget(
                self.description_edit, 6, 1, 1, 3
            )
            self.batch_review_list.setMaximumHeight(96)
        displayed_cover = (
            self.preview_cover_path or self.cover_path_edit.text().strip()
        )
        if displayed_cover:
            self._show_cover(displayed_cover)
        QTimer.singleShot(0, self._resize_description_editor)
        super().resizeEvent(event)

    def _resize_description_editor(self) -> None:
        """Grow readable descriptions while keeping the page screen-bounded."""
        if not hasattr(self, "description_edit"):
            return
        compact = self.width() < 900 or self.height() < 650
        if compact:
            self.description_edit.setFixedHeight(42)
            return

        # QTextDocument reports its wrapped height using the current viewport
        # width. Add the editor frame/padding, then cap growth so exceptionally
        # long summaries use the field's own scrollbar rather than making the
        # complete Metadata page scroll.
        content_height = ceil(
            self.description_edit.document().documentLayout()
            .documentSize()
            .height()
        )
        chrome_height = self.description_edit.frameWidth() * 2 + 18
        minimum_height = 72
        maximum_height = (
            min(200, max(150, round(self.height() * 0.17)))
            if self.width() >= 1200 and self.height() >= 850
            else min(132, max(96, round(self.height() * 0.16)))
        )
        target_height = max(
            minimum_height,
            min(maximum_height, content_height + chrome_height),
        )
        self.description_edit.setMinimumHeight(target_height)
        self.description_edit.setMaximumHeight(target_height)

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        selected_id = (
            self.current_book.book_id if self.current_book is not None else 0
        )
        records = self.service.list_books()
        selected_provider = str(self.provider_combo.currentData() or "")
        provider_choices = getattr(
            self.service,
            "metadata_provider_choices",
            None,
        )
        choices = (
            provider_choices()
            if callable(provider_choices)
            else (("", "All active providers"),)
        )
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        for plugin_id, label in choices:
            self.provider_combo.addItem(label, plugin_id)
        selected_provider_index = self.provider_combo.findData(
            selected_provider
        )
        self.provider_combo.setCurrentIndex(
            selected_provider_index if selected_provider_index >= 0 else 0
        )
        self.provider_combo.blockSignals(False)
        self.book_combo.blockSignals(True)
        self.book_combo.clear()
        for record in records:
            self.book_combo.addItem(
                f"{record.title} — {record.author}",
                record,
            )
        self.book_combo.blockSignals(False)
        if not records:
            self.current_book = None
            self.original_path_edit.clear()
            self.original_path_edit.setToolTip("")
            self.new_path_edit.clear()
            self.new_path_edit.setToolTip("")
            self.lookup_button.setEnabled(False)
            self.find_covers_button.setEnabled(False)
            self.preview_button.setEnabled(False)
            self.manual_review_button.setEnabled(False)
            self.delete_book_button.setEnabled(False)
            self.status_label.setText(
                "The metadata review queue is empty. Completed books remain "
                "available in Library and are hidden from this queue."
            )
            self._clear_fields()
            return
        self.lookup_button.setEnabled(True)
        self.find_covers_button.setEnabled(True)
        self.preview_button.setEnabled(True)
        self.manual_review_button.setEnabled(True)
        self.delete_book_button.setEnabled(True)
        index = next(
            (
                position
                for position in range(self.book_combo.count())
                if self.book_combo.itemData(position).book_id == selected_id
            ),
            0,
        )
        self.book_combo.setCurrentIndex(index)
        self._book_changed(index)

    def set_context(self, title: str = "") -> None:
        """Select a routed book from Library or Review Queue."""
        self.refresh()
        wanted = title.strip().casefold()
        if not wanted:
            return
        for index in range(self.book_combo.count()):
            record = self.book_combo.itemData(index)
            if isinstance(record, LibraryRecord) and (
                record.title.casefold() == wanted
            ):
                self.book_combo.setCurrentIndex(index)
                return

    def _book_changed(self, index: int) -> None:
        record = self.book_combo.itemData(index)
        self.current_book = record if isinstance(record, LibraryRecord) else None
        original_path = (
            self.current_book.file_path if self.current_book is not None else ""
        )
        self.original_path_edit.setText(original_path)
        self.original_path_edit.setToolTip(original_path)
        self.original_path_edit.setCursorPosition(0)
        self.new_path_edit.setText(original_path)
        self.new_path_edit.setToolTip(original_path)
        self.new_path_edit.setCursorPosition(0)
        self.current_plan_id = None
        self.apply_button.setEnabled(False)
        self.plan_summary.setText(
            "No changes are prepared for this book. Lookup does not change "
            "your catalogue."
        )
        self.organise_file_check.blockSignals(True)
        self.organise_file_check.setChecked(False)
        self.organise_file_check.blockSignals(False)
        self.manual_review_button.setEnabled(self.current_book is not None)
        self.delete_book_button.setEnabled(self.current_book is not None)
        self.find_covers_button.setEnabled(self.current_book is not None)
        self.results_list.clear()
        self.results_list.addItem(
            "Run Find Metadata & Covers to see matches",
            None,
        )
        self.source_assessment_label.clear()
        self.source_assessment_label.hide()
        self.cover_result_combo.clear()
        self.download_cover_button.setEnabled(False)
        self.preview_cover_path = ""
        self.preview_cover_candidate = None
        self.pending_cover_candidate = None
        self.pending_cover_fallback = False
        self.cover_fallback_attempted = False
        self.validated_cover_paths.clear()
        self.provider_summary = ""
        self.current_candidates = ()
        if self.current_book is None:
            self._clear_fields()
            return
        values = {
            "title": self.current_book.title,
            "author": self.current_book.author,
            "isbn": self.current_book.isbn,
            "publisher": self.current_book.publisher,
            "language": self.current_book.language,
            "published_date": clean_published_date(
                self.current_book.published_date
            ),
            "series": self.current_book.series,
            "series_number": (
                "" if self.current_book.series_number is None
                else _display_order_number(self.current_book.series_number)
            ),
            "series_group": self.current_book.series_group,
            "series_group_number": (
                "" if self.current_book.series_group_number is None
                else _display_order_number(
                    self.current_book.series_group_number
                )
            ),
            "description": self.current_book.description,
            "cover_path": self.current_book.cover_path,
        }
        self._populate_fields(values)
        self._show_cover(values["cover_path"])
        self.status_label.setText(
            "Ready to find book information and covers. Nothing changes "
            "until you preview and approve the reviewed fields."
        )
        if self.current_book.book_id in self.prepared_results:
            self._show_prepared_results(self.current_book.book_id)

    def _auto_next_preference_changed(self, checked: bool) -> None:
        current = self.preferences.load_metadata_preferences()
        self.preferences.save_metadata_preferences(
            replace(current, auto_lookup_next=bool(checked))
        )
        self.preferences.sync()

    def _prepare_or_cancel_review_queue(self) -> None:
        if self.batch_worker is not None:
            self.batch_worker.request_cancel()
            self.prepare_queue_button.setEnabled(False)
            self.prepare_queue_button.setText("Stopping…")
            self.status_label.setText(
                "Stopping after the current book lookup finishes…"
            )
            return
        if self.is_busy():
            QMessageBox.information(
                self,
                "Finish Current Task",
                "Finish or cancel the current metadata task before preparing "
                "the review queue.",
            )
            return
        list_all_books = getattr(self.service, "list_all_books", None)
        records = tuple(
            list_all_books() if callable(list_all_books) else self.service.list_books()
        )
        if not records:
            QMessageBox.information(
                self,
                "Catalogue Is Empty",
                "There are no catalogued books to recheck. Scan a library "
                "folder first.",
            )
            return
        self._confirm_and_start_review_queue(
            records,
            title="Recheck All Books for Metadata & Covers?",
            scope="catalogued books, including completed books",
        )

    def _prepare_folder_review_queue(self) -> None:
        if self.is_busy():
            QMessageBox.information(
                self,
                "Finish Current Task",
                "Finish or cancel the current metadata task before preparing "
                "a folder review queue.",
            )
            return
        folder_name = QFileDialog.getExistingDirectory(
            self,
            "Choose Folder to Rescan",
            str(Path(self.current_book.file_path).parent)
            if self.current_book is not None
            else "",
        )
        if not folder_name:
            return
        folder = Path(folder_name).resolve()
        records = tuple(
            record
            for record in self.service.list_all_books()
            if _path_is_beneath(record.file_path, folder)
        )
        if not records:
            QMessageBox.information(
                self,
                "No Catalogued Books",
                "That folder does not contain any books currently listed in "
                "Twano. Scan it on the Scan page first.",
            )
            return
        self._confirm_and_start_review_queue(
            records,
            title="Rescan Folder for Metadata & Covers?",
            scope=f"catalogued books beneath {folder}",
        )

    def _confirm_and_start_review_queue(
        self,
        records: tuple[LibraryRecord, ...],
        *,
        title: str,
        scope: str,
    ) -> None:
        answer = QMessageBox.question(
            self,
            title,
            f"Twano will search the enabled providers for {len(records):,} "
            f"{scope} using "
            f"{self.provider_combo.currentText()}.\n\nThis can take a long "
            "time and use "
            "provider allowances. It does not change metadata, covers, "
            "filenames, or folders. You can cancel safely at any time.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        metadata_preferences = self.preferences.load_metadata_preferences()
        self.prepared_results.clear()
        self.prepared_reports.clear()
        self.prepared_failures.clear()
        self.prepared_records = {
            record.book_id: record for record in records
        }
        self.prepared_decisions.clear()
        self.batch_review_list.clear()
        self.batch_review_panel.show()
        self.queue_status_label.setText(
            f"Preparing 0 of {len(records):,}"
        )
        self._set_busy(True, "Preparing metadata review queue…")
        self.progress.setRange(0, len(records))
        self.progress.setValue(0)
        self.prepare_queue_button.setEnabled(True)
        self.prepare_queue_button.setText("Cancel Recheck")
        self.batch_thread = QThread(self)
        self.batch_worker = MetadataBatchLookupWorker(
            self.service,
            records,
            cache_days=metadata_preferences.cache_days,
            include_open_library=(
                metadata_preferences.open_library_enabled
            ),
            provider_plugin_id=str(
                self.provider_combo.currentData() or ""
            ),
        )
        self.batch_worker.moveToThread(self.batch_thread)
        self.batch_thread.started.connect(self.batch_worker.run)
        self.batch_worker.result_ready.connect(self._batch_result_ready)
        self.batch_worker.book_failed.connect(self._batch_book_failed)
        self.batch_worker.progress_changed.connect(self._batch_progress)
        self.batch_worker.completed.connect(self._batch_completed)
        self.batch_worker.cancelled.connect(self._batch_cancelled)
        self.batch_worker.finished.connect(self.batch_thread.quit)
        self.batch_worker.finished.connect(self.batch_worker.deleteLater)
        self.batch_thread.finished.connect(self._batch_thread_finished)
        self.batch_thread.finished.connect(self.batch_thread.deleteLater)
        self.batch_thread.start()

    def _batch_result_ready(
        self,
        book_id: int,
        candidates: tuple[MetadataCandidate, ...],
        report: ProviderSearchReport,
    ) -> None:
        self.prepared_results[int(book_id)] = tuple(candidates)
        self.prepared_reports[int(book_id)] = report
        self._upsert_batch_review_item(int(book_id))

    def _batch_book_failed(self, book_id: int, message: str) -> None:
        self.prepared_failures[int(book_id)] = str(message)
        self._upsert_batch_review_item(int(book_id))

    def _batch_progress(
        self,
        processed: int,
        total: int,
        message: str,
    ) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(processed)
        self.progress.show()
        self.queue_status_label.setText(
            f"Preparing {processed:,} of {total:,}"
        )
        self.status_label.setText(message)

    def _batch_completed(self, processed: int, matched: int) -> None:
        no_match = sum(
            1 for candidates in self.prepared_results.values() if not candidates
        )
        failed = len(self.prepared_failures)
        self.queue_status_label.setText(
            f"{matched:,} with matches, {no_match:,} without, "
            f"{failed:,} failed"
        )
        self.status_label.setText(
            f"Scanned {processed:,} books safely. Click any book in the "
            "results list, then accept or reject its findings."
        )
        self._select_first_batch_review_item()

    def _batch_cancelled(self, processed: int, matched: int) -> None:
        self.queue_status_label.setText(
            f"Stopped: {processed:,} prepared, {matched:,} with matches"
        )
        self.status_label.setText(
            "Queue preparation stopped safely. Prepared results remain "
            "available for manual review."
        )
        self._select_first_batch_review_item()

    def _batch_thread_finished(self) -> None:
        self.batch_thread = None
        self.batch_worker = None
        self.prepare_queue_button.setText("Recheck All Books")
        self._set_busy(False)
        self.prepare_queue_button.setEnabled(True)
        self.next_prepared_button.setEnabled(bool(self.prepared_results))
        if self.current_book is not None:
            self._show_prepared_results(self.current_book.book_id)
        self.work_stopped.emit()

    def _upsert_batch_review_item(self, book_id: int) -> None:
        record = self.prepared_records.get(book_id)
        if record is None:
            return
        item = next(
            (
                self.batch_review_list.item(index)
                for index in range(self.batch_review_list.count())
                if self.batch_review_list.item(index).data(
                    Qt.ItemDataRole.UserRole
                ) == book_id
            ),
            None,
        )
        if item is None:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, book_id)
            self.batch_review_list.addItem(item)
        decision = self.prepared_decisions.get(book_id, "")
        candidates = self.prepared_results.get(book_id)
        if decision == "applied":
            status = "APPLIED"
        elif decision == "accepted":
            status = "ACCEPTED FOR PREVIEW"
        elif decision == "rejected":
            status = "REJECTED"
        elif book_id in self.prepared_failures:
            status = "SEARCH FAILED"
        elif candidates:
            covers = sum(
                1
                for candidate in candidates
                if candidate.cover_url and candidate.confidence >= 75
            )
            status = f"READY - {len(candidates)} matches, {covers} covers"
        else:
            status = "NO MATCH"
        item.setText(f"{status} | {record.title} - {record.author}")

    def _select_first_batch_review_item(self) -> None:
        if self.batch_review_list.count():
            self.batch_review_list.setCurrentRow(0)

    def _batch_review_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        book_id = (
            current.data(Qt.ItemDataRole.UserRole)
            if current is not None
            else None
        )
        if not isinstance(book_id, int):
            self.accept_prepared_button.setEnabled(False)
            self.reject_prepared_button.setEnabled(False)
            return
        self._select_book_by_id(book_id)
        candidates = self.prepared_results.get(book_id, ())
        failed = self.prepared_failures.get(book_id, "")
        self.accept_prepared_button.setEnabled(bool(candidates))
        self.reject_prepared_button.setEnabled(True)
        if candidates:
            self._show_prepared_results(book_id)
        elif failed:
            self.status_label.setText(
                f"Search failed for this book: {failed} No changes were made."
            )
        else:
            self._present_lookup_candidates(
                (),
                report=self.prepared_reports.get(
                    book_id,
                    ProviderSearchReport(),
                ),
                prepared=True,
            )

    def _accept_prepared_result(self) -> None:
        if self.current_book is None:
            return
        book_id = self.current_book.book_id
        if not self.prepared_results.get(book_id):
            return
        self._preview_changes()
        if self.current_plan_id is not None:
            self.prepared_decisions[book_id] = "accepted"
            self._upsert_batch_review_item(book_id)

    def _reject_prepared_result(self) -> None:
        if self.current_book is None:
            return
        book_id = self.current_book.book_id
        self.prepared_decisions[book_id] = "rejected"
        self.current_plan_id = None
        self.apply_button.setEnabled(False)
        self._upsert_batch_review_item(book_id)
        self.status_label.setText(
            "Result rejected for this review session. The catalogue and "
            "ebook file were not changed."
        )
        current_row = self.batch_review_list.currentRow()
        for offset in range(1, self.batch_review_list.count() + 1):
            row = (current_row + offset) % self.batch_review_list.count()
            item = self.batch_review_list.item(row)
            candidate_id = item.data(Qt.ItemDataRole.UserRole)
            if self.prepared_decisions.get(candidate_id) not in {
                "accepted",
                "rejected",
            }:
                self.batch_review_list.setCurrentRow(row)
                break

    def _show_prepared_results(self, book_id: int) -> None:
        candidates = self.prepared_results.get(int(book_id))
        if candidates is None:
            return
        report = self.prepared_reports.get(
            int(book_id),
            ProviderSearchReport(),
        )
        self._present_lookup_candidates(
            candidates,
            report=report,
            prepared=True,
        )

    def _select_next_prepared_result(self) -> None:
        prepared_ids = tuple(
            book_id
            for book_id in self.prepared_results
            if any(
                isinstance(self.book_combo.itemData(index), LibraryRecord)
                and self.book_combo.itemData(index).book_id == book_id
                for index in range(self.book_combo.count())
            )
        )
        if not prepared_ids:
            self.next_prepared_button.setEnabled(False)
            return
        current_id = (
            self.current_book.book_id if self.current_book is not None else 0
        )
        try:
            next_index = (prepared_ids.index(current_id) + 1) % len(
                prepared_ids
            )
        except ValueError:
            next_index = 0
        self._select_book_by_id(prepared_ids[next_index])

    def _start_lookup(self) -> None:
        if self.current_book is None or self.lookup_thread is not None:
            return
        self.pending_cover_fallback = False
        self.cover_fallback_attempted = False
        metadata_preferences = self.preferences.load_metadata_preferences()
        self._set_busy(
            True,
            "Searching for book information and covers together…",
        )
        self.lookup_thread = QThread(self)
        self.lookup_worker = MetadataLookupWorker(
            self.service,
            title=self.current_book.title,
            author=(
                "" if self.current_book.author == "Unknown"
                else self.current_book.author
            ),
            isbn=self.current_book.isbn,
            file_name=self.current_book.file_path,
            book_id=self.current_book.book_id,
            cache_days=metadata_preferences.cache_days,
            include_open_library=(
                metadata_preferences.open_library_enabled
            ),
            provider_plugin_id=str(
                self.provider_combo.currentData() or ""
            ),
        )
        self.lookup_worker.moveToThread(self.lookup_thread)
        self.lookup_thread.started.connect(self.lookup_worker.run)
        self.lookup_worker.candidates_ready.connect(self._lookup_completed)
        self.lookup_worker.failed.connect(self._lookup_failed)
        self.lookup_worker.finished.connect(self.lookup_thread.quit)
        self.lookup_worker.finished.connect(self.lookup_worker.deleteLater)
        self.lookup_thread.finished.connect(self._lookup_thread_finished)
        self.lookup_thread.finished.connect(self.lookup_thread.deleteLater)
        self.lookup_thread.start()
        self.lookup_elapsed_seconds = 0
        self.lookup_status_timer.start()

    def _start_cover_lookup(self) -> None:
        """Search covers independently using the reviewed metadata fields."""
        if self.current_book is None or self.lookup_thread is not None:
            return
        self.pending_cover_fallback = False
        self.cover_fallback_attempted = True
        metadata_preferences = self.preferences.load_metadata_preferences()
        title_editor = self.field_editors.get("title")
        author_editor = self.field_editors.get("author")
        isbn_editor = self.field_editors.get("isbn")
        title = (
            title_editor.text().strip()
            if isinstance(title_editor, QLineEdit)
            else ""
        )
        author = (
            author_editor.text().strip()
            if isinstance(author_editor, QLineEdit)
            else ""
        )
        isbn = (
            isbn_editor.text().strip()
            if isinstance(isbn_editor, QLineEdit)
            else ""
        )
        if not any((title, author, isbn)):
            self.status_label.setText(
                "Enter or select a title, author, or ISBN before searching "
                "for covers."
            )
            return

        self._set_busy(True, "Searching all active cover providers\u2026")
        self.lookup_thread = QThread(self)
        self.lookup_worker = MetadataLookupWorker(
            self.service,
            title=title,
            author=author,
            isbn=isbn,
            file_name=self.current_book.file_path,
            cover_source_id="automatic",
            book_id=self.current_book.book_id,
            cache_days=metadata_preferences.cache_days,
            include_open_library=(
                metadata_preferences.open_library_enabled
            ),
        )
        self.lookup_worker.moveToThread(self.lookup_thread)
        self.lookup_thread.started.connect(self.lookup_worker.run)
        self.lookup_worker.candidates_ready.connect(
            self._cover_lookup_completed
        )
        self.lookup_worker.failed.connect(self._lookup_failed)
        self.lookup_worker.finished.connect(self.lookup_thread.quit)
        self.lookup_worker.finished.connect(self.lookup_worker.deleteLater)
        self.lookup_thread.finished.connect(self._lookup_thread_finished)
        self.lookup_thread.finished.connect(self.lookup_thread.deleteLater)
        self.lookup_thread.start()

    def _cover_lookup_completed(
        self,
        candidates: tuple[MetadataCandidate, ...],
    ) -> None:
        """Show cover-only results without replacing reviewed metadata."""
        usable = tuple(
            candidate
            for candidate in candidates
            if candidate.cover_url and candidate.confidence >= 75
        )
        self.preview_cover_path = ""
        self.preview_cover_candidate = None
        self.pending_cover_candidate = None
        self.validated_cover_paths.clear()
        self.cover_result_combo.blockSignals(True)
        self.cover_result_combo.clear()
        for candidate in usable:
            self.cover_result_combo.addItem(
                f"{candidate.provider_name}: {candidate.title} \u2014 "
                f"{candidate.author or 'Unknown author'} "
                f"({candidate.confidence}%)",
                candidate,
            )
        self.cover_result_combo.blockSignals(False)
        self.download_cover_button.setEnabled(False)
        if usable:
            self._set_cover_preview_text("Loading cover\npreview\u2026")
            self.pending_cover_candidate = usable[0]
            cover_word = "cover" if len(usable) == 1 else "covers"
            self.status_label.setText(
                f"Found {len(usable)} matching {cover_word}. Loading the "
                "first available preview. Your metadata was not changed."
            )
        else:
            self._set_cover_preview_text("No cover\nfound")
            self.status_label.setText(
                "No matching cover was found by the active cover providers. "
                "Your selected metadata remains unchanged; you can edit the "
                "title or author and try again, or choose Cover File."
            )

    def _lookup_completed(
        self,
        candidates: tuple[MetadataCandidate, ...],
    ) -> None:
        self.lookup_status_timer.stop()
        self._present_lookup_candidates(
            candidates,
            report=self.service.last_search_report,
        )

    def _present_lookup_candidates(
        self,
        candidates: tuple[MetadataCandidate, ...],
        *,
        report: ProviderSearchReport,
        prepared: bool = False,
    ) -> None:
        incoming_cover_candidates = tuple(
            candidate
            for candidate in candidates
            if candidate.cover_url and candidate.confidence >= 75
        )
        retained_cover_path = self.cover_path_edit.text().strip()
        retained_preview_path = self.preview_cover_path
        retained_cover_candidate = self.preview_cover_candidate
        if retained_cover_candidate is None:
            selected_cover = self.cover_result_combo.currentData()
            if isinstance(selected_cover, MetadataCandidate):
                retained_cover_candidate = selected_cover
        retain_selected_cover = bool(
            retained_cover_path
            and Path(retained_cover_path).is_file()
            and not incoming_cover_candidates
        )
        retained_validated_paths = dict(self.validated_cover_paths)

        self.current_candidates = tuple(candidates)
        self.preview_cover_path = ""
        self.preview_cover_candidate = None
        self.pending_cover_candidate = None
        self.validated_cover_paths.clear()
        self.results_list.blockSignals(True)
        self.cover_result_combo.blockSignals(True)
        self.results_list.clear()
        self.cover_result_combo.clear()
        for candidate in self.current_candidates:
            self.results_list.addItem(
                _candidate_display_text(candidate),
                candidate,
            )
            if candidate.cover_url and candidate.confidence >= 75:
                self.cover_result_combo.addItem(
                    _candidate_display_text(candidate),
                    candidate,
                )
        if retain_selected_cover:
            self.preview_cover_path = (
                retained_preview_path or retained_cover_path
            )
            self.preview_cover_candidate = retained_cover_candidate
            self.validated_cover_paths.update(retained_validated_paths)
            if (
                retained_cover_candidate is not None
                and retained_cover_candidate.cover_url
            ):
                self.cover_result_combo.addItem(
                    _candidate_display_text(retained_cover_candidate),
                    retained_cover_candidate,
                )
        self.results_list.blockSignals(False)
        self.download_cover_button.setEnabled(False)
        self.provider_summary = _provider_summary_text(
            report.searched_providers,
            report.failed_providers,
            report.cover_providers,
            report.failure_details,
        )
        if self.current_candidates:
            self.results_list.setCurrentIndex(0)
            self._candidate_changed(0)
            match_word = (
                "match" if len(self.current_candidates) == 1 else "matches"
            )
            cover_word = (
                "cover" if self.cover_result_combo.count() == 1 else "covers"
            )
            self.status_label.setText(
                f"{'Prepared queue search' if prepared else 'One search'} "
                f"found {len(self.current_candidates)} possible "
                f"{match_word} and {self.cover_result_combo.count()} "
                f"{cover_word}. "
                f"{'Providers disagree on the series; choose the result you trust. ' if _has_series_conflict(self.current_candidates) else ''}"
                f"{self.provider_summary}"
            )
            if incoming_cover_candidates:
                self._set_cover_preview_text("Loading cover\npreview…")
                selected_cover = self.cover_result_combo.currentData()
                if isinstance(selected_cover, MetadataCandidate):
                    self.pending_cover_candidate = selected_cover
            elif retain_selected_cover:
                self._show_cover(
                    retained_preview_path or retained_cover_path
                )
                self.status_label.setText(
                    "The metadata search found no replacement cover, so "
                    "Twano kept the cover already selected from the cover "
                    f"search. {self.provider_summary}"
                )
            else:
                self._set_cover_preview_text("No cover\nfound")
                if not prepared and not self.cover_fallback_attempted:
                    self.pending_cover_fallback = True
                    self.status_label.setText(
                        "The metadata providers found no usable cover. "
                        "Checking every active cover provider now…"
                    )
        else:
            self.results_list.addItem("No matches found", None)
            if retain_selected_cover:
                self._show_cover(
                    retained_preview_path or retained_cover_path
                )
                self.status_label.setText(
                    "No new metadata match or replacement cover was found. "
                    "Twano kept the cover already selected from the cover "
                    f"search. {self.provider_summary}"
                )
            else:
                self._set_cover_preview_text("No cover\nfound")
                self.status_label.setText(
                    f"{'Prepared queue search: ' if prepared else ''}No "
                    "confident match or cover was found. You can edit the "
                    "fields yourself or choose a cover file from your "
                    f"computer. {self.provider_summary}"
                )
        self.cover_result_combo.blockSignals(False)
        if (
            prepared
            and self.pending_cover_candidate is not None
            and self.batch_thread is None
            and self.lookup_thread is None
        ):
            pending_cover = self.pending_cover_candidate
            self.pending_cover_candidate = None
            QTimer.singleShot(
                0,
                lambda candidate=pending_cover: self._start_cover_preview(
                    candidate
                ),
            )

    def _lookup_failed(self, message: str) -> None:
        self.lookup_status_timer.stop()
        self.pending_cover_candidate = None
        self.status_label.setText(message)

    def _update_lookup_elapsed(self) -> None:
        """Make a slow online lookup visibly active without blocking the UI."""
        if self.lookup_thread is None:
            self.lookup_status_timer.stop()
            return
        self.lookup_elapsed_seconds += 1
        self.status_label.setText(
            "Searching active metadata and cover providers in parallel… "
            f"{self.lookup_elapsed_seconds} seconds. Twano is still working; "
            "no book files are being changed."
        )

    def _lookup_thread_finished(self) -> None:
        self.lookup_status_timer.stop()
        pending_cover = self.pending_cover_candidate
        self.pending_cover_candidate = None
        pending_cover_fallback = self.pending_cover_fallback
        self.pending_cover_fallback = False
        self.lookup_thread = None
        self.lookup_worker = None
        self._set_busy(False)
        if pending_cover is not None:
            QTimer.singleShot(
                0,
                lambda candidate=pending_cover: self._start_cover_preview(
                    candidate
                ),
            )
        elif pending_cover_fallback:
            QTimer.singleShot(0, self._start_cover_lookup)
        else:
            self.work_stopped.emit()

    def _candidate_changed(
        self,
        index: int,
    ) -> None:
        candidate = self.results_list.itemData(index)
        if not isinstance(candidate, MetadataCandidate):
            self.source_assessment_label.clear()
            self.source_assessment_label.hide()
            return
        values = {
            "title": candidate.title,
            "author": candidate.author,
            "isbn": candidate.isbn,
            "publisher": candidate.publisher,
            "language": candidate.language,
            "published_date": candidate.published_date,
            "series": candidate.series,
            "series_number": _display_order_number(candidate.series_number),
            "series_group": candidate.series_group,
            "series_group_number": _display_order_number(
                candidate.series_group_number
            ),
            "provider_rating": (
                f"{candidate.provider_rating:.2f}"
                if candidate.provider_rating > 0
                else ""
            ),
        }
        self.rating_check.setChecked(candidate.provider_rating > 0)
        self.rating_details.setText(
            (
                f"from {candidate.provider_name}"
                + (
                    f" · {candidate.rating_count:,} ratings"
                    if candidate.rating_count > 0
                    else ""
                )
            )
            if candidate.provider_rating > 0
            else "No website rating was returned for this match."
        )
        if (
            candidate.series
            and not str(candidate.series_number).strip()
            and self.current_book is not None
        ):
            values["series_number"] = _leading_series_number(
                self.current_book.file_name or self.current_book.file_path
            )
        for field, value in (
            ("description", candidate.description),
        ):
            if value:
                values[field] = value
        self._populate_fields(values)
        self._update_source_assessment(candidate)
        self._select_organisation_for_candidate(candidate)
        self._update_new_file_path()
        matching_cover_index = self._matching_cover_index(candidate)
        if matching_cover_index >= 0:
            self.cover_result_combo.setCurrentIndex(matching_cover_index)
        self.current_plan_id = None
        self.apply_button.setEnabled(False)

    def _update_source_assessment(
        self,
        candidate: MetadataCandidate,
    ) -> None:
        """Show where the selected result agrees or conflicts."""
        if self.current_book is None:
            self.source_assessment_label.clear()
            self.source_assessment_label.hide()
            return
        assess_candidate_sources = getattr(
            self.service, "assess_candidate_sources", None
        )
        if not callable(assess_candidate_sources):
            self.source_assessment_label.clear()
            self.source_assessment_label.hide()
            return
        assessment = assess_candidate_sources(
            self.current_book,
            candidate,
            self.current_candidates,
        )
        self.source_assessment_label.setText(assessment.summary)
        colour = "#f0b45a" if assessment.needs_manual_review else "#8fd19e"
        self.source_assessment_label.setStyleSheet(f"color: {colour};")
        self.source_assessment_label.setVisible(bool(assessment.summary))

    def _select_organisation_for_candidate(
        self,
        candidate: MetadataCandidate,
    ) -> None:
        """Select safe Author/Series organisation for a usable match."""
        author = " ".join(candidate.author.split())
        title = " ".join(candidate.title.split())
        usable_author = bool(author) and author.casefold() not in {
            "unknown",
            "unknown author",
        }
        should_organise = bool(title and usable_author)
        self.organise_file_check.blockSignals(True)
        self.organise_file_check.setChecked(should_organise)
        self.organise_file_check.blockSignals(False)
        if not should_organise:
            self.plan_summary.setText(
                "No usable author was found, so file organisation was not "
                "selected automatically."
            )
            return
        if candidate.series:
            detail = "the shared -=Series=- folder"
            if not str(candidate.series_number).strip():
                detail += "; add the series number before Preview"
        else:
            detail = "the Author folder"
        self.plan_summary.setText(
            "File organisation was selected automatically. Preview "
            f"Selected Changes to confirm the exact path in {detail}."
        )

    def _cover_candidate_changed(self, index: int) -> None:
        candidate = self.cover_result_combo.itemData(index)
        if isinstance(candidate, MetadataCandidate):
            validated_path = self.validated_cover_paths.get(
                candidate.cover_url
            )
            if validated_path:
                self.preview_cover_path = validated_path
                self.preview_cover_candidate = candidate
                self._show_cover(validated_path)
                self._select_preview_cover(validated_path)
                self.download_cover_button.setEnabled(
                    self.lookup_thread is None
                    and self.current_book is not None
                )
                self.status_label.setText(
                    f"Showing {candidate.provider_name}: "
                    f"{candidate.title}. This cover will be applied with the "
                    "reviewed metadata. "
                    f"{self.provider_summary}"
                )
                return
            self.preview_cover_path = ""
            self.preview_cover_candidate = None
            self.download_cover_button.setEnabled(False)
            self._set_cover_preview_text("Loading cover\npreview…")
            self.status_label.setText(
                f"Loading the {candidate.provider_name} cover preview for "
                f"{candidate.title}."
            )
            if self.lookup_thread is None:
                self._start_cover_preview(candidate)
            else:
                self.pending_cover_candidate = candidate

    def _matching_cover_index(self, candidate: MetadataCandidate) -> int:
        wanted_title = _normalised_match_text(candidate.title)
        wanted_author = _normalised_match_text(candidate.author)
        title_match = -1
        for index in range(self.cover_result_combo.count()):
            cover = self.cover_result_combo.itemData(index)
            if not isinstance(cover, MetadataCandidate):
                continue
            if cover is candidate:
                return index
            if _normalised_match_text(cover.title) != wanted_title:
                continue
            if (
                wanted_author
                and _normalised_match_text(cover.author) == wanted_author
            ):
                return index
            if title_match < 0:
                title_match = index
        return title_match

    def _next_unvalidated_cover_index(self) -> int:
        for index in range(self.cover_result_combo.count()):
            candidate = self.cover_result_combo.itemData(index)
            if (
                isinstance(candidate, MetadataCandidate)
                and candidate.cover_url not in self.validated_cover_paths
            ):
                return index
        return -1

    def _select_cover_without_loading(self, index: int) -> None:
        self.cover_result_combo.blockSignals(True)
        self.cover_result_combo.setCurrentIndex(index)
        self.cover_result_combo.blockSignals(False)

    def _start_cover_preview(self, candidate: MetadataCandidate) -> None:
        if self.current_book is None or self.lookup_thread is not None:
            return
        self.pending_cover_candidate = None
        self._set_busy(True, "Loading the selected cover preview…")
        self.lookup_thread = QThread(self)
        self.lookup_worker = MetadataLookupWorker(
            self.service,
            cover_candidate=candidate,
            book_id=self.current_book.book_id,
            preview_cover=True,
        )
        self.lookup_worker.moveToThread(self.lookup_thread)
        self.lookup_thread.started.connect(self.lookup_worker.run)
        self.lookup_worker.cover_ready.connect(
            self._cover_preview_downloaded
        )
        self.lookup_worker.failed.connect(self._cover_preview_failed)
        self.lookup_worker.finished.connect(self.lookup_thread.quit)
        self.lookup_worker.finished.connect(self.lookup_worker.deleteLater)
        self.lookup_thread.finished.connect(self._lookup_thread_finished)
        self.lookup_thread.finished.connect(self.lookup_thread.deleteLater)
        self.lookup_thread.start()

    def _cover_preview_downloaded(self, path: str) -> None:
        candidate = self.cover_result_combo.currentData()
        if not isinstance(candidate, MetadataCandidate):
            return
        self.pending_cover_candidate = None
        self.validated_cover_paths[candidate.cover_url] = path
        self.preview_cover_path = path
        self.preview_cover_candidate = candidate
        self._show_cover(path)
        self._select_preview_cover(path)
        self.download_cover_button.setEnabled(
            self.lookup_thread is None and self.current_book is not None
        )
        self.status_label.setText(
            f"Showing {candidate.provider_name}: {candidate.title}. "
            "This cover will be applied with the reviewed metadata. "
            f"{self.provider_summary}"
        )

    def _select_preview_cover(self, path: str) -> None:
        """Include a successfully previewed online cover in the same Apply."""
        self.cover_path_edit.setText(path)
        self.field_checks["cover_path"].setChecked(True)
        self.current_plan_id = None
        self.apply_button.setEnabled(False)

    def _cover_preview_failed(self, message: str) -> None:
        self.preview_cover_path = ""
        self.preview_cover_candidate = None
        failed_index = self.cover_result_combo.currentIndex()
        failed_candidate = self.cover_result_combo.currentData()
        if isinstance(failed_candidate, MetadataCandidate):
            self.cover_result_combo.blockSignals(True)
            self.cover_result_combo.removeItem(failed_index)
            self.cover_result_combo.blockSignals(False)
        next_index = self._next_unvalidated_cover_index()
        next_candidate = (
            self.cover_result_combo.itemData(next_index)
            if next_index >= 0
            else None
        )

        if isinstance(next_candidate, MetadataCandidate):
            self._select_cover_without_loading(next_index)
            self.pending_cover_candidate = next_candidate
            self._set_cover_preview_text("Checking next\ncover…")
            self.status_label.setText(
                f"{message} That unavailable option was removed. "
                "Checking the next found cover."
            )
            return

        self.pending_cover_candidate = None
        if self.cover_result_combo.count():
            self._select_cover_without_loading(0)
            remaining_candidate = self.cover_result_combo.currentData()
            if isinstance(remaining_candidate, MetadataCandidate):
                remaining_path = self.validated_cover_paths.get(
                    remaining_candidate.cover_url,
                    "",
                )
                if remaining_path:
                    self.preview_cover_path = remaining_path
                    self.preview_cover_candidate = remaining_candidate
                    self._show_cover(remaining_path)
            self.status_label.setText(
                f"{message} That unavailable option was removed. "
                f"{self.cover_result_combo.count()} usable cover "
                f"{'remains' if self.cover_result_combo.count() == 1 else 'remain'}."
            )
            return
        self.download_cover_button.setEnabled(False)
        self._set_cover_preview_text("No cover\nfound")
        if not self.cover_fallback_attempted:
            self.pending_cover_fallback = True
            self.status_label.setText(
                f"{message} No usable online cover was found in the initial "
                "results. Checking every other active cover provider now…"
            )
        else:
            self.status_label.setText(
                f"{message} No usable online cover was found. Choose Cover "
                "File to select one from this computer. "
                f"{self.provider_summary}"
            )

    def _start_cover_download(self) -> None:
        candidate = self.cover_result_combo.currentData()
        if (
            self.current_book is None
            or not isinstance(candidate, MetadataCandidate)
            or self.lookup_thread is not None
        ):
            self.status_label.setText(
                "Run Find Metadata & Covers and select a found cover first."
            )
            return
        self._set_busy(True, "Selecting the displayed cover…")
        self.lookup_thread = QThread(self)
        self.lookup_worker = MetadataLookupWorker(
            self.service,
            cover_candidate=candidate,
            book_id=self.current_book.book_id,
        )
        self.lookup_worker.moveToThread(self.lookup_thread)
        self.lookup_thread.started.connect(self.lookup_worker.run)
        self.lookup_worker.cover_ready.connect(self._cover_downloaded)
        self.lookup_worker.failed.connect(self._lookup_failed)
        self.lookup_worker.finished.connect(self.lookup_thread.quit)
        self.lookup_worker.finished.connect(self.lookup_worker.deleteLater)
        self.lookup_thread.finished.connect(self._lookup_thread_finished)
        self.lookup_thread.finished.connect(self.lookup_thread.deleteLater)
        self.lookup_thread.start()

    def _cover_downloaded(self, path: str) -> None:
        self.cover_path_edit.setText(path)
        self._show_cover(path)
        self.current_plan_id = None
        self.apply_button.setEnabled(False)
        self.status_label.setText(
            "Cover selected. Preview Selected Changes to add it to the "
            "catalogue."
        )

    def _choose_local_cover(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose Book Cover",
            "",
            "Images (*.jpg *.jpeg *.png *.webp)",
        )
        if path:
            self.cover_path_edit.setText(path)
            self._show_cover(path)
            self.current_plan_id = None
            self.apply_button.setEnabled(False)

    def _preview_changes(self) -> None:
        if self.current_book is None:
            return
        values: dict[str, object] = {}
        for field, checkbox in self.field_checks.items():
            if not checkbox.isChecked():
                continue
            editor = self.field_editors[field]
            if isinstance(editor, QLineEdit):
                values[field] = editor.text().strip()
            elif isinstance(editor, QTextEdit):
                values[field] = editor.toPlainText().strip()
        selected_candidate = self.results_list.currentData()
        if (
            "provider_rating" in values
            and isinstance(selected_candidate, MetadataCandidate)
        ):
            values["rating_count"] = selected_candidate.rating_count
            values["rating_source"] = selected_candidate.provider_name
        try:
            operation = self.service.build_plan(
                self.current_book.book_id,
                values,
                organise_file=self.organise_file_check.isChecked(),
            )
        except Exception as error:
            self.current_plan_id = None
            self.apply_button.setEnabled(False)
            message = str(error)
            if (
                message
                == "The selected metadata and organised file path already "
                "match the catalogue."
                and self._mark_current_book_complete_if_ready()
            ):
                return
            self.plan_summary.setText(message)
            self.status_label.setText(
                "Preview could not be prepared. Review the explanation "
                "shown above the buttons."
            )
            QMessageBox.warning(
                self,
                "Cannot Prepare Preview",
                message,
            )
            return
        self.current_plan_id = operation.operation_id
        self.plan_summary.setText(
            operation.plan.summary
            + "\n"
            + " ".join(operation.plan.warnings)
        )
        self.apply_button.setEnabled(True)
        self.status_label.setText(
            "Preview ready. Review the summary, then Apply Reviewed Changes "
            "when you are satisfied."
        )

    def _mark_current_book_complete_if_ready(self) -> bool:
        """Retire a legacy no-change record from the active review queue."""
        if self.current_book is None:
            return False
        marker = getattr(self.service, "mark_book_complete_if_ready", None)
        if not callable(marker):
            return False
        completed_book_id = self.current_book.book_id
        try:
            complete = bool(marker(completed_book_id))
        except Exception:
            return False
        if not complete:
            return False
        self.auto_lookup_completed_ids.add(completed_book_id)
        self.catalogue_changed.emit()
        self.refresh()
        self.plan_summary.setText(
            "This book was already fully updated and has been marked complete."
        )
        self.status_label.setText(
            "The completed book was removed from the Metadata & Cover Art "
            "queue. It remains available in Library."
        )
        return True

    def _organisation_option_changed(self, _checked: bool) -> None:
        """Require a fresh exact preview when physical organisation changes."""
        self._update_new_file_path()
        self.current_plan_id = None
        self.apply_button.setEnabled(False)
        self.plan_summary.setText(
            "Organisation option changed. Preview Selected Changes to see "
            "the exact proposed file path."
        )

    def _update_new_file_path(self, *_args: object) -> None:
        """Show the exact destination implied by the current reviewed fields."""
        if self.current_book is None:
            self.new_path_edit.clear()
            self.new_path_edit.setToolTip("")
            return
        values: dict[str, object] = {}
        for field in (
            "title",
            "author",
            "series",
            "series_number",
            "series_group",
            "series_group_number",
        ):
            checkbox = self.field_checks.get(field)
            editor = self.field_editors.get(field)
            if (
                checkbox is not None
                and checkbox.isChecked()
                and isinstance(editor, QLineEdit)
            ):
                values[field] = editor.text().strip()
        try:
            proposed_path = self.service.proposed_file_path(
                self.current_book.book_id,
                values,
                organise_file=self.organise_file_check.isChecked(),
            )
            path_text = str(proposed_path)
        except AttributeError:
            path_text = self.current_book.file_path
        except Exception as error:
            self.new_path_edit.clear()
            self.new_path_edit.setPlaceholderText(str(error))
            self.new_path_edit.setToolTip(str(error))
            return
        self.new_path_edit.setPlaceholderText(
            "The complete path that Apply will use"
        )
        self.new_path_edit.setText(path_text)
        self.new_path_edit.setToolTip(path_text)
        self.new_path_edit.setCursorPosition(0)

    def _apply_changes(self) -> None:
        if self.current_plan_id is None or self.apply_thread is not None:
            return
        service = self.protection_service_factory()
        try:
            operation = service.get_operation(self.current_plan_id)
        except Exception as error:
            self._reject_unusable_preview(str(error))
            return

        planned_book_ids = {
            int(item.book_id)
            for item in (
                *operation.plan.database_changes,
                *operation.plan.file_changes,
            )
            if item.book_id is not None
        }
        current_book_id = (
            self.current_book.book_id if self.current_book is not None else None
        )
        if planned_book_ids != {current_book_id}:
            self._reject_unusable_preview(
                "That preview belongs to a different book and cannot be "
                "applied. Twano has discarded it to protect your library."
            )
            return

        if operation.plan.is_expired():
            self.current_plan_id = None
            self.apply_button.setEnabled(False)
            self._preview_changes()
            if self.current_plan_id is not None:
                QMessageBox.information(
                    self,
                    "Preview Refreshed",
                    "That preview expired after 30 minutes to protect your "
                    "library.\n\nTwano has created a fresh preview from the "
                    "fields currently shown. Review the updated summary, "
                    "then choose Apply Reviewed Changes again.",
                )
            else:
                QMessageBox.warning(
                    self,
                    "Preview Expired",
                    "That preview expired and Twano could not create a fresh "
                    "one. Review the message on this page, then choose "
                    "Preview Selected Changes again.",
                )
            return

        if not self._confirm_reviewed_apply():
            return
        confirmation = PlanConfirmation(
            plan_token=operation.plan.plan_token,
            approved=True,
            confirmer="metadata_studio",
        )
        try:
            approved = service.approve_change_plan(
                operation.operation_id,
                confirmation,
                current_basis_token=service.current_basis_token(operation),
            )
            saved = self.preferences.load_protection_preferences()
            folder = (
                Path(saved.backup_folder)
                if saved.backup_folder
                else service.default_backup_folder()
            )
            policy = service.build_policy(folder, saved.retention_days)
            mode = self.preferences.load_home_preferences().protection_mode
        except Exception as error:
            self._reject_unusable_preview(str(error))
            return

        self._set_busy(True, "Creating a safety backup…")
        self.apply_thread = QThread(self)
        self.apply_worker = ProtectionExecutorWorker(
            approved.operation_id,
            policy,
            mode,
            self.protection_service_factory,
        )
        self.apply_worker.moveToThread(self.apply_thread)
        self.apply_thread.started.connect(self.apply_worker.run)
        self.apply_worker.progress_changed.connect(self._apply_progress)
        self.apply_worker.completed.connect(self._apply_completed)
        self.apply_worker.failed.connect(self._apply_failed)
        self.apply_worker.cancelled.connect(self._apply_failed)
        self.apply_worker.finished.connect(self.apply_thread.quit)
        self.apply_worker.finished.connect(self.apply_worker.deleteLater)
        self.apply_thread.finished.connect(self._apply_thread_finished)
        self.apply_thread.finished.connect(self.apply_thread.deleteLater)
        self.apply_thread.start()

    def _confirm_reviewed_apply(self) -> bool:
        """Request the optional final confirmation without weakening Apply."""
        metadata = self.preferences.load_metadata_preferences()
        if not metadata.confirm_reviewed_apply:
            return True

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Apply Reviewed Metadata?")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(
            self.plan_summary.text()
            + "\n\nTwano will create a verified safety backup first."
        )
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        dialog.setEscapeButton(QMessageBox.StandardButton.No)
        hide_checkbox = QCheckBox("Don't show this confirmation again")
        dialog.setCheckBox(hide_checkbox)
        answer = QMessageBox.StandardButton(dialog.exec())
        if answer != QMessageBox.StandardButton.Yes:
            return False
        if hide_checkbox.isChecked():
            self.preferences.save_metadata_preferences(
                replace(metadata, confirm_reviewed_apply=False)
            )
            self.preferences.sync()
        return True

    def _reject_unusable_preview(self, message: str) -> None:
        """Make a stale or missing preview failure visible and recoverable."""
        self.current_plan_id = None
        self.apply_button.setEnabled(False)
        self.status_label.setText(message)
        QMessageBox.warning(
            self,
            "Cannot Apply Preview",
            message
            + "\n\nChoose Preview Selected Changes to create and review a "
            "fresh preview before applying.",
        )

    def _apply_progress(self, percent: int, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(percent)
        self.status_label.setText(message)

    def _apply_completed(self, _operation) -> None:
        completed_book_id = (
            self.current_book.book_id if self.current_book is not None else 0
        )
        self.current_plan_id = None
        self.apply_button.setEnabled(False)
        if completed_book_id:
            self.auto_lookup_completed_ids.add(completed_book_id)
        if completed_book_id in self.prepared_records:
            self.prepared_decisions[completed_book_id] = "applied"
            self._upsert_batch_review_item(completed_book_id)
        self.prepared_results.pop(completed_book_id, None)
        self.prepared_reports.pop(completed_book_id, None)
        self.prepared_failures.pop(completed_book_id, None)
        self.catalogue_changed.emit()
        if completed_book_id:
            self.book_updated.emit(completed_book_id)
        self.refresh()
        auto_lookup = self.auto_next_checkbox.isChecked()
        advanced = (
            self._select_next_unprocessed_book(completed_book_id)
            if auto_lookup
            else self._select_next_book_needing_attention(completed_book_id)
        )
        if advanced:
            self.status_label.setText(
                "Metadata updated safely. "
                + (
                    "The next book is ready. Starting its metadata and cover "
                    "search…"
                    if auto_lookup
                    else "The next book needing attention is ready. Choose "
                    "Find Metadata & Covers when you are ready."
                )
            )
            if auto_lookup and self.current_book is not None:
                self.pending_auto_lookup_book_id = self.current_book.book_id
                if self.apply_thread is None:
                    QTimer.singleShot(0, self._run_pending_auto_lookup)
        else:
            self.status_label.setText(
                "Metadata updated safely. There are no other books needing "
                "attention. The catalogue backup is available from "
                "Protection & Undo."
            )

    def _select_next_unprocessed_book(self, completed_book_id: int) -> bool:
        """Select the next Library book not applied in this automatic run."""
        count = self.book_combo.count()
        if count == 0:
            return False
        completed_index = next(
            (
                index
                for index in range(count)
                if (
                    isinstance(self.book_combo.itemData(index), LibraryRecord)
                    and self.book_combo.itemData(index).book_id
                    == completed_book_id
                )
            ),
            -1,
        )
        if completed_index < 0:
            return self.current_book is not None
        if count < 2:
            return False
        for offset in range(1, count):
            index = (completed_index + offset) % count
            record = self.book_combo.itemData(index)
            if (
                isinstance(record, LibraryRecord)
                and record.book_id not in self.auto_lookup_completed_ids
            ):
                self.book_combo.setCurrentIndex(index)
                return True
        record = self.prepared_records.get(int(book_id))
        if record is not None:
            self.book_combo.addItem(
                f"{record.title} — {record.author}",
                record,
            )
            self.book_combo.setCurrentIndex(self.book_combo.count() - 1)
            return True
        return False

    def _select_next_book_needing_attention(
        self,
        completed_book_id: int,
    ) -> bool:
        """Advance through the visible book order, wrapping once if needed."""
        count = self.book_combo.count()
        if count == 0:
            return False
        completed_index = next(
            (
                index
                for index in range(count)
                if (
                    isinstance(
                        self.book_combo.itemData(index),
                        LibraryRecord,
                    )
                    and self.book_combo.itemData(index).book_id
                    == completed_book_id
                )
            ),
            -1,
        )
        if completed_index < 0:
            return (
                self.current_book is not None
                and self.current_book.metadata_issue_count > 0
            )
        if count < 2:
            return False
        for offset in range(1, count):
            index = (completed_index + offset) % count
            record = self.book_combo.itemData(index)
            if (
                isinstance(record, LibraryRecord)
                and record.book_id != completed_book_id
                and record.metadata_issue_count > 0
            ):
                self.book_combo.setCurrentIndex(index)
                return True
        return False

    def _apply_failed(self, message: str) -> None:
        self.current_plan_id = None
        self.apply_button.setEnabled(False)
        self.plan_summary.setText(message)
        self.status_label.setText(message)
        QMessageBox.warning(
            self,
            "Apply Could Not Finish",
            message
            + "\n\nNothing further was applied. Review the message, then "
            "create a fresh preview before trying again.",
        )

    def _move_to_manual_review(self) -> None:
        if self.current_book is None or self.is_busy():
            return
        book = self.current_book
        answer = QMessageBox.question(
            self,
            "Move Book to Manual Review?",
            (
                f'Move "{book.title}" out of the active Library?\n\n'
                "The ebook file will be physically moved into a folder named "
                '"To be manually reviewed" inside its watched library. '
                "Twano will remove its catalogue entry and future scans will "
                "skip that folder.\n\n"
                "The ebook contents will not be changed or deleted."
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        next_book_id = self._next_book_needing_attention_id(book.book_id)
        try:
            result = self.service.move_book_to_manual_review(book.book_id)
        except Exception as error:
            self.status_label.setText(
                f"Twano could not move this book for manual review: {error}"
            )
            return
        self.current_plan_id = None
        self.catalogue_changed.emit()
        self.refresh()
        advanced = (
            next_book_id is not None
            and self._select_book_by_id(next_book_id)
        )
        if advanced:
            self.status_label.setText(
                f'"{book.title}" was moved to manual review. The next book '
                "needing attention is ready."
            )
        else:
            self.status_label.setText(
                f'"{book.title}" was moved to:\n{result.review_folder}\n'
                "There are no other books needing attention."
            )

    def _delete_book(self) -> None:
        if self.current_book is None or self.is_busy():
            return
        book = self.current_book
        answer = QMessageBox.question(
            self,
            "Delete Book?",
            (
                f'Stop Twano checking "{book.title}"?\n\n'
                "The ebook file will be physically moved into a folder "
                'named "-=deleted=-" inside its watched library. Twano '
                "will remove its catalogue entry and future scans will "
                "skip that folder.\n\n"
                "The ebook contents will not be changed or permanently "
                "deleted — move it out of that folder to bring it back."
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        next_book_id = self._next_book_needing_attention_id(book.book_id)
        try:
            result = self.service.delete_book(book.book_id)
        except Exception as error:
            self.status_label.setText(
                f"Twano could not delete this book: {error}"
            )
            return
        self.current_plan_id = None
        self.catalogue_changed.emit()
        self.refresh()
        advanced = (
            next_book_id is not None
            and self._select_book_by_id(next_book_id)
        )
        if advanced:
            self.status_label.setText(
                f'"{book.title}" was deleted. The next book needing '
                "attention is ready."
            )
        else:
            self.status_label.setText(
                f'"{book.title}" was moved to:\n{result.deleted_folder}\n'
                "There are no other books needing attention."
            )

    def _next_book_needing_attention_id(
        self,
        current_book_id: int,
    ) -> int | None:
        count = self.book_combo.count()
        current_index = self.book_combo.currentIndex()
        for offset in range(1, count):
            index = (current_index + offset) % count
            record = self.book_combo.itemData(index)
            if (
                isinstance(record, LibraryRecord)
                and record.book_id != current_book_id
                and record.metadata_issue_count > 0
            ):
                return record.book_id
        return None

    def _select_book_by_id(self, book_id: int) -> bool:
        for index in range(self.book_combo.count()):
            record = self.book_combo.itemData(index)
            if (
                isinstance(record, LibraryRecord)
                and record.book_id == book_id
            ):
                self.book_combo.setCurrentIndex(index)
                return True
        return False

    def _apply_thread_finished(self) -> None:
        self.apply_thread = None
        self.apply_worker = None
        self._set_busy(False)
        if self.pending_auto_lookup_book_id is not None:
            QTimer.singleShot(0, self._run_pending_auto_lookup)
        self.work_stopped.emit()

    def _run_pending_auto_lookup(self) -> None:
        wanted_id = self.pending_auto_lookup_book_id
        if wanted_id is None or self.is_busy():
            return
        self.pending_auto_lookup_book_id = None
        if not self._select_book_by_id(wanted_id):
            return
        if wanted_id in self.prepared_results:
            self._show_prepared_results(wanted_id)
            return
        self._start_lookup()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.lookup_button.setEnabled(not busy and self.current_book is not None)
        self.find_covers_button.setEnabled(
            not busy and self.current_book is not None
        )
        self.preview_button.setEnabled(not busy and self.current_book is not None)
        self.apply_button.setEnabled(
            not busy and self.current_plan_id is not None
        )
        self.download_cover_button.setEnabled(
            not busy
            and isinstance(
                self.cover_result_combo.currentData(),
                MetadataCandidate,
            )
        )
        self.results_list.setEnabled(not busy)
        self.cover_result_combo.setEnabled(not busy)
        self.local_cover_button.setEnabled(not busy)
        self.manual_review_button.setEnabled(
            not busy and self.current_book is not None
        )
        self.delete_book_button.setEnabled(
            not busy and self.current_book is not None
        )
        self.book_combo.setEnabled(not busy)
        self.provider_combo.setEnabled(not busy)
        self.queue_button.setEnabled(not busy)
        self.auto_next_checkbox.setEnabled(not busy)
        self.prepare_queue_button.setEnabled(
            self.batch_worker is not None or not busy
        )
        self.prepare_folder_button.setEnabled(not busy)
        self.next_prepared_button.setEnabled(
            not busy and bool(self.prepared_results)
        )
        self.batch_review_list.setEnabled(not busy)
        selected_batch_book = (
            self.current_book is not None
            and self.current_book.book_id in self.prepared_results
        )
        self.accept_prepared_button.setEnabled(
            not busy
            and selected_batch_book
            and bool(self.prepared_results.get(self.current_book.book_id, ()))
        )
        self.reject_prepared_button.setEnabled(
            not busy
            and self.current_book is not None
            and self.current_book.book_id in self.prepared_records
        )
        if busy:
            self.progress.setRange(0, 0)
            self.progress.show()
            if message:
                self.status_label.setText(message)
        else:
            self.progress.hide()

    def _populate_fields(self, values: dict[str, object]) -> None:
        for field, value in values.items():
            editor = self.field_editors.get(field)
            if isinstance(editor, QLineEdit):
                editor.setText(str(value or ""))
            elif isinstance(editor, QTextEdit):
                editor.setPlainText(str(value or ""))

    def _clear_fields(self) -> None:
        for editor in self.field_editors.values():
            if isinstance(editor, QLineEdit):
                editor.clear()
            elif isinstance(editor, QTextEdit):
                editor.clear()
        self.results_list.clear()
        self.results_list.addItem(
            "Run Find Metadata & Covers to see matches",
            None,
        )
        self.cover_result_combo.clear()
        self.download_cover_button.setEnabled(False)
        self.preview_cover_path = ""
        self.preview_cover_candidate = None
        self.pending_cover_candidate = None
        self.pending_cover_fallback = False
        self.cover_fallback_attempted = False
        self.validated_cover_paths.clear()
        self.provider_summary = ""
        self._set_cover_preview_text("No cover\nselected")

    def _set_cover_preview_text(self, text: str) -> None:
        self.cover_preview.setPixmap(QPixmap())
        self.cover_preview.setText(text)
        self.cover_preview.setToolTip(
            "A larger preview will be available after a cover is loaded."
        )

    def _show_cover(self, path: str) -> None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self._set_cover_preview_text("Preview not\navailable")
            return
        self.cover_preview.setText("")
        self.cover_preview.setToolTip(
            "Click to view this cover at a larger size."
        )
        self.cover_preview.setPixmap(
            pixmap.scaled(
                max(1, self.cover_preview.width() - 6),
                max(1, self.cover_preview.height() - 6),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _open_large_cover(self) -> None:
        path = (
            self.preview_cover_path
            or self.cover_path_edit.text().strip()
        )
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.status_label.setText(
                "Load or choose a cover before opening the large preview."
            )
            return
        if self.cover_viewer is not None:
            self.cover_viewer.close()
        title = (
            self.preview_cover_candidate.title
            if self.preview_cover_candidate is not None
            else self.current_book.title
            if self.current_book is not None
            else "Book cover"
        )
        viewer = CoverPreviewDialog(
            pixmap,
            title=title,
            parent=self,
        )
        viewer.destroyed.connect(self._cover_viewer_closed)
        self.cover_viewer = viewer
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

    def _cover_viewer_closed(self) -> None:
        self.cover_viewer = None

    def is_busy(self) -> bool:
        return (
            self.lookup_thread is not None
            or self.apply_thread is not None
            or self.batch_thread is not None
        )

    def cancel_active_operation(self) -> None:
        if self.apply_worker is not None:
            self.apply_worker.request_cancel()
        if self.batch_worker is not None:
            self.batch_worker.request_cancel()


def _leading_series_number(file_name: str) -> str:
    """Read an explicit ``01 -`` filename prefix without guessing."""
    name = Path(str(file_name)).name
    match = re.match(
        r"^\s*(\d{1,4}(?:\.\d+)?)\s*(?:-|\u2013|\u2014)\s+",
        name,
    )
    if match is None:
        return ""
    whole, separator, fraction = match.group(1).partition(".")
    normalised = whole.lstrip("0") or "0"
    return normalised + (separator + fraction if separator else "")


def _path_is_beneath(file_path: str, folder: Path) -> bool:
    """Return whether a catalogued file belongs to the selected folder tree."""
    try:
        Path(file_path).resolve().relative_to(folder)
    except (OSError, ValueError):
        return False
    return True


def _normalised_match_text(value: str) -> str:
    """Return a punctuation-insensitive value for matching provider results."""
    return "".join(
        character
        for character in value.casefold()
        if character.isalnum()
    )


def _display_order_number(value: object) -> str:
    """Display whole-number reading positions without a redundant decimal."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        number = float(text)
    except (TypeError, ValueError):
        return text
    if number.is_integer():
        return str(int(number))
    return text


def _candidate_display_text(candidate: MetadataCandidate) -> str:
    """Show provider-specific series details directly in result choices."""
    series = ""
    if candidate.series:
        series = f" [{candidate.series}"
        if candidate.series_number:
            series += f" #{_display_order_number(candidate.series_number)}"
        series += "]"
    rating = (
        f" · {candidate.provider_rating:.1f}/5"
        if candidate.provider_rating > 0
        else ""
    )
    return (
        f"{candidate.provider_name}: {candidate.title}{series} — "
        f"{candidate.author or 'Unknown author'} ({candidate.confidence}%)"
        f"{rating}"
    )


def _has_series_conflict(
    candidates: tuple[MetadataCandidate, ...],
) -> bool:
    """Identify different strong series claims without choosing one silently."""
    values = {
        (
            _normalised_match_text(candidate.series),
            _normalised_match_text(candidate.series_number),
        )
        for candidate in candidates
        if candidate.confidence >= 75 and candidate.series.strip()
    }
    return len(values) > 1


def _provider_summary_text(
    searched: tuple[str, ...],
    failed: tuple[str, ...],
    covers: tuple[str, ...],
    failure_details: tuple[str, ...] = (),
) -> str:
    """Return a compact explanation of the combined provider search."""
    if not searched:
        return "No active online providers were searched."
    summary = "Searched: " + ", ".join(searched) + "."
    if covers:
        summary += " Covers from: " + ", ".join(covers) + "."
    if failed:
        summary += " Unavailable: " + ", ".join(failed) + "."
        if failure_details:
            summary += " " + " ".join(failure_details)
        elif "Google Books" in failed:
            summary += " Check Google Books setup in Plugins."
    return summary

"""Responsive, paged RC6.5 Library browser."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import (
    QItemSelectionModel,
    QModelIndex,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from preferences import (
    LibraryDensity,
    LibraryPreferences,
    LibrarySortDirection,
    LibrarySortField,
    LibraryViewMode,
    PreferencesStore,
)
from services.library_service import (
    LibraryFilterOptions,
    LibraryQuery,
    LibraryRecord,
    LibraryService,
)
from ui.book_actions import (
    open_book,
    open_containing_folder,
    open_folder_path,
)
from ui.book_details import BookDetailsPanel
from ui.library_format import display_status, format_file_size
from ui.library_grid import LibraryGridDelegate
from ui.library_model import LibraryModel
from ui.thumbnail_cache import ThumbnailCache


logger = logging.getLogger(__name__)

SORT_LABELS = {
    LibrarySortField.TITLE: "Title",
    LibrarySortField.AUTHOR: "Author",
    LibrarySortField.SERIES: "Series & sequence",
    LibrarySortField.DATE_ADDED: "Date added",
    LibrarySortField.FILE_MODIFIED: "File modified",
    LibrarySortField.FORMAT: "Format",
    LibrarySortField.METADATA_QUALITY: "Metadata quality",
}

TOOLBAR_REFLOW_BREAKPOINT = 1020
DETAILS_SIDEBAR_BREAKPOINT = 900


class CheckableFilterButton(QToolButton):
    """Compact multi-select filter whose menu entries are checkable."""

    selection_changed = Signal()

    def __init__(self, all_label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._all_label = all_label
        self._actions: list[QAction] = []
        self._updating = False
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setMenu(QMenu(self))
        self._update_text()

    def set_options(
        self,
        values: tuple[object, ...] | list[object],
        *,
        labeler=lambda value: str(value),
        selected: tuple[object, ...] | list[object] = (),
    ) -> None:
        selected_values = set(selected)
        self._updating = True
        self.menu().clear()
        self._actions.clear()
        for value in values:
            action = self.menu().addAction(labeler(value))
            action.setData(value)
            action.setCheckable(True)
            action.setChecked(value in selected_values)
            action.toggled.connect(self._action_toggled)
            self._actions.append(action)
        self._updating = False
        self._update_text()

    def selected_values(self) -> tuple[object, ...]:
        return tuple(
            action.data() for action in self._actions if action.isChecked()
        )

    def set_selected_values(self, values) -> None:
        wanted = set(values)
        self._updating = True
        for action in self._actions:
            action.setChecked(action.data() in wanted)
        self._updating = False
        self._update_text()

    def clear_selection(self) -> None:
        self.set_selected_values(())

    def currentData(self):
        selected = self.selected_values()
        return selected[0] if len(selected) == 1 else None

    def findData(self, value) -> int:
        for index, action in enumerate(self._actions, start=1):
            if action.data() == value:
                return index
        return -1

    def setCurrentIndex(self, index: int) -> None:
        if index <= 0:
            self.clear_selection()
        elif index - 1 < len(self._actions):
            self.set_selected_values((self._actions[index - 1].data(),))

    def _action_toggled(self, _checked: bool) -> None:
        self._update_text()
        if not self._updating:
            self.selection_changed.emit()

    def _update_text(self) -> None:
        selected = [action.text() for action in self._actions if action.isChecked()]
        if not selected:
            self.setText(self._all_label)
        elif len(selected) == 1:
            self.setText(selected[0])
        else:
            noun = "formats" if "format" in self._all_label.casefold() else "ratings"
            self.setText(f"{len(selected)} {noun}")


class LibraryPage(QWidget):
    """Browse one shared paged result source in grid or list form."""

    edit_metadata_requested = Signal(str)
    review_issues_requested = Signal(str)

    def __init__(
        self,
        service: LibraryService,
        preferences: PreferencesStore | None = None,
        *,
        background_queries: bool = True,
    ) -> None:
        super().__init__()
        self.service = service
        self.preferences = preferences or PreferencesStore()
        self._preferences = self.preferences.load_library_preferences()
        self._compact = False
        self._toolbar_compact = True
        self._pending_selection_id: int | None = None

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(self.refresh_library)

        self._build_heading()
        self._build_filters()
        self._build_toolbar()
        self._build_views(background_queries)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(10)
        layout.addWidget(self.heading)
        layout.addWidget(self.description)
        layout.addWidget(self.search_input)
        layout.addWidget(self.filter_frame)
        layout.addWidget(self.toolbar_widget)
        layout.addWidget(self.content_stack, 1)
        self.manual_review_folder_button = QPushButton(
            "Open Manual Review Folder"
        )
        self.manual_review_folder_button.setObjectName(
            "openManualReviewFolderAction"
        )
        self.manual_review_folder_button.clicked.connect(
            self._open_manual_review_folder
        )
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self.manual_review_folder_button)
        layout.addLayout(footer)

        self.refresh_library_data()
        QTimer.singleShot(0, self._apply_responsive_layout)

    def _build_heading(self) -> None:
        self.heading = QLabel("Library")
        self.heading.setObjectName("pageTitle")
        self.description = QLabel(
            "Browse your collection as a living bookshelf. Grid and list "
            "share the same filters, selection and paged results."
        )
        self.description.setObjectName("pageDescription")
        self.description.setWordWrap(True)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("librarySearch")
        self.search_input.setPlaceholderText(
            "Search title, author, ISBN, publisher, series, filename or "
            "location…"
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._schedule_refresh)

    def _build_filters(self) -> None:
        self.format_filter = CheckableFilterButton("All formats")
        self.rating_filter = CheckableFilterButton("All website ratings")
        self.rating_filter.set_options(
            tuple(range(0, 6)),
            labeler=lambda rating: (
                "No website rating"
                if rating == 0
                else "★" * rating + "☆" * (5 - rating)
            ),
        )
        self.author_filter = self._filter_combo("All authors")
        self.series_filter = self._filter_combo("All series")
        self.collection_filter = self._filter_combo("All collections")
        self.location_filter = self._filter_combo("All locations")
        self.status_filter = self._filter_combo("All metadata")

        self.clear_button = QPushButton("Clear Filters")
        self.clear_button.clicked.connect(self.clear_filters)

        self.filter_frame = QFrame()
        self.filter_frame.setObjectName("searchFilters")
        grid = QGridLayout(self.filter_frame)
        grid.setContentsMargins(12, 9, 12, 10)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        controls = (
            ("Format", self.format_filter),
            ("Website rating", self.rating_filter),
            ("Author", self.author_filter),
            ("Series", self.series_filter),
            ("Collection", self.collection_filter),
            ("Library location", self.location_filter),
            ("Metadata status", self.status_filter),
        )
        for index, (label_text, control) in enumerate(controls):
            row = (index // 4) * 2
            column = index % 4
            label = QLabel(label_text)
            label.setObjectName("filterLabel")
            grid.addWidget(label, row, column)
            grid.addWidget(control, row + 1, column)
            grid.setColumnStretch(column, 1)
        grid.addWidget(self.clear_button, 3, 3)

    def _build_toolbar(self) -> None:
        self.summary_label = QLabel("Loading Library…")
        self.summary_label.setObjectName("scanSummary")
        self.summary_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )

        self.grid_button = QPushButton("Grid")
        self.list_button = QPushButton("List")
        self.grid_button.setCheckable(True)
        self.list_button.setCheckable(True)
        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        self.view_group.addButton(self.grid_button)
        self.view_group.addButton(self.list_button)
        self.grid_button.clicked.connect(
            lambda: self.set_view_mode(LibraryViewMode.GRID)
        )
        self.list_button.clicked.connect(
            lambda: self.set_view_mode(LibraryViewMode.LIST)
        )

        self.density_combo = QComboBox()
        self.density_combo.setToolTip("Cover density")
        for density, label in (
            (LibraryDensity.COMPACT, "Compact covers"),
            (LibraryDensity.COMFORTABLE, "Comfortable covers"),
            (LibraryDensity.SPACIOUS, "Spacious covers"),
        ):
            self.density_combo.addItem(label, density.value)
        self.density_combo.setCurrentIndex(
            self.density_combo.findData(self._preferences.density.value)
        )
        self.density_combo.currentIndexChanged.connect(
            self._density_changed
        )

        self.sort_combo = QComboBox()
        self.sort_combo.setToolTip("Sort Library")
        for field, label in SORT_LABELS.items():
            self.sort_combo.addItem(label, field.value)
        self.sort_combo.setCurrentIndex(
            self.sort_combo.findData(self._preferences.sort_field.value)
        )
        self.sort_combo.currentIndexChanged.connect(
            self._sort_controls_changed
        )

        self.direction_combo = QComboBox()
        self.direction_combo.addItem(
            "Ascending",
            LibrarySortDirection.ASCENDING.value,
        )
        self.direction_combo.addItem(
            "Descending",
            LibrarySortDirection.DESCENDING.value,
        )
        self.direction_combo.setCurrentIndex(
            self.direction_combo.findData(
                self._preferences.sort_direction.value
            )
        )
        self.direction_combo.currentIndexChanged.connect(
            self._sort_controls_changed
        )

        self.details_button = QPushButton("Details")
        self.details_button.setCheckable(True)
        self.details_button.setChecked(self._preferences.details_visible)
        self.details_button.toggled.connect(self._details_toggled)
        self.details_button.clicked.connect(self._details_button_clicked)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_library_data)

        for combo in (
            self.density_combo,
            self.sort_combo,
            self.direction_combo,
        ):
            self._configure_responsive_combo(combo)

        self.toolbar_widget = QWidget()
        self.toolbar_widget.setObjectName("libraryToolbar")
        self.toolbar_layout = QGridLayout(self.toolbar_widget)
        self.toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar_layout.setSpacing(7)
        self._toolbar_widgets = (
            self.summary_label,
            self.grid_button,
            self.list_button,
            self.density_combo,
            self.sort_combo,
            self.direction_combo,
            self.details_button,
            self.refresh_button,
        )
        self._layout_toolbar(compact=True)

    def _build_views(self, background_queries: bool) -> None:
        self.model = LibraryModel(
            self.service,
            background_queries=background_queries,
            parent=self,
        )
        self.thumbnail_cache = ThumbnailCache(parent=self)
        self.grid_delegate = LibraryGridDelegate(
            self.thumbnail_cache,
            self._preferences.density,
            self,
        )

        self.library_grid = QListView()
        self.library_grid.setObjectName("libraryGrid")
        self.library_grid.setViewMode(QListView.ViewMode.IconMode)
        self.library_grid.setFlow(QListView.Flow.LeftToRight)
        self.library_grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.library_grid.setMovement(QListView.Movement.Static)
        self.library_grid.setWrapping(True)
        self.library_grid.setSpacing(4)
        self.library_grid.setUniformItemSizes(True)
        self.library_grid.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.library_grid.setItemDelegate(self.grid_delegate)
        self.library_grid.setGridSize(self.grid_delegate.item_size)
        self.library_grid.setModel(self.model)

        self.library_table = QTableView()
        self.library_table.setObjectName("libraryList")
        self.library_table.setModel(self.model)
        self.library_table.setAlternatingRowColors(True)
        self.library_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.library_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.library_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.library_table.setWordWrap(False)
        self.library_table.verticalHeader().setVisible(False)
        self.library_table.verticalHeader().setDefaultSectionSize(31)
        header = self.library_table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        for column in range(1, self.model.columnCount()):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Interactive,
            )
        header.setSortIndicator(
            self._sort_column(self._preferences.sort_field),
            self._qt_sort_order(self._preferences.sort_direction),
        )
        header.sortIndicatorChanged.connect(self._table_sort_changed)

        self.selection_model = QItemSelectionModel(self.model, self)
        self.library_grid.setSelectionModel(self.selection_model)
        self.library_table.setSelectionModel(self.selection_model)
        self.selection_model.currentChanged.connect(
            self._selection_changed
        )
        self.library_grid.activated.connect(self._activate_details)
        self.library_table.activated.connect(self._activate_details)
        self.library_grid.clicked.connect(self._open_compact_details)
        self.library_table.clicked.connect(self._open_compact_details)

        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.library_grid)
        self.view_stack.addWidget(self.library_table)

        self.state_label = QLabel("Loading Library…")
        self.state_label.setObjectName("emptyResults")
        self.state_label.setWordWrap(True)
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.browser_state = QStackedWidget()
        self.browser_state.addWidget(self.view_stack)
        self.browser_state.addWidget(self.state_label)

        self.details_panel = BookDetailsPanel(
            self.service,
            self.thumbnail_cache,
        )
        self.details_panel.back_requested.connect(self._show_browser)
        self.details_panel.open_book_requested.connect(
            lambda book: open_book(self, book, self.preferences)
        )
        self.details_panel.open_folder_requested.connect(
            lambda book: open_containing_folder(self, book)
        )
        self.details_panel.edit_metadata_requested.connect(
            self.edit_metadata_requested
        )
        self.details_panel.review_issues_requested.connect(
            self.review_issues_requested
        )
        self.details_panel.collections_changed.connect(
            self._collections_changed
        )

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.browser_state)
        self.splitter.addWidget(self.details_panel)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([820, 360])

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.splitter)

        self.model.loading_changed.connect(self._loading_changed)
        self.model.counts_changed.connect(self._counts_changed)
        self.model.page_loaded.connect(self._page_loaded)
        self.model.error_occurred.connect(self._query_failed)
        self.model.query_changed.connect(self._model_query_changed)
        self.thumbnail_cache.thumbnail_ready.connect(
            lambda _book_id: self.library_grid.viewport().update()
        )
        self.thumbnail_cache.thumbnail_failed.connect(
            lambda _book_id, _message: (
                self.library_grid.viewport().update()
            )
        )
        for view in (self.library_grid, self.library_table):
            view.verticalScrollBar().valueChanged.connect(
                lambda _value, browser=view: self._maybe_fetch_more(browser)
            )

        self.set_view_mode(self._preferences.view_mode, save=False)
        self.details_panel.setVisible(self._preferences.details_visible)

    @staticmethod
    def _filter_combo(all_label: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem(all_label, "")
        LibraryPage._configure_responsive_combo(combo)
        return combo

    @staticmethod
    def _configure_responsive_combo(combo: QComboBox) -> None:
        """Prevent long paths or labels from forcing horizontal overflow."""
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(10)
        combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

    def apply_search(self, search_text: str) -> None:
        """Apply a routed search without issuing a duplicate query."""
        self.search_timer.stop()
        self.search_input.blockSignals(True)
        self.search_input.setText(search_text)
        self.search_input.blockSignals(False)
        self.refresh_library()

    def activate(self) -> None:
        """Refresh the current paged query when navigation activates Library."""
        logger.info("Library page activated")
        self.search_timer.stop()
        self.refresh_library()

    def has_active_database_work(self) -> bool:
        """Return whether a background Library query still owns SQLite work."""
        return self.model.active_query_count > 0

    def refresh_library_data(self) -> None:
        """Refresh filter options, preserving all currently selected values."""
        selected = {
            "formats": self.format_filter.selected_values(),
            "author": self.author_filter.currentData(),
            "series": self.series_filter.currentData(),
            "collection": self.collection_filter.currentData(),
            "location": self.location_filter.currentData(),
            "status": self.status_filter.currentData(),
        }
        options = self.service.get_filter_options()
        self.format_filter.set_options(
            options.formats,
            selected=selected["formats"],
        )
        definitions = (
            (
                self.author_filter,
                "All authors",
                options.authors,
                selected["author"],
                lambda value: value,
            ),
            (
                self.series_filter,
                "All series",
                options.series,
                selected["series"],
                lambda value: value,
            ),
            (
                self.collection_filter,
                "All collections",
                options.collections,
                selected["collection"],
                lambda value: value,
            ),
            (
                self.location_filter,
                "All locations",
                options.locations,
                selected["location"],
                lambda value: value,
            ),
            (
                self.status_filter,
                "All metadata",
                options.metadata_statuses,
                selected["status"],
                display_status,
            ),
        )
        for combo, all_label, values, previous, labeler in definitions:
            self._replace_combo_options(
                combo,
                all_label,
                values,
                previous,
                labeler,
            )
        self._connect_filter_signals()
        self.refresh_library()

    def refresh_library(self) -> None:
        """Start a new background first-page query."""
        self.search_timer.stop()
        query = LibraryQuery(
            search_text=self.search_input.text(),
            file_formats=tuple(
                str(value) for value in self.format_filter.selected_values()
            ),
            provider_ratings=tuple(
                int(value) for value in self.rating_filter.selected_values()
            ),
            metadata_status=str(self.status_filter.currentData() or ""),
            author=str(self.author_filter.currentData() or ""),
            series=str(self.series_filter.currentData() or ""),
            collection=str(
                self.collection_filter.currentData() or ""
            ),
            library_location=str(
                self.location_filter.currentData() or ""
            ),
            sort_field=str(self.sort_combo.currentData() or "title"),
            sort_direction=str(
                self.direction_combo.currentData() or "ascending"
            ),
        )
        logger.info(
            "Library page query started search=%r offset=0 page_size=%s",
            query.search_text,
            query.page_size,
        )
        self.model.set_query(query)

    def clear_filters(self) -> None:
        """Reset every Library query control with one refresh."""
        self.search_timer.stop()
        controls = (
            self.search_input,
            self.format_filter,
            self.rating_filter,
            self.author_filter,
            self.series_filter,
            self.collection_filter,
            self.location_filter,
            self.status_filter,
        )
        for control in controls:
            control.blockSignals(True)
        self.search_input.clear()
        self.format_filter.clear_selection()
        self.rating_filter.clear_selection()
        for combo in controls[3:]:
            combo.setCurrentIndex(0)
        for control in controls:
            control.blockSignals(False)
        self.refresh_library()

    def reveal_book_after_update(self, book_id: int) -> None:
        """Clear stale filters and reselect a book changed by Metadata."""
        self._pending_selection_id = int(book_id)
        self.clear_filters()

    def set_view_mode(
        self,
        mode: LibraryViewMode,
        *,
        save: bool = True,
    ) -> None:
        """Switch presentation without changing or reloading the model."""
        mode = LibraryViewMode(mode)
        self.view_stack.setCurrentWidget(
            self.library_grid
            if mode == LibraryViewMode.GRID
            else self.library_table
        )
        self.grid_button.setChecked(mode == LibraryViewMode.GRID)
        self.list_button.setChecked(mode == LibraryViewMode.LIST)
        self.density_combo.setEnabled(mode == LibraryViewMode.GRID)
        if save:
            self._save_preferences()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _connect_filter_signals(self) -> None:
        if self.format_filter.property("librarySignalsConnected"):
            return
        for control in (self.format_filter, self.rating_filter):
            control.selection_changed.connect(self.refresh_library)
            control.setProperty("librarySignalsConnected", True)
        for combo in (
            self.author_filter,
            self.series_filter,
            self.collection_filter,
            self.location_filter,
            self.status_filter,
        ):
            combo.currentIndexChanged.connect(self.refresh_library)
            combo.setProperty("librarySignalsConnected", True)

    @staticmethod
    def _replace_combo_options(
        combo: QComboBox,
        all_label: str,
        values: tuple[str, ...],
        previous: object,
        labeler,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(all_label, "")
        for value in values:
            combo.addItem(labeler(value), value)
        index = combo.findData(previous)
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)

    def _schedule_refresh(self) -> None:
        self.search_timer.start()

    def _sort_controls_changed(self) -> None:
        if not hasattr(self, "model"):
            return
        self._save_preferences()
        self.refresh_library()

    def _table_sort_changed(
        self,
        column: int,
        order: Qt.SortOrder,
    ) -> None:
        fields = {
            0: LibrarySortField.TITLE,
            1: LibrarySortField.AUTHOR,
            2: LibrarySortField.SERIES,
            3: LibrarySortField.FORMAT,
            5: LibrarySortField.METADATA_QUALITY,
        }
        field = fields.get(column)
        if field is None:
            return
        direction = (
            LibrarySortDirection.DESCENDING
            if order == Qt.SortOrder.DescendingOrder
            else LibrarySortDirection.ASCENDING
        )
        self.sort_combo.blockSignals(True)
        self.direction_combo.blockSignals(True)
        self.sort_combo.setCurrentIndex(
            self.sort_combo.findData(field.value)
        )
        self.direction_combo.setCurrentIndex(
            self.direction_combo.findData(direction.value)
        )
        self.sort_combo.blockSignals(False)
        self.direction_combo.blockSignals(False)
        self._save_preferences()
        self.refresh_library()

    def _density_changed(self) -> None:
        density = LibraryDensity(
            str(self.density_combo.currentData())
        )
        self.grid_delegate.set_density(density)
        self.library_grid.setGridSize(self.grid_delegate.item_size)
        self.library_grid.doItemsLayout()
        self._save_preferences()

    def _details_toggled(self, visible: bool) -> None:
        if self._compact:
            return
        if not visible:
            self._show_browser()
            self.details_panel.setVisible(False)
        else:
            self.details_panel.setVisible(True)
        self._save_preferences()

    def _selection_changed(
        self,
        current: QModelIndex,
        _previous: QModelIndex,
    ) -> None:
        self.details_panel.set_book(
            self.model.record_at(current.row())
            if current.isValid()
            else None
        )

    def _activate_details(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self.selection_model.setCurrentIndex(
            index,
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows,
        )
        self._open_compact_details(index)

    def _open_compact_details(self, index: QModelIndex) -> None:
        """Open the selected book as the full compact content view."""
        if not self._compact or not index.isValid():
            return
        self.selection_model.setCurrentIndex(
            index,
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows,
        )
        self._set_browser_controls_visible(False)
        self.details_panel.setVisible(True)
        self.content_stack.setCurrentWidget(self.details_panel)

    def _details_button_clicked(self) -> None:
        """Open compact details without changing the wide-panel preference."""
        if not self._compact:
            return
        index = self.selection_model.currentIndex()
        if not index.isValid() and self.model.rowCount() > 0:
            index = self.model.index(0, 0)
        self._open_compact_details(index)

    def _show_browser(self) -> None:
        self._set_browser_controls_visible(True)
        self.content_stack.setCurrentWidget(self.splitter)
        if not self._compact:
            self.details_panel.setVisible(
                self.details_button.isChecked()
            )

    def _apply_responsive_layout(self) -> None:
        toolbar_compact = self.width() < TOOLBAR_REFLOW_BREAKPOINT
        if toolbar_compact != self._toolbar_compact:
            self._toolbar_compact = toolbar_compact
            self._layout_toolbar(toolbar_compact)

        compact = self.width() < DETAILS_SIDEBAR_BREAKPOINT
        if compact == self._compact:
            return
        self._compact = compact
        self.details_button.blockSignals(True)
        self.details_button.setCheckable(not compact)
        self.details_button.setText(
            "View Details" if compact else "Details"
        )
        if not compact:
            self.details_button.setChecked(
                self._preferences.details_visible
            )
        self.details_button.blockSignals(False)
        if compact:
            self.content_stack.addWidget(self.details_panel)
            self.details_panel.back_button.setVisible(True)
            self.content_stack.setCurrentWidget(self.splitter)
        else:
            self._set_browser_controls_visible(True)
            self.content_stack.removeWidget(self.details_panel)
            self.splitter.addWidget(self.details_panel)
            self.details_panel.back_button.setVisible(False)
            self.details_panel.setVisible(
                self._preferences.details_visible
            )
            self.content_stack.setCurrentWidget(self.splitter)

    def _layout_toolbar(self, compact: bool) -> None:
        """Reflow Library options instead of clipping them at narrow widths."""
        for widget in self._toolbar_widgets:
            self.toolbar_layout.removeWidget(widget)
        for column in range(9):
            self.toolbar_layout.setColumnStretch(column, 0)

        if compact:
            self.toolbar_layout.addWidget(
                self.summary_label,
                0,
                0,
                1,
                3,
            )
            self.toolbar_layout.addWidget(self.refresh_button, 0, 3)
            self.toolbar_layout.addWidget(self.grid_button, 1, 0)
            self.toolbar_layout.addWidget(self.list_button, 1, 1)
            self.toolbar_layout.addWidget(
                self.density_combo,
                1,
                2,
                1,
                2,
            )
            self.toolbar_layout.addWidget(
                self.sort_combo,
                2,
                0,
                1,
                2,
            )
            self.toolbar_layout.addWidget(self.direction_combo, 2, 2)
            self.toolbar_layout.addWidget(self.details_button, 2, 3)
            for column in range(4):
                self.toolbar_layout.setColumnStretch(column, 1)
            return

        self.toolbar_layout.addWidget(self.summary_label, 0, 0)
        for column, widget in enumerate(
            (
                self.grid_button,
                self.list_button,
                self.density_combo,
                self.sort_combo,
                self.direction_combo,
                self.details_button,
                self.refresh_button,
            ),
            1,
        ):
            self.toolbar_layout.addWidget(widget, 0, column)
        self.toolbar_layout.setColumnStretch(0, 1)

    def _set_browser_controls_visible(self, visible: bool) -> None:
        """Give compact details the vertical space used by browser controls."""
        self.description.setVisible(visible)
        self.search_input.setVisible(visible)
        self.filter_frame.setVisible(visible)
        for index in range(self.toolbar_layout.count()):
            item = self.toolbar_layout.itemAt(index)
            widget = item.widget()
            if widget is not None:
                widget.setVisible(visible)

    def _loading_changed(self, loading: bool) -> None:
        if loading and self.model.rowCount() == 0:
            self.state_label.setText("Loading your Library…")
            self.browser_state.setCurrentWidget(self.state_label)

    def _counts_changed(self, matching: int, total: int) -> None:
        loaded = self.model.rowCount()
        if matching == total:
            self.summary_label.setText(
                f"{loaded:,} of {total:,} books loaded"
            )
        else:
            self.summary_label.setText(
                f"{loaded:,} of {matching:,} matches loaded "
                f"• {total:,} books"
            )

    def _page_loaded(self, count: int) -> None:
        logger.info(
            "Library page loaded rows=%s loaded=%s matching=%s total=%s",
            count,
            self.model.rowCount(),
            self.model.matching_count,
            self.model.total_count,
        )
        if self.model.rowCount():
            self.browser_state.setCurrentWidget(self.view_stack)
            self._restore_pending_selection()
        elif self.model.total_count == 0:
            self.state_label.setText(
                "Your Library is empty.\n\nChoose Scan from the sidebar "
                "to add an ebook folder."
            )
            self.browser_state.setCurrentWidget(self.state_label)
        else:
            self.state_label.setText(
                "No books match these filters.\n\nClear filters or try a "
                "broader search."
            )
            self.browser_state.setCurrentWidget(self.state_label)

    def _query_failed(self, message: str) -> None:
        logger.error("Library query failed: %s", message)
        self.state_label.setText(
            "Library results could not be loaded.\n\n"
            f"{message}\n\nTry Refresh. If the problem continues, close "
            "Twano and check the database location."
        )
        self.browser_state.setCurrentWidget(self.state_label)

    def _model_query_changed(self, _query: LibraryQuery) -> None:
        self.thumbnail_cache.set_generation(self.model.generation)
        self.details_panel.set_book(None)

    def _maybe_fetch_more(self, view: QAbstractItemView) -> None:
        scrollbar = view.verticalScrollBar()
        if scrollbar.maximum() - scrollbar.value() <= 3:
            self.model.fetchMore()

    def _collections_changed(self) -> None:
        book = self.details_panel.book
        self._pending_selection_id = book.book_id if book else None
        self.refresh_library_data()

    def _open_manual_review_folder(self) -> None:
        try:
            folders = self.service.manual_review_folders()
        except Exception as error:
            QMessageBox.warning(
                self,
                "Manual review folder unavailable",
                f"Twano could not find the manual review folders.\n\n{error}",
            )
            return
        if not folders:
            QMessageBox.information(
                self,
                "No Manual Review Folder Yet",
                "The folder is created inside a watched library after you "
                "move the first invalid book from Metadata & Cover Art.",
            )
            return
        folder = self._preferred_manual_review_folder(folders)
        if folder is None:
            return
        open_folder_path(self, folder)

    def _preferred_manual_review_folder(
        self,
        folders: tuple[Path, ...],
    ) -> Path | None:
        book = self.details_panel.book
        if book is not None:
            preferred = (
                Path(book.library_folder) / "To be manually reviewed"
            )
            for folder in folders:
                if folder == preferred.resolve(strict=False):
                    return folder
        if len(folders) == 1:
            return folders[0]
        labels = [str(folder) for folder in folders]
        selected, accepted = QInputDialog.getItem(
            self,
            "Choose Manual Review Folder",
            "More than one watched library has a manual review folder:",
            labels,
            0,
            False,
        )
        return Path(selected) if accepted and selected else None

    def _restore_pending_selection(self) -> None:
        if self._pending_selection_id is None:
            return
        for row, book in enumerate(self.model.records):
            if book.book_id == self._pending_selection_id:
                index = self.model.index(row, 0)
                self.selection_model.setCurrentIndex(
                    index,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
                self._pending_selection_id = None
                return

    def _save_preferences(self) -> None:
        if not hasattr(self, "details_button"):
            return
        details_visible = (
            self._preferences.details_visible
            if self._compact
            else self.details_button.isChecked()
        )
        self._preferences = LibraryPreferences(
            view_mode=(
                LibraryViewMode.GRID
                if self.view_stack.currentWidget() is self.library_grid
                else LibraryViewMode.LIST
            ),
            density=LibraryDensity(
                str(self.density_combo.currentData())
            ),
            sort_field=LibrarySortField(
                str(self.sort_combo.currentData())
            ),
            sort_direction=LibrarySortDirection(
                str(self.direction_combo.currentData())
            ),
            details_visible=details_visible,
        )
        self.preferences.save_library_preferences(self._preferences)
        self.preferences.sync()

    @staticmethod
    def _sort_column(field: LibrarySortField) -> int:
        return {
            LibrarySortField.TITLE: 0,
            LibrarySortField.AUTHOR: 1,
            LibrarySortField.SERIES: 2,
            LibrarySortField.FORMAT: 3,
            LibrarySortField.METADATA_QUALITY: 5,
        }.get(field, 0)

    @staticmethod
    def _qt_sort_order(
        direction: LibrarySortDirection,
    ) -> Qt.SortOrder:
        return (
            Qt.SortOrder.DescendingOrder
            if direction == LibrarySortDirection.DESCENDING
            else Qt.SortOrder.AscendingOrder
        )

"""Shared paged model for RC6.5 Library grid and list views."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QRunnable,
    QThreadPool,
    Qt,
    Signal,
    Slot,
)

from services.library_service import (
    LibraryPageResult,
    LibraryQuery,
    LibraryRecord,
    LibraryService,
)
from ui.library_format import (
    display_series,
    display_status,
    format_file_size,
)


LIBRARY_RECORD_ROLE = int(Qt.ItemDataRole.UserRole) + 1
BOOK_ID_ROLE = LIBRARY_RECORD_ROLE + 1


class _QuerySignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, int, str)


class _LibraryQueryTask(QRunnable):
    """Run one service query without retaining a SQLite connection."""

    def __init__(
        self,
        service: LibraryService,
        query: LibraryQuery,
        generation: int,
    ) -> None:
        super().__init__()
        self._service = service
        self._query = query
        self._generation = generation
        self.signals = _QuerySignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.get_library_page(self._query)
        except Exception as error:
            self.signals.failed.emit(
                self._generation,
                self._query.offset,
                str(error) or type(error).__name__,
            )
            return
        self.signals.finished.emit(self._generation, result)


class LibraryModel(QAbstractTableModel):
    """Incrementally expose one filtered Library query to two views."""

    loading_changed = Signal(bool)
    counts_changed = Signal(int, int)
    page_loaded = Signal(int)
    error_occurred = Signal(str)
    query_changed = Signal(object)

    COLUMNS = (
        ("Title", "title"),
        ("Author", "author"),
        ("Series", "series"),
        ("Format", "format"),
        ("Size", None),
        ("Metadata", "metadata_quality"),
        ("Location", None),
    )

    def __init__(
        self,
        service: LibraryService,
        *,
        thread_pool: QThreadPool | None = None,
        background_queries: bool = True,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._background_queries = background_queries
        self._query = LibraryQuery()
        self._records: list[LibraryRecord] = []
        self._matching_count = 0
        self._total_count = 0
        self._has_more = False
        self._loading = False
        self._generation = 0
        self._active_tasks: dict[
            tuple[int, int],
            _LibraryQueryTask,
        ] = {}

    @property
    def query(self) -> LibraryQuery:
        return self._query

    @property
    def records(self) -> tuple[LibraryRecord, ...]:
        return tuple(self._records)

    @property
    def matching_count(self) -> int:
        return self._matching_count

    @property
    def total_count(self) -> int:
        return self._total_count

    @property
    def loading(self) -> bool:
        return self._loading

    @property
    def active_query_count(self) -> int:
        """Return database queries that have not delivered a result yet."""
        return len(self._active_tasks)

    @property
    def generation(self) -> int:
        return self._generation

    def record_at(self, row: int) -> LibraryRecord | None:
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(
        self,
        index: QModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ):
        if not index.isValid():
            return None
        record = self.record_at(index.row())
        if record is None:
            return None

        if role == LIBRARY_RECORD_ROLE:
            return record
        if role == BOOK_ID_ROLE:
            return record.book_id
        if role == int(Qt.ItemDataRole.ToolTipRole):
            return self._tooltip(record)
        if role == int(Qt.ItemDataRole.TextAlignmentRole):
            if index.column() in {3, 4, 5}:
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter
            )
        if role != int(Qt.ItemDataRole.DisplayRole):
            return None

        values = (
            record.title,
            record.author,
            display_series(record),
            record.file_format,
            format_file_size(record.file_size),
            display_status(record.metadata_status),
            record.library_folder or record.file_path,
        )
        return values[index.column()]

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ):
        if (
            role == int(Qt.ItemDataRole.DisplayRole)
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(self.COLUMNS)
        ):
            return self.COLUMNS[section][0]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:
        return (
            not parent.isValid()
            and self._has_more
            and not self._loading
        )

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:
        if not self.canFetchMore(parent):
            return
        self._start_query(
            replace(self._query, offset=len(self._records)),
            self._generation,
        )

    def sort(
        self,
        column: int,
        order: Qt.SortOrder = Qt.SortOrder.AscendingOrder,
    ) -> None:
        if not 0 <= column < len(self.COLUMNS):
            return
        sort_field = self.COLUMNS[column][1]
        if sort_field is None:
            return
        direction = (
            "descending"
            if order == Qt.SortOrder.DescendingOrder
            else "ascending"
        )
        self.set_query(
            replace(
                self._query,
                sort_field=sort_field,
                sort_direction=direction,
            )
        )

    def set_query(self, query: LibraryQuery) -> None:
        """Clear loaded rows and asynchronously load a new first page."""
        query = replace(query, offset=0)
        self._generation += 1
        self._query = query
        self.beginResetModel()
        self._records.clear()
        self._matching_count = 0
        self._total_count = 0
        self._has_more = False
        self.endResetModel()
        self.query_changed.emit(query)
        self.counts_changed.emit(0, 0)
        self._start_query(query, self._generation)

    def refresh(self) -> None:
        """Reload the current query from its first page."""
        self.set_query(self._query)

    def _start_query(
        self,
        query: LibraryQuery,
        generation: int,
    ) -> None:
        self._set_loading(True)
        if not self._background_queries:
            try:
                result = self._service.get_library_page(query)
            except Exception as error:
                self._handle_failure(
                    generation,
                    str(error) or type(error).__name__,
                )
            else:
                self._handle_result(generation, result)
            return

        task = _LibraryQueryTask(self._service, query, generation)
        self._active_tasks[(generation, query.offset)] = task
        task.signals.finished.connect(self._background_result)
        task.signals.failed.connect(self._background_failure)
        self._thread_pool.start(task)

    @Slot(int, object)
    def _handle_result(
        self,
        generation: int,
        result: LibraryPageResult,
    ) -> None:
        if generation != self._generation:
            return
        if result.offset != len(self._records):
            self._set_loading(False)
            self.error_occurred.emit(
                "Library paging changed while results were loading."
            )
            return

        if result.records:
            first_row = len(self._records)
            last_row = first_row + len(result.records) - 1
            self.beginInsertRows(QModelIndex(), first_row, last_row)
            self._records.extend(result.records)
            self.endInsertRows()

        self._matching_count = result.matching_count
        self._total_count = result.total_count
        self._has_more = result.has_more
        self._set_loading(False)
        self.counts_changed.emit(
            self._matching_count,
            self._total_count,
        )
        self.page_loaded.emit(len(result.records))

    @Slot(int, str)
    def _handle_failure(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self._set_loading(False)
        self.error_occurred.emit(message)

    @Slot(int, object)
    def _background_result(
        self,
        generation: int,
        result: LibraryPageResult,
    ) -> None:
        self._active_tasks.pop((generation, result.offset), None)
        self._handle_result(generation, result)

    @Slot(int, int, str)
    def _background_failure(
        self,
        generation: int,
        offset: int,
        message: str,
    ) -> None:
        self._active_tasks.pop((generation, offset), None)
        self._handle_failure(generation, message)

    def _set_loading(self, loading: bool) -> None:
        if self._loading == loading:
            return
        self._loading = loading
        self.loading_changed.emit(loading)

    @staticmethod
    def _tooltip(record: LibraryRecord) -> str:
        lines = [record.title, f"by {record.author}"]
        series = display_series(record)
        if series:
            lines.append(series)
        lines.append(record.file_path)
        return "\n".join(value for value in lines if value)

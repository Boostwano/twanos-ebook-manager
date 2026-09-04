"""Actionable library-health page without an analytics dashboard."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.library_health_service import (
    HealthIssue,
    LibraryHealthService,
)
from services.library_service import LibraryService, MissingFileEntry


class VerifyLibraryDialog(QDialog):
    """Review books whose file could not be found, and choose what to remove.

    Nothing is removed automatically. A file can look missing for reasons
    that aren't really gone -- an offline network drive, a USB drive not
    plugged in -- so every entry here needs a deliberate choice, the same
    as the existing Delete Book action elsewhere in Twano.
    """

    def __init__(
        self,
        entries: tuple[MissingFileEntry, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Verify Library")
        self.entries = entries

        description = QLabel(
            f"{len(entries)} book{'s' if len(entries) != 1 else ''} "
            "checked across your whole catalogue whose file could not be "
            "found, including any already organised outside a watched "
            "source. Check the ones you want to remove from the "
            "catalogue -- their ebook files are never touched, since "
            "there is nothing left to find."
        )
        description.setWordWrap(True)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("verifyLibraryList")
        for entry in entries:
            label = entry.title
            if entry.author:
                label += f" — {entry.author}"
            label += f"\n{entry.file_path}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry.book_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)

        select_all = QPushButton("Check All")
        select_all.clicked.connect(lambda: self._set_all_checked(True))
        select_none = QPushButton("Uncheck All")
        select_none.clicked.connect(lambda: self._set_all_checked(False))
        selection_row = QHBoxLayout()
        selection_row.addWidget(select_all)
        selection_row.addWidget(select_none)
        selection_row.addStretch()

        buttons = QDialogButtonBox()
        self.remove_button = buttons.addButton(
            "Remove Selected", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.remove_button.setObjectName("verifyLibraryRemoveAction")
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(description)
        layout.addLayout(selection_row)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(buttons)
        self.resize(560, 420)

    def _set_all_checked(self, checked: bool) -> None:
        state = (
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        for row in range(self.list_widget.count()):
            self.list_widget.item(row).setCheckState(state)

    def selected_book_ids(self) -> tuple[int, ...]:
        ids: list[int] = []
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return tuple(ids)


class LibraryHealthPage(QWidget):
    destination_requested = Signal(str)
    catalogue_changed = Signal()

    def __init__(
        self,
        service: LibraryHealthService,
        library_service: LibraryService,
    ) -> None:
        super().__init__()
        self.service = service
        self.library_service = library_service

        title = QLabel("Library Health")
        title.setObjectName("pageTitle")
        description = QLabel(
            "See what needs attention and go directly to the place where "
            "you can fix it. The score is based only on visible catalogue "
            "and library-location checks."
        )
        description.setObjectName("pageDescription")
        description.setWordWrap(True)

        self.score_panel = QFrame()
        self.score_panel.setObjectName("healthScorePanel")
        score_layout = QHBoxLayout(self.score_panel)
        self.score_label = QLabel("100")
        self.score_label.setObjectName("healthScore")
        self.score_text = QLabel("Your library is ready.")
        self.score_text.setObjectName("healthScoreText")
        self.score_text.setWordWrap(True)
        score_layout.addWidget(self.score_label)
        score_layout.addWidget(self.score_text, 1)

        self.issue_grid = QGridLayout()
        self.issue_grid.setSpacing(10)
        self.empty_label = QLabel(
            "No health issues need attention. Add and scan a library to "
            "begin, or enjoy the clean result."
        )
        self.empty_label.setObjectName("healthEmpty")
        self.empty_label.setWordWrap(True)

        refresh_button = QPushButton("Refresh Health Check")
        refresh_button.setObjectName("healthRefreshAction")
        refresh_button.clicked.connect(self.refresh)
        verify_button = QPushButton("Verify Library")
        verify_button.setObjectName("healthVerifyLibraryAction")
        verify_button.setToolTip(
            "Check every catalogued book's file, not just ones inside a "
            "watched source, and review any that can no longer be found."
        )
        verify_button.clicked.connect(self._verify_library)
        actions_row = QHBoxLayout()
        actions_row.addWidget(refresh_button)
        actions_row.addWidget(verify_button)
        actions_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 22)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(self.score_panel)
        layout.addLayout(self.issue_grid, 1)
        layout.addWidget(self.empty_label)
        layout.addLayout(actions_row)
        self.refresh()

    def activate(self) -> None:
        self.refresh()

    def _verify_library(self) -> None:
        entries = self.library_service.find_books_with_missing_files()
        if not entries:
            QMessageBox.information(
                self,
                "Verify Library",
                "Every catalogued book's file was found. Nothing needs "
                "review.",
            )
            return
        dialog = VerifyLibraryDialog(entries, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.selected_book_ids()
        if not selected:
            return
        removed = self.library_service.remove_books_from_catalogue(selected)
        self.refresh()
        self.catalogue_changed.emit()
        QMessageBox.information(
            self,
            "Verify Library",
            f"Removed {removed} book{'s' if removed != 1 else ''} from the "
            "catalogue. Their ebook files, if any still exist elsewhere, "
            "were never touched.",
        )

    def refresh(self) -> None:
        report = self.service.get_report()
        self.score_label.setText(str(report.score))
        if report.total_books == 0:
            self.score_text.setText(
                "No books are catalogued yet. Your first scan will create "
                "the health baseline."
            )
        elif report.issues:
            self.score_text.setText(
                f"{report.total_books:,} books checked. "
                f"{len(report.issues)} areas have clear next steps."
            )
        else:
            self.score_text.setText(
                f"{report.total_books:,} books checked with no current "
                "health warnings."
            )

        while self.issue_grid.count():
            item = self.issue_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, issue in enumerate(report.issues[:6]):
            self.issue_grid.addWidget(
                self._issue_card(issue),
                index // 2,
                index % 2,
            )
        self.empty_label.setVisible(not report.issues)

    def _issue_card(self, issue: HealthIssue) -> QFrame:
        card = QFrame()
        card.setObjectName("healthIssueCard")
        title = QLabel(issue.title)
        title.setObjectName("healthIssueTitle")
        count = QLabel(str(issue.count))
        count.setObjectName(f"healthCount_{issue.severity}")
        explanation = QLabel(issue.explanation)
        explanation.setObjectName("healthIssueDescription")
        explanation.setWordWrap(True)
        remaining = max(0, issue.count - len(issue.preview_items))
        preview_lines = [f"• {item}" for item in issue.preview_items]
        if remaining:
            preview_lines.append(f"• and {remaining:,} more")
        preview = QLabel("\n".join(preview_lines))
        preview.setObjectName("healthIssuePreview")
        preview.setTextFormat(Qt.TextFormat.PlainText)
        preview.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        preview.setWordWrap(True)
        action = QPushButton(issue.action_label)
        action.setObjectName("healthIssueAction")
        action.clicked.connect(
            lambda _checked=False, destination=issue.destination: (
                self.destination_requested.emit(destination)
            )
        )
        heading = QHBoxLayout()
        heading.addWidget(title, 1)
        heading.addWidget(count)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.addLayout(heading)
        layout.addWidget(explanation)
        layout.addWidget(preview, 1)
        layout.addWidget(action)
        return card

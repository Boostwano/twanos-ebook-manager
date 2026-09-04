"""Dialog for adding or editing one watched library source."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.scan_service import LibrarySource, ScanService


class MultipleLibrarySourcesDialog(QDialog):
    """Stage several watched folders before adding any of them."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Watched Folders")
        self.setMinimumWidth(620)

        explanation = QLabel(
            "Add as many ebook folders as you need. Each folder becomes a "
            "separate watched source and can still be edited or removed later."
        )
        explanation.setWordWrap(True)

        self.folder_list = QListWidget()
        self.folder_list.setMinimumHeight(150)
        add_button = QPushButton("Add Folder…")
        add_button.clicked.connect(self._browse)
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self._remove_selected)
        folder_actions = QHBoxLayout()
        folder_actions.addWidget(add_button)
        folder_actions.addWidget(remove_button)
        folder_actions.addStretch()

        self.recursive_checkbox = QCheckBox(
            "Include folders inside each source"
        )
        self.recursive_checkbox.setChecked(True)
        self.include_input = QLineEdit()
        self.include_input.setPlaceholderText(
            "Optional, for example: *.epub; **/*.pdf"
        )
        self.exclude_input = QLineEdit()
        self.exclude_input.setPlaceholderText(
            "Optional, for example: Temp/**; **/Drafts/**"
        )
        form = QFormLayout()
        form.addRow("", self.recursive_checkbox)
        form.addRow("Include", self.include_input)
        form.addRow("Exclude", self.exclude_input)

        rules_note = QLabel(
            "The same optional scan rules are applied to every folder added "
            "here. You can edit an individual source afterward."
        )
        rules_note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addWidget(self.folder_list)
        layout.addLayout(folder_actions)
        layout.addLayout(form)
        layout.addWidget(rules_note)
        layout.addWidget(buttons)

    @property
    def folder_paths(self) -> tuple[str, ...]:
        return tuple(
            self.folder_list.item(index).text()
            for index in range(self.folder_list.count())
        )

    @property
    def include_subfolders(self) -> bool:
        return self.recursive_checkbox.isChecked()

    @property
    def include_patterns(self) -> str:
        return self.include_input.text()

    @property
    def exclude_patterns(self) -> str:
        return self.exclude_input.text()

    def add_folder_path(self, folder_path: str) -> None:
        """Add one normalised unique folder to the staged list."""
        folder = ScanService.normalise_source_path(folder_path)
        key = str(folder).casefold()
        if any(value.casefold() == key for value in self.folder_paths):
            return
        self.folder_list.addItem(str(folder))

    def _browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Add Watched eBook Folder",
            str(Path.home()),
        )
        if selected:
            self.add_folder_path(selected)

    def _remove_selected(self) -> None:
        for item in self.folder_list.selectedItems():
            self.folder_list.takeItem(self.folder_list.row(item))

    def _validate_and_accept(self) -> None:
        if not self.folder_paths:
            QMessageBox.warning(
                self,
                "No folders selected",
                "Choose at least one ebook folder before saving.",
            )
            return
        try:
            ScanService.normalise_patterns(self.include_patterns)
            ScanService.normalise_patterns(self.exclude_patterns)
        except ValueError as error:
            QMessageBox.warning(self, "Sources not saved", str(error))
            return
        self.accept()


class LibrarySourceDialog(QDialog):
    """Collect source settings without performing database work."""

    def __init__(
        self,
        source: LibrarySource | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source = source
        self.setWindowTitle(
            "Edit Watched Source" if source else "Add Watched Source"
        )
        self.setMinimumWidth(560)

        explanation = QLabel(
            "Twano will only watch this location. Adding or editing a source "
            "does not import, move, or change any ebook."
        )
        explanation.setWordWrap(True)

        self.path_input = QLineEdit(
            source.folder_path if source else ""
        )
        self.path_input.setPlaceholderText(
            r"C:\Books or \\server\share\Books"
        )
        self.path_input.setReadOnly(source is not None)
        browse_button = QPushButton("Browse…")
        browse_button.setVisible(source is None)
        browse_button.clicked.connect(self._browse)

        path_layout = QHBoxLayout()
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(self.path_input, 1)
        path_layout.addWidget(browse_button)
        path_widget = QWidget()
        path_widget.setLayout(path_layout)

        self.name_input = QLineEdit(
            source.display_name if source else ""
        )
        self.name_input.setPlaceholderText("For example: Main Library")

        self.recursive_checkbox = QCheckBox(
            "Include folders inside this source"
        )
        self.recursive_checkbox.setChecked(
            source.include_subfolders if source else True
        )

        self.include_input = QLineEdit(
            "; ".join(source.include_patterns) if source else ""
        )
        self.include_input.setPlaceholderText(
            "Optional, for example: *.epub; **/*.pdf"
        )
        self.exclude_input = QLineEdit(
            "; ".join(source.exclude_patterns) if source else ""
        )
        self.exclude_input.setPlaceholderText(
            "Optional, for example: Temp/**; **/Drafts/**"
        )

        rules_note = QLabel(
            "Rules are relative glob patterns separated by semicolons. "
            "They can narrow supported ebook files but cannot enable "
            "unsupported formats."
        )
        rules_note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Folder", path_widget)
        form.addRow("Name", self.name_input)
        form.addRow("", self.recursive_checkbox)
        form.addRow("Include", self.include_input)
        form.addRow("Exclude", self.exclude_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addLayout(form)
        layout.addWidget(rules_note)
        layout.addWidget(buttons)

    @property
    def folder_path(self) -> str:
        return self.path_input.text().strip()

    @property
    def display_name(self) -> str:
        return self.name_input.text().strip()

    @property
    def include_subfolders(self) -> bool:
        return self.recursive_checkbox.isChecked()

    @property
    def include_patterns(self) -> str:
        return self.include_input.text()

    @property
    def exclude_patterns(self) -> str:
        return self.exclude_input.text()

    def _browse(self) -> None:
        current = self.path_input.text().strip()
        start = current if current else str(Path.home())
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Watched eBook Folder",
            start,
        )
        if not selected:
            return
        self.path_input.setText(selected)
        if not self.name_input.text().strip():
            path = Path(selected)
            self.name_input.setText(path.name or selected)

    def _validate_and_accept(self) -> None:
        try:
            folder = ScanService.normalise_source_path(self.folder_path)
            ScanService.normalise_patterns(self.include_patterns)
            ScanService.normalise_patterns(self.exclude_patterns)
        except ValueError as error:
            QMessageBox.warning(self, "Source not saved", str(error))
            return
        if not self.display_name:
            self.name_input.setText(folder.name or str(folder))
        self.accept()

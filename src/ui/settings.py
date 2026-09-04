"""Application settings page."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from preferences import (
    AccessibilityPreferences,
    BANNER_NAMES,
    BannerRotation,
    GeneralPreferences,
    GreetingStyle,
    HomePreferences,
    MetadataPreferences,
    OrganizationPreferences,
    PreferencesStore,
    ProtectionMode,
    ReaderMode,
    ReadingPreferences,
)


class SettingsPage(QWidget):
    preferences_changed = Signal()
    protection_mode_changed = Signal(object)
    destination_folder_changed = Signal(str)

    def __init__(self, store: PreferencesStore) -> None:
        super().__init__()
        self.store = store

        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        description = QLabel(
            "Configure protection, the Home experience and how Twano "
            "opens books."
        )
        description.setObjectName("pageDescription")

        self.mode_combo = QComboBox()
        self.mode_combo.addItem(
            "Standard - changes allowed with safeguards",
            ProtectionMode.STANDARD,
        )
        self.mode_combo.addItem(
            "Read-Only - browsing and reports only",
            ProtectionMode.READ_ONLY,
        )

        self.greeting_combo = QComboBox()
        self.greeting_combo.addItem(
            "Dynamic (recommended)",
            GreetingStyle.DYNAMIC,
        )
        self.greeting_combo.addItem("Simple", GreetingStyle.SIMPLE)
        self.greeting_combo.addItem("Minimal", GreetingStyle.MINIMAL)

        self.banner_combo = QComboBox()
        self.banner_combo.addItems(BANNER_NAMES)
        self.rotation_combo = QComboBox()
        self.rotation_combo.addItem(
            "Fixed banner",
            BannerRotation.FIXED,
        )
        self.rotation_combo.addItem(
            "Rotate on startup",
            BannerRotation.STARTUP,
        )

        self.insight_checkbox = QCheckBox("Show Today's Insight")
        self.seasonal_checkbox = QCheckBox(
            "Show neutral seasonal messages"
        )
        self.quotes_checkbox = QCheckBox("Show reading quotes")

        home_form = QFormLayout()
        home_form.addRow("Protection Mode", self.mode_combo)
        home_form.addRow("Greeting style", self.greeting_combo)
        home_form.addRow("Hero banner", self.banner_combo)
        home_form.addRow("Banner mode", self.rotation_combo)
        home_form.addRow("", self.insight_checkbox)
        home_form.addRow("", self.seasonal_checkbox)
        home_form.addRow("", self.quotes_checkbox)

        home = QFrame()
        home.setObjectName("settingsPanel")
        home_layout = QVBoxLayout(home)
        home_layout.setContentsMargins(24, 22, 24, 22)
        home_layout.addLayout(home_form)

        self.reader_mode = QComboBox()
        self.reader_mode.addItem(
            "Use the Windows default application",
            ReaderMode.WINDOWS_DEFAULT,
        )
        self.reader_mode.addItem(
            "Use a specific application for each format",
            ReaderMode.CUSTOM,
        )
        self.reader_mode.addItem(
            "Ask which application to use",
            ReaderMode.ASK,
        )
        self.reader_mode.addItem(
            "Open the containing folder",
            ReaderMode.FOLDER,
        )

        self.epub_reader = QLineEdit()
        self.pdf_reader = QLineEdit()
        self.mobi_reader = QLineEdit()
        self.comic_reader = QLineEdit()
        for editor in (
            self.epub_reader,
            self.pdf_reader,
            self.mobi_reader,
            self.comic_reader,
        ):
            editor.setPlaceholderText(
                "Optional path to reader executable"
            )

        reading_form = QFormLayout()
        reading_form.addRow("Opening behaviour", self.reader_mode)
        reading_form.addRow("EPUB reader", self.epub_reader)
        reading_form.addRow("PDF reader", self.pdf_reader)
        reading_form.addRow("MOBI / AZW reader", self.mobi_reader)
        reading_form.addRow("CBZ / CBR reader", self.comic_reader)

        reading = QFrame()
        reading.setObjectName("settingsPanel")
        reading_layout = QVBoxLayout(reading)
        reading_layout.setContentsMargins(24, 22, 24, 22)
        reading_layout.addWidget(
            QLabel(
                "Leave an application path empty to fall back to the "
                "Windows default reader."
            )
        )
        reading_layout.addLayout(reading_form)

        self.open_library_checkbox = QCheckBox(
            "Allow manual Open Library metadata and cover searches"
        )
        self.confirm_metadata_apply_checkbox = QCheckBox(
            "Show confirmation before applying reviewed metadata"
        )
        self.confirm_metadata_apply_checkbox.setToolTip(
            "Re-enable the Apply confirmation if it was hidden from the "
            "Metadata & Cover Art page."
        )
        self.metadata_cache_combo = QComboBox()
        for label, days in (
            ("Do not keep lookup cache", 0),
            ("30 days (recommended)", 30),
            ("90 days", 90),
            ("1 year", 365),
        ):
            self.metadata_cache_combo.addItem(label, days)
        metadata = QFrame()
        metadata.setObjectName("settingsPanel")
        metadata_layout = QVBoxLayout(metadata)
        metadata_layout.setContentsMargins(24, 22, 24, 22)
        metadata_copy = QLabel(
            "A lookup sends the selected book's title, author, or ISBN to "
            "the enabled providers only after you choose a lookup action. "
            "Prepare Review Queue can search every book needing attention "
            "without changing files or catalogue data."
        )
        metadata_copy.setWordWrap(True)
        metadata_form = QFormLayout()
        metadata_form.addRow("", self.open_library_checkbox)
        metadata_form.addRow("", self.confirm_metadata_apply_checkbox)
        metadata_form.addRow("Keep completed lookups", self.metadata_cache_combo)
        metadata_layout.addWidget(metadata_copy)
        metadata_layout.addLayout(metadata_form)
        metadata_layout.addStretch()

        self.text_scale_combo = QComboBox()
        for percent in (90, 100, 110, 125, 150):
            label = f"{percent}%"
            if percent == 100:
                label += " (recommended)"
            self.text_scale_combo.addItem(label, percent)
        self.reduced_motion_checkbox = QCheckBox(
            "Reduce non-essential motion"
        )
        self.focus_checkbox = QCheckBox(
            "Use strong keyboard focus outlines"
        )
        accessibility = QFrame()
        accessibility.setObjectName("settingsPanel")
        accessibility_layout = QVBoxLayout(accessibility)
        accessibility_layout.setContentsMargins(24, 22, 24, 22)
        accessibility_form = QFormLayout()
        accessibility_form.addRow("Text size", self.text_scale_combo)
        accessibility_form.addRow("", self.reduced_motion_checkbox)
        accessibility_form.addRow("", self.focus_checkbox)
        accessibility_layout.addLayout(accessibility_form)
        accessibility_layout.addWidget(
            QLabel(
                "Text-size changes take effect after restarting Twano. "
                "Every core workflow remains available by keyboard."
            )
        )
        accessibility_layout.addStretch()

        self.destination_folder_edit = QLineEdit()
        self.destination_folder_edit.setObjectName("destinationFolder")
        self.destination_folder_edit.setPlaceholderText(
            "Leave empty to organise each book inside its own watched library"
        )
        self.destination_browse_button = QPushButton("Browse…")
        self.destination_browse_button.setObjectName(
            "browseDestinationAction"
        )
        self.destination_browse_button.clicked.connect(
            self._browse_for_destination_folder
        )
        destination_controls = QWidget()
        destination_controls.setObjectName("inlineControls")
        destination_layout = QHBoxLayout(destination_controls)
        destination_layout.setContentsMargins(0, 0, 0, 0)
        destination_layout.setSpacing(8)
        destination_layout.addWidget(self.destination_folder_edit, 1)
        destination_layout.addWidget(self.destination_browse_button)

        organisation = QFrame()
        organisation.setObjectName("settingsPanel")
        organisation_layout = QVBoxLayout(organisation)
        organisation_layout.setContentsMargins(24, 22, 24, 22)
        organisation_layout.addWidget(
            QLabel(
                "Choose one destination folder for every book Twano "
                "identifies with confidence, and for books moved to "
                '"Delete Book...". Books are still sorted into Author or '
                "shared -=Series=- folders (and a -=deleted=- folder) "
                "inside it. If you move already-organised books into this "
                "folder yourself, saving here also checks it for any book "
                "currently flagged missing and re-links it automatically."
            )
        )
        organisation_layout.itemAt(0).widget().setWordWrap(True)
        organisation_form = QFormLayout()
        organisation_form.addRow(
            "Destination folder", destination_controls
        )
        organisation_layout.addLayout(organisation_form)
        organisation_layout.addStretch()

        self.update_startup_checkbox = QCheckBox(
            "Check for updates when Twano starts"
        )
        self.first_run_checkbox = QCheckBox(
            "Show first-run guidance for an empty library"
        )
        general = QFrame()
        general.setObjectName("settingsPanel")
        general_layout = QVBoxLayout(general)
        general_layout.setContentsMargins(24, 22, 24, 22)
        general_layout.addWidget(self.update_startup_checkbox)
        general_layout.addWidget(self.first_run_checkbox)
        general_layout.addWidget(
            QLabel(
                "Backups and Undo retention are managed from the safety "
                "card at the bottom of the navigation bar."
            )
        )
        general_layout.addStretch()

        tabs = QTabWidget()
        self.tabs = tabs
        tabs.addTab(general, "General")
        tabs.addTab(home, "Home")
        tabs.addTab(reading, "Reading")
        tabs.addTab(metadata, "Metadata & Privacy")
        tabs.addTab(organisation, "File Organisation")
        tabs.addTab(accessibility, "Accessibility")

        save_button = QPushButton("Save Settings")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 35, 40, 35)
        layout.setSpacing(18)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(tabs, 1)
        layout.addWidget(save_button)

        self.setStyleSheet(
            "#settingsPanel {"
            "background: #18212a;"
            "border: 1px solid #30404e;"
            "border-radius: 6px;"
            "}"
        )
        self.load()

    def load(self) -> None:
        home = self.store.load_home_preferences()
        reading = self.store.load_reading_preferences()
        metadata = self.store.load_metadata_preferences()
        organisation = self.store.load_organization_preferences()
        accessibility = self.store.load_accessibility_preferences()
        general = self.store.load_general_preferences()
        self.destination_folder_edit.setText(
            organisation.destination_folder
        )

        self._select(self.mode_combo, home.protection_mode)
        self._select(self.greeting_combo, home.greeting_style)
        self.banner_combo.setCurrentText(home.banner_name)
        self._select(self.rotation_combo, home.banner_rotation)
        self.insight_checkbox.setChecked(home.show_today_insight)
        self.seasonal_checkbox.setChecked(
            home.show_seasonal_messages
        )
        self.quotes_checkbox.setChecked(home.show_reading_quotes)

        self._select(self.reader_mode, reading.reader_mode)
        self.epub_reader.setText(reading.epub_reader)
        self.pdf_reader.setText(reading.pdf_reader)
        self.mobi_reader.setText(reading.mobi_reader)
        self.comic_reader.setText(reading.comic_reader)
        self.open_library_checkbox.setChecked(
            metadata.open_library_enabled
        )
        self.confirm_metadata_apply_checkbox.setChecked(
            metadata.confirm_reviewed_apply
        )
        self._select(self.metadata_cache_combo, metadata.cache_days)
        self._select(
            self.text_scale_combo,
            accessibility.text_scale_percent,
        )
        self.reduced_motion_checkbox.setChecked(
            accessibility.reduced_motion
        )
        self.focus_checkbox.setChecked(
            accessibility.high_contrast_focus
        )
        self.update_startup_checkbox.setChecked(
            general.check_updates_on_startup
        )
        self.first_run_checkbox.setChecked(
            general.show_first_run_guide
        )

    def _browse_for_destination_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose Destination Folder",
            self.destination_folder_edit.text().strip(),
        )
        if folder:
            self.destination_folder_edit.setText(folder)

    def save(self) -> None:
        home = HomePreferences(
            protection_mode=ProtectionMode(
                self.mode_combo.currentData()
            ),
            greeting_style=GreetingStyle(
                self.greeting_combo.currentData()
            ),
            show_today_insight=self.insight_checkbox.isChecked(),
            show_seasonal_messages=(
                self.seasonal_checkbox.isChecked()
            ),
            show_reading_quotes=self.quotes_checkbox.isChecked(),
            banner_name=self.banner_combo.currentText(),
            banner_rotation=BannerRotation(
                self.rotation_combo.currentData()
            ),
        )
        reading = ReadingPreferences(
            reader_mode=ReaderMode(self.reader_mode.currentData()),
            epub_reader=self.epub_reader.text().strip(),
            pdf_reader=self.pdf_reader.text().strip(),
            mobi_reader=self.mobi_reader.text().strip(),
            comic_reader=self.comic_reader.text().strip(),
        )
        metadata = MetadataPreferences(
            open_library_enabled=self.open_library_checkbox.isChecked(),
            cache_days=int(self.metadata_cache_combo.currentData()),
            auto_lookup_next=(
                self.store.load_metadata_preferences().auto_lookup_next
            ),
            confirm_reviewed_apply=(
                self.confirm_metadata_apply_checkbox.isChecked()
            ),
        )
        accessibility = AccessibilityPreferences(
            text_scale_percent=int(self.text_scale_combo.currentData()),
            reduced_motion=self.reduced_motion_checkbox.isChecked(),
            high_contrast_focus=self.focus_checkbox.isChecked(),
        )
        general = GeneralPreferences(
            check_updates_on_startup=(
                self.update_startup_checkbox.isChecked()
            ),
            show_first_run_guide=self.first_run_checkbox.isChecked(),
        )
        new_destination = self.destination_folder_edit.text().strip()
        organisation = OrganizationPreferences(
            destination_folder=new_destination,
            destination_prompt_shown=True,
        )
        self.store.save_home_preferences(home)
        self.store.save_reading_preferences(reading)
        self.store.save_metadata_preferences(metadata)
        try:
            self.store.save_organization_preferences(organisation)
        except ValueError as error:
            QMessageBox.warning(self, "Destination Folder", str(error))
            return
        self.store.save_accessibility_preferences(accessibility)
        self.store.save_general_preferences(general)
        self.store.sync()
        self.protection_mode_changed.emit(home.protection_mode)
        self.preferences_changed.emit()
        if new_destination:
            # Emitted every time, not just on a real change: it's cheap
            # and safe to re-check, and lets the user re-save to pick up
            # books they moved into the folder themselves since the last
            # save, without needing to edit the path to force a refresh.
            self.destination_folder_changed.emit(new_destination)

    @staticmethod
    def _select(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

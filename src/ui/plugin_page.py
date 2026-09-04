"""Approved plugin catalogue plus Calibre and network integrations."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QThread, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database.database import DatabaseManager
from services.integration_service import IntegrationService
from services.metadata_studio_service import MetadataStudioService
from services.plugin_service import (
    REQUIRED_PLUGIN_IDS,
    PluginRecord,
    PluginService,
)
from workers.metadata_lookup_worker import ProviderConnectionCheckWorker


class PluginPage(QWidget):
    """Keep extensions controlled and integrations understandable."""

    scan_source_requested = Signal(str)

    def __init__(
        self,
        plugin_service: PluginService,
        integration_service: IntegrationService,
    ) -> None:
        super().__init__()
        self.plugin_service = plugin_service
        self.integration_service = integration_service
        # A manual provider check never reads or writes the real catalogue
        # (only network providers), so it gets its own disposable database
        # file instead of opening the user's real library.db unnecessarily.
        self.metadata_studio_service = MetadataStudioService(
            DatabaseManager(
                Path(tempfile.gettempdir()) / "twano-plugin-check.db"
            ),
            plugin_service=plugin_service,
        )
        self.plugins: tuple[PluginRecord, ...] = ()
        self.check_connection_thread: QThread | None = None
        self.check_connection_worker: ProviderConnectionCheckWorker | None = None

        title = QLabel("Plugins & Integrations")
        title.setObjectName("pageTitle")
        description = QLabel(
            "Use approved providers and built-in integrations. Unknown "
            "plugin packages are refused before installation."
        )
        description.setObjectName("pageDescription")
        description.setWordWrap(True)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_plugins_tab(), "Approved Plugins")
        self.tabs.addTab(
            self._build_integrations_tab(),
            "Calibre & Network Libraries",
        )
        self.status_label = QLabel()
        self.status_label.setObjectName("pluginStatus")
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.status_label)
        self.refresh()

    def _build_plugins_tab(self) -> QWidget:
        sort_label = QLabel("Sort plugins")
        self.plugin_sort_combo = QComboBox()
        self.plugin_sort_combo.setObjectName("pluginSort")
        self.plugin_sort_combo.addItem("Name A–Z", "ascending")
        self.plugin_sort_combo.addItem("Name Z–A", "descending")
        self.plugin_sort_combo.setToolTip(
            "Sort the approved plugin list alphabetically."
        )
        self.plugin_sort_combo.currentIndexChanged.connect(
            self._plugin_sort_changed
        )
        sort_row = QHBoxLayout()
        sort_row.addWidget(sort_label)
        sort_row.addWidget(self.plugin_sort_combo)
        sort_row.addStretch()

        self.plugin_table = QTableWidget(0, 8)
        self.plugin_table.setObjectName("pluginTable")
        self.plugin_table.setHorizontalHeaderLabels(
            (
                "Plugin",
                "Publisher",
                "Version",
                "Purpose",
                "Status",
                "API Key",
                "Provider Check",
                "Source",
            )
        )
        self.plugin_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.plugin_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.plugin_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.plugin_table.itemSelectionChanged.connect(
            self._plugin_selection_changed
        )
        self.plugin_table.itemChanged.connect(self._plugin_item_changed)
        self.install_button = QPushButton("Install Selected")
        self.install_button.setObjectName("pluginInstallAction")
        self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self._install_selected)
        self.uninstall_button = QPushButton("Uninstall Selected")
        self.uninstall_button.setObjectName("pluginUninstallAction")
        self.uninstall_button.setEnabled(False)
        self.uninstall_button.clicked.connect(self._uninstall_selected)
        self.enable_button = QPushButton("Enable Selected")
        self.enable_button.setObjectName("pluginEnableAction")
        self.enable_button.setEnabled(False)
        self.enable_button.clicked.connect(
            lambda: self._set_selected_enabled(True)
        )
        self.disable_button = QPushButton("Disable Selected")
        self.disable_button.setObjectName("pluginDisableAction")
        self.disable_button.setEnabled(False)
        self.disable_button.clicked.connect(
            lambda: self._set_selected_enabled(False)
        )
        self.delete_button = QPushButton("Delete Selected Package")
        self.delete_button.setObjectName("pluginDeleteAction")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._delete_selected)
        self.api_key_button = QPushButton("Configure API Key")
        self.api_key_button.setObjectName("pluginApiKeyAction")
        self.api_key_button.setEnabled(False)
        self.api_key_button.clicked.connect(self._configure_api_key)
        self.source_button = QPushButton("View Reputable Source")
        self.source_button.setObjectName("pluginSourceAction")
        self.source_button.setEnabled(False)
        self.source_button.clicked.connect(self._open_source)
        self.check_connection_button = QPushButton("Check Connection")
        self.check_connection_button.setObjectName(
            "pluginCheckConnectionAction"
        )
        self.check_connection_button.setEnabled(False)
        self.check_connection_button.clicked.connect(self._check_connection)
        self.package_button = QPushButton("Install Verified Package…")
        self.package_button.setObjectName("pluginPackageAction")
        self.package_button.clicked.connect(self._install_package)
        actions = QHBoxLayout()
        actions.addWidget(self.install_button)
        actions.addWidget(self.uninstall_button)
        actions.addWidget(self.enable_button)
        actions.addWidget(self.disable_button)
        actions.addStretch()
        details_actions = QGridLayout()
        details_actions.setHorizontalSpacing(8)
        details_actions.setVerticalSpacing(6)
        details_actions.addWidget(self.api_key_button, 0, 0)
        details_actions.addWidget(self.source_button, 0, 1)
        details_actions.addWidget(self.delete_button, 1, 0)
        details_actions.addWidget(self.package_button, 1, 1)
        details_actions.addWidget(self.check_connection_button, 2, 0, 1, 2)
        details_actions.setColumnStretch(0, 1)
        details_actions.setColumnStretch(1, 1)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(sort_row)
        layout.addWidget(self.plugin_table, 1)
        layout.addLayout(actions)
        layout.addLayout(details_actions)
        return page

    def _build_integrations_tab(self) -> QWidget:
        self.calibre_status = QLabel()
        self.calibre_status.setObjectName("calibreStatus")
        self.calibre_status.setWordWrap(True)
        detect_button = QPushButton("Detect Calibre")
        detect_button.setObjectName("calibreDetectAction")
        detect_button.clicked.connect(self._detect_calibre)

        self.calibre_folder = QLineEdit()
        self.calibre_folder.setPlaceholderText(
            "Choose the folder that contains Calibre's metadata.db"
        )
        browse_button = QPushButton("Choose Calibre Library…")
        browse_button.setObjectName("calibreBrowseAction")
        browse_button.clicked.connect(self._choose_calibre_library)
        inspect_button = QPushButton("Check Library")
        inspect_button.setObjectName("calibreInspectAction")
        inspect_button.clicked.connect(self._inspect_calibre_library)
        open_button = QPushButton("Open in Calibre")
        open_button.setObjectName("calibreOpenAction")
        open_button.clicked.connect(self._open_calibre_library)
        add_button = QPushButton("Add to Twano Scan")
        add_button.setObjectName("calibreAddSourceAction")
        add_button.clicked.connect(self._add_calibre_source)

        calibre_row = QHBoxLayout()
        calibre_row.addWidget(self.calibre_folder, 1)
        calibre_row.addWidget(browse_button)
        calibre_actions = QHBoxLayout()
        calibre_actions.addWidget(detect_button)
        calibre_actions.addWidget(inspect_button)
        calibre_actions.addWidget(open_button)
        calibre_actions.addWidget(add_button)
        calibre_actions.addStretch()

        network_heading = QLabel("Network Library Check")
        network_heading.setObjectName("sectionTitle")
        network_copy = QLabel(
            "Twano supports mapped drives and Windows UNC paths. An offline "
            "NAS remains unavailable instead of making every book look "
            "deleted."
        )
        network_copy.setObjectName("sectionDescription")
        network_copy.setWordWrap(True)
        self.network_path = QLineEdit()
        self.network_path.setPlaceholderText(
            r"Example: \\NAS\Books or Z:\Books"
        )
        network_button = QPushButton("Check Path")
        network_button.setObjectName("networkCheckAction")
        network_button.clicked.connect(self._check_network_path)
        add_network_button = QPushButton("Add to Twano Scan")
        add_network_button.setObjectName("networkAddSourceAction")
        add_network_button.clicked.connect(
            lambda: self.scan_source_requested.emit(
                self.network_path.text().strip()
            )
        )
        network_row = QHBoxLayout()
        network_row.addWidget(self.network_path, 1)
        network_row.addWidget(network_button)
        network_row.addWidget(add_network_button)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.addWidget(self.calibre_status)
        layout.addLayout(calibre_row)
        layout.addLayout(calibre_actions)
        layout.addSpacing(12)
        layout.addWidget(network_heading)
        layout.addWidget(network_copy)
        layout.addLayout(network_row)
        layout.addStretch()
        return page

    def activate(self) -> None:
        self.refresh()
        self._detect_calibre()

    def refresh(
        self,
        *,
        selected_plugin_id: str = "",
        status_message: str = "",
        checked_plugin_ids: set[str] | None = None,
    ) -> None:
        if checked_plugin_ids is None:
            checked_plugin_ids = self._checked_plugin_ids()
        if not selected_plugin_id:
            selected = self._selected_plugin()
            selected_plugin_id = selected.plugin_id if selected else ""
        self.plugins = tuple(
            sorted(
                self.plugin_service.list_plugins(),
                key=lambda plugin: (plugin.name.casefold(), plugin.plugin_id),
                reverse=self.plugin_sort_combo.currentData() == "descending",
            )
        )
        blocker = QSignalBlocker(self.plugin_table)
        try:
            self.plugin_table.clearSelection()
            self.plugin_table.setRowCount(len(self.plugins))
            selected_row = -1
            for row, plugin in enumerate(self.plugins):
                values = (
                    plugin.name,
                    plugin.publisher,
                    plugin.version,
                    ", ".join(
                        capability.replace("_", " ").title()
                        for capability in plugin.capabilities
                    ),
                    plugin.status,
                    _api_key_table_status(plugin),
                    _provider_health_table_status(plugin),
                    plugin.source_name,
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(256, plugin)
                    if column == 0:
                        item.setFlags(
                            item.flags()
                            | Qt.ItemFlag.ItemIsUserCheckable
                        )
                        item.setCheckState(
                            Qt.CheckState.Checked
                            if plugin.plugin_id in checked_plugin_ids
                            else Qt.CheckState.Unchecked
                        )
                    if column == 4:
                        item.setForeground(
                            QColor(
                                "#7fda89"
                                if plugin.enabled
                                else "#f0b45c"
                                if plugin.installed
                                else "#9fb0bc"
                            )
                        )
                    elif column == 5:
                        item.setForeground(
                            QColor(
                                "#7fda89"
                                if value in {"API Key Added", "None Required"}
                                else "#f0b45c"
                                if value == "Needs Re-entry"
                                else "#9fb0bc"
                            )
                        )
                    elif column == 6:
                        item.setForeground(
                            QColor(
                                "#7fda89"
                                if plugin.provider_health == "healthy"
                                else "#ef7868"
                                if plugin.provider_health
                                in {"blocked", "layout_changed"}
                                else "#f0b45c"
                                if plugin.provider_health == "unavailable"
                                else "#9fb0bc"
                            )
                        )
                    self.plugin_table.setItem(row, column, item)
                if plugin.plugin_id == selected_plugin_id:
                    selected_row = row
            if self.plugins:
                self.plugin_table.selectRow(
                    selected_row if selected_row >= 0 else 0
                )
        finally:
            del blocker
        self._plugin_selection_changed()
        if status_message:
            self.status_label.setText(status_message)

    def _plugin_sort_changed(self) -> None:
        selected = self._selected_plugin()
        self.refresh(
            selected_plugin_id=selected.plugin_id if selected else "",
            checked_plugin_ids=self._checked_plugin_ids(),
        )

    def _selected_plugin(self) -> PluginRecord | None:
        row = self.plugin_table.currentRow()
        item = self.plugin_table.item(row, 0) if row >= 0 else None
        plugin = item.data(256) if item else None
        return plugin if isinstance(plugin, PluginRecord) else None

    def _checked_plugin_ids(self) -> set[str]:
        checked: set[str] = set()
        for row in range(self.plugin_table.rowCount()):
            item = self.plugin_table.item(row, 0)
            plugin = item.data(256) if item else None
            if (
                item is not None
                and item.checkState() == Qt.CheckState.Checked
                and isinstance(plugin, PluginRecord)
            ):
                checked.add(plugin.plugin_id)
        return checked

    def _action_plugins(self) -> tuple[PluginRecord, ...]:
        checked_ids = self._checked_plugin_ids()
        if checked_ids:
            return tuple(
                plugin
                for plugin in self.plugins
                if plugin.plugin_id in checked_ids
            )
        selected = self._selected_plugin()
        return (selected,) if selected is not None else ()

    def _plugin_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._plugin_selection_changed()

    def _plugin_selection_changed(self) -> None:
        plugin = self._selected_plugin()
        checked = self._checked_plugin_ids()
        if checked:
            self._update_action_states(plugin)
            noun = "plugin" if len(checked) == 1 else "plugins"
            self.status_label.setText(
                f"{len(checked)} {noun} checked. Install, uninstall, enable, "
                "disable, or delete will apply to every eligible checked "
                "plugin."
            )
            return
        if plugin is None:
            self._update_action_states(None)
            self.status_label.setText(
                "Check one or more plugins, or select one row, to see the "
                "actions available."
            )
            return
        self._update_action_states(plugin)
        if not plugin.installed:
            next_step = "Choose Install Selected to add this plugin."
        elif plugin.api_key_unreadable:
            next_step = (
                "Windows cannot unlock the saved key. Choose Configure API "
                "Key and paste it again under your normal Windows account."
            )
        elif plugin.requires_api_key and not plugin.api_key_configured:
            next_step = (
                "Choose Configure API Key, follow the guide, then enable it."
            )
        elif plugin.enabled:
            next_step = (
                "This plugin is active. Choose Disable Selected to turn it off."
            )
            if plugin.optional_api_key and not plugin.api_key_configured:
                next_step += (
                    " If searches are unavailable, Configure API Key can "
                    "improve Google Books reliability."
                )
            if plugin.provider_health_message:
                next_step += (
                    " Provider check: "
                    + plugin.provider_health_message
                )
            if plugin.provider_health == "layout_changed":
                next_step += (
                    " Report 'Provider Update Needed' to Twano support so "
                    "the built-in page reader can be updated."
                )
            elif plugin.provider_health == "blocked":
                next_step += (
                    " Try again later; the provider may remove the temporary "
                    "access check."
                )
        else:
            next_step = (
                "This plugin is disabled. Choose Enable Selected to turn it on."
            )
        self.status_label.setText(
            f"{plugin.description}\nStatus: {plugin.status}. {next_step}"
        )

    def _update_action_states(
        self,
        plugin: PluginRecord | None,
    ) -> None:
        targets = self._action_plugins()
        can_install = any(
            not target.installed and target.built_in
            for target in targets
        )
        can_uninstall = any(
            target.installed
            and target.built_in
            and target.plugin_id not in REQUIRED_PLUGIN_IDS
            for target in targets
        )
        can_enable = any(
            target.installed
            and not target.enabled
            and target.compatible
            and (
                not target.requires_api_key
                or target.api_key_configured
            )
            for target in targets
        )
        can_disable = any(
            target.installed and target.enabled
            for target in targets
        )
        can_delete = any(
            target.installed and not target.built_in
            for target in targets
        )
        self.install_button.setEnabled(can_install)
        self.uninstall_button.setEnabled(can_uninstall)
        self.enable_button.setEnabled(can_enable)
        self.disable_button.setEnabled(can_disable)
        self.delete_button.setEnabled(can_delete)
        can_configure_key = bool(
            plugin is not None
            and plugin.installed
            and (plugin.requires_api_key or plugin.optional_api_key)
        )
        self.api_key_button.setEnabled(can_configure_key)
        self.source_button.setEnabled(
            bool(plugin is not None and plugin.source_url)
        )
        can_check_connection = bool(
            plugin is not None
            and not self._checked_plugin_ids()
            and plugin.installed
            and plugin.enabled
            and {"metadata_provider", "cover_provider"}
            & set(plugin.capabilities)
            and self.check_connection_thread is None
        )
        self.check_connection_button.setEnabled(can_check_connection)
        self.install_button.setToolTip(
            "Install every eligible checked approved plugin."
            if can_install
            else "No checked or selected plugin is ready to install."
        )
        self.uninstall_button.setToolTip(
            "Uninstall eligible checked built-in plugins. Saved API keys are "
            "kept for a later reinstall."
            if can_uninstall
            else "No checked or selected built-in plugin can be uninstalled."
        )
        self.enable_button.setToolTip(
            "Enable every eligible checked installed plugin."
            if can_enable
            else "No checked or selected plugin is ready to enable."
        )
        self.disable_button.setToolTip(
            "Disable every checked active plugin."
            if can_disable
            else "No checked or selected plugin is active."
        )
        self.delete_button.setToolTip(
            "Permanently delete checked downloaded plugin packages."
            if can_delete
            else "Built-in plugins can be uninstalled but not deleted."
        )
        self.api_key_button.setToolTip(
            "Add, replace, or remove this provider's protected API key."
            if can_configure_key
            else "This action is available for installed providers that use a key."
        )
        self.check_connection_button.setToolTip(
            "Run a small discardable search to confirm this provider "
            "responds right now, without needing a real book."
            if can_check_connection
            else (
                "Select one active metadata or cover provider to check its "
                "connection."
            )
        )

    def _install_selected(self) -> None:
        targets = self._action_plugins()
        eligible = tuple(
            plugin
            for plugin in targets
            if not plugin.installed and plugin.built_in
        )
        if not eligible:
            return
        installed: list[PluginRecord] = []
        failures: list[str] = []
        for plugin in eligible:
            try:
                installed.append(
                    self.plugin_service.install_builtin(plugin.plugin_id)
                )
            except Exception as error:
                failures.append(f"{plugin.name}: {error}")
        selected_id = installed[-1].plugin_id if installed else ""
        message = (
            f"{installed[0].name} was installed successfully."
            if len(installed) == 1
            else f"{len(installed)} plugins were installed successfully."
            if installed
            else "No plugins were installed."
        )
        setup_count = sum(
            plugin.requires_api_key
            and not plugin.api_key_configured
            for plugin in installed
        )
        if setup_count:
            message += (
                " Choose Configure API Key for "
                + (
                    "this provider before enabling it."
                    if setup_count == 1
                    else f"the {setup_count} providers that require one."
                )
            )
        elif installed:
            message += " Choose Enable Selected to make it Active."
        if failures:
            message += " Could not install: " + "; ".join(failures)
        self.refresh(
            selected_plugin_id=selected_id,
            checked_plugin_ids=self._checked_plugin_ids(),
            status_message=message,
        )

    def _uninstall_selected(self) -> None:
        targets = self._action_plugins()
        eligible = tuple(
            plugin
            for plugin in targets
            if (
                plugin.installed
                and plugin.built_in
                and plugin.plugin_id not in REQUIRED_PLUGIN_IDS
            )
        )
        if not eligible:
            return
        removed: list[PluginRecord] = []
        failures: list[str] = []
        for plugin in eligible:
            try:
                removed.append(self.plugin_service.uninstall(plugin.plugin_id))
            except Exception as error:
                failures.append(f"{plugin.name}: {error}")
        message = (
            f"{removed[0].name} was uninstalled."
            if len(removed) == 1
            else f"{len(removed)} plugins were uninstalled."
            if removed
            else "No plugins were uninstalled."
        )
        if failures:
            message += " Could not uninstall: " + "; ".join(failures)
        self.refresh(
            selected_plugin_id=removed[-1].plugin_id if removed else "",
            checked_plugin_ids=self._checked_plugin_ids(),
            status_message=message,
        )

    def _set_selected_enabled(self, enabled: bool) -> None:
        targets = self._action_plugins()
        eligible = tuple(
            plugin
            for plugin in targets
            if plugin.installed
            and plugin.enabled != enabled
            and plugin.compatible
            and (
                not enabled
                or not plugin.requires_api_key
                or plugin.api_key_configured
            )
        )
        if not eligible:
            return
        changed: list[PluginRecord] = []
        failures: list[str] = []
        for plugin in eligible:
            try:
                changed.append(
                    self.plugin_service.set_enabled(
                        plugin.plugin_id,
                        enabled,
                    )
                )
            except Exception as error:
                failures.append(f"{plugin.name}: {error}")
        state = "Active" if enabled else "Disabled"
        message = (
            f"{changed[0].name} is now {state}."
            if len(changed) == 1
            else f"{len(changed)} plugins are now {state}."
            if changed
            else f"No plugins were changed to {state}."
        )
        if failures:
            message += " Could not update: " + "; ".join(failures)
        self.refresh(
            selected_plugin_id=changed[-1].plugin_id if changed else "",
            checked_plugin_ids=self._checked_plugin_ids(),
            status_message=message,
        )

    def _delete_selected(self) -> None:
        eligible = tuple(
            plugin
            for plugin in self._action_plugins()
            if plugin.installed and not plugin.built_in
        )
        if not eligible:
            return
        names = "\n".join(f"• {plugin.name}" for plugin in eligible)
        answer = QMessageBox.question(
            self,
            "Delete Selected Plugin Packages?",
            (
                "The following downloaded plugin packages will be permanently "
                "deleted from Twano:\n\n"
                f"{names}\n\n"
                "Approved built-in plugins are never deleted."
            )
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        deleted: list[str] = []
        failures: list[str] = []
        for plugin in eligible:
            try:
                deleted.append(
                    self.plugin_service.delete_package(plugin.plugin_id)
                )
            except Exception as error:
                failures.append(f"{plugin.name}: {error}")
        message = (
            f"{deleted[0]} was deleted."
            if len(deleted) == 1
            else f"{len(deleted)} plugin packages were deleted."
            if deleted
            else "No plugin packages were deleted."
        )
        if failures:
            message += " Could not delete: " + "; ".join(failures)
        self.refresh(
            checked_plugin_ids=(
                self._checked_plugin_ids()
                - {plugin.plugin_id for plugin in eligible}
            ),
            status_message=message,
        )

    def _open_source(self) -> None:
        plugin = self._selected_plugin()
        if plugin and plugin.source_url:
            QDesktopServices.openUrl(QUrl(plugin.source_url))

    def _check_connection(self) -> None:
        plugin = self._selected_plugin()
        if (
            plugin is None
            or self.check_connection_thread is not None
            or not plugin.installed
            or not plugin.enabled
        ):
            return
        self.check_connection_button.setEnabled(False)
        self.status_label.setText(
            f"Checking {plugin.name}… this uses a small, discardable "
            "probe search, not your own library."
        )
        self.check_connection_thread = QThread(self)
        self.check_connection_worker = ProviderConnectionCheckWorker(
            self.metadata_studio_service,
            plugin.plugin_id,
        )
        self.check_connection_worker.moveToThread(
            self.check_connection_thread
        )
        self.check_connection_thread.started.connect(
            self.check_connection_worker.run
        )
        self.check_connection_worker.checked.connect(
            self._check_connection_succeeded
        )
        self.check_connection_worker.failed.connect(
            self._check_connection_failed
        )
        self.check_connection_worker.finished.connect(
            self.check_connection_thread.quit
        )
        self.check_connection_worker.finished.connect(
            self.check_connection_worker.deleteLater
        )
        self.check_connection_thread.finished.connect(
            self._check_connection_thread_finished
        )
        self.check_connection_thread.finished.connect(
            self.check_connection_thread.deleteLater
        )
        self.check_connection_thread.start()

    def _check_connection_succeeded(self, status: str, message: str) -> None:
        del status
        self.status_label.setText(message)

    def _check_connection_failed(self, message: str) -> None:
        self.status_label.setText(message)

    def _check_connection_thread_finished(self) -> None:
        self.check_connection_thread = None
        self.check_connection_worker = None
        selected = self._selected_plugin()
        self.refresh(
            selected_plugin_id=selected.plugin_id if selected else "",
            checked_plugin_ids=self._checked_plugin_ids(),
        )

    def _configure_api_key(self) -> None:
        plugin = self._selected_plugin()
        if (
            plugin is None
            or not plugin.installed
            or not (plugin.requires_api_key or plugin.optional_api_key)
        ):
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Configure {plugin.name}")
        dialog.setMinimumWidth(520)
        heading = QLabel(f"<b>{plugin.name} API key</b>")
        instructions = QLabel(
            self._api_key_instructions(plugin)
            + (
                f'<br><br><a href="{plugin.api_key_help_url}">'
                "Open the provider's API key page</a>"
                if plugin.api_key_help_url
                else ""
            )
        )
        instructions.setWordWrap(True)
        instructions.setOpenExternalLinks(True)
        note = QLabel(
            plugin.api_key_note
            + "<br><br>Twano encrypts the key for your current Windows "
            "account. It is never displayed again or included in diagnostics."
        )
        note.setWordWrap(True)

        key_edit = QLineEdit()
        key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        key_edit.setPlaceholderText(
            "A key is already saved — enter a replacement"
            if plugin.api_key_configured
            else "The saved key cannot be unlocked — paste it again"
            if plugin.api_key_unreadable
            else "Paste the API key or token here"
        )
        show_key = QCheckBox("Show while typing")
        show_key.toggled.connect(
            lambda checked: key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal
                if checked
                else QLineEdit.EchoMode.Password
            )
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        clear_button = None
        if plugin.api_key_configured or plugin.api_key_unreadable:
            clear_button = QPushButton("Remove Saved Key")

        layout = QVBoxLayout(dialog)
        layout.addWidget(heading)
        layout.addWidget(instructions)
        layout.addWidget(note)
        layout.addWidget(key_edit)
        layout.addWidget(show_key)
        action_row = QHBoxLayout()
        if clear_button is not None:
            action_row.addWidget(clear_button)
        action_row.addStretch()
        action_row.addWidget(buttons)
        layout.addLayout(action_row)

        if clear_button is not None:
            clear_button.clicked.connect(
                lambda: self._remove_api_key(plugin, dialog)
            )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            changed = self.plugin_service.set_api_key(
                plugin.plugin_id,
                key_edit.text(),
            )
        except Exception as error:
            self.status_label.setText(str(error))
            return
        self.refresh(
            selected_plugin_id=changed.plugin_id,
            status_message=(
                f"{changed.name} API key was saved securely. "
                + (
                    "Choose Enable to make the provider Active."
                    if not changed.enabled
                    else "The active provider will use it on the next search."
                )
            ),
        )

    def _remove_api_key(
        self,
        plugin: PluginRecord,
        dialog: QDialog,
    ) -> None:
        answer = QMessageBox.question(
            dialog,
            "Remove Saved API Key?",
            (
                f"Remove the saved key and disable {plugin.name}?"
                if plugin.requires_api_key
                else (
                    f"Remove the saved key from {plugin.name}? The provider "
                    "can remain active, but availability may be reduced."
                )
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        changed = self.plugin_service.clear_api_key(plugin.plugin_id)
        dialog.reject()
        self.refresh(
            selected_plugin_id=changed.plugin_id,
            status_message=(
                f"{changed.name} API key was removed. "
                + (
                    "The plugin is disabled."
                    if changed.requires_api_key
                    else "The provider remains available without a key."
                )
            ),
        )

    @staticmethod
    def _api_key_instructions(plugin: PluginRecord) -> str:
        if plugin.plugin_id == "hardcover_metadata":
            return (
                "1. Create or sign in to a Hardcover account.<br>"
                "2. Open Account → API.<br>"
                "3. Generate or copy your API token.<br>"
                "4. Return to Twano and paste the token below. You may paste "
                "it with or without the word Bearer."
            )
        if plugin.plugin_id == "comic_vine_metadata":
            return (
                "1. Create or sign in to a Comic Vine account.<br>"
                "2. Open its API page and review the usage terms.<br>"
                "3. Copy the API key shown for your account.<br>"
                "4. Return to Twano and paste the key below."
            )
        if plugin.plugin_id == "google_books_covers":
            return (
                "Google Books normally works without a key. If Twano reports "
                "it as unavailable:<br>"
                "1. Sign in to Google Cloud Console.<br>"
                "2. Create or select a project and enable Books API.<br>"
                "3. Open Credentials and create an API key.<br>"
                "4. Restrict the key to Books API, then paste it below."
            )
        if plugin.plugin_id == "big_book_metadata":
            return (
                "1. Open the Big Book API pricing or account page.<br>"
                "2. Create an account and choose the free plan if its "
                "non-commercial terms suit your use.<br>"
                "3. Copy the API key from the console.<br>"
                "4. Return to Twano and paste the key below. The free plan "
                "has a small daily request limit."
            )
        if plugin.plugin_id == "openweb_ninja_metadata":
            return (
                "1. Create an OpenWeb Ninja account.<br>"
                "2. Open the API dashboard and create an API key.<br>"
                "3. Confirm the Real-Time Books Data API is available.<br>"
                "4. Return to Twano and paste the key below. The free plan "
                "has a hard monthly request limit."
            )
        return "Open the provider's account page, create a key, and paste it below."

    def _install_package(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Install Verified Twano Plugin",
            "",
            "Twano Plugins (*.twano-plugin)",
        )
        if not path:
            return
        catalogue_path = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "approved-plugin-catalog.json"
        )
        try:
            raw = json.loads(catalogue_path.read_text(encoding="utf-8"))
            hashes = {
                str(item["id"]): str(item["sha256"])
                for item in raw.get("packages", ())
            }
            plugin = self.plugin_service.install_package(
                path,
                approved_hashes=hashes,
            )
        except Exception as error:
            self.status_label.setText(str(error))
            return
        self.refresh(
            selected_plugin_id=plugin.plugin_id,
            status_message=(
                f"{plugin.name} was verified and installed Disabled. "
                "Review it, then choose Enable when ready."
            ),
        )

    def _detect_calibre(self) -> None:
        found = self.integration_service.detect_calibre()
        if found.available:
            version = f"\n{found.version}" if found.version else ""
            self.calibre_status.setText(
                "Calibre detected safely at "
                f"{found.calibre_path}{version}\nTwano uses documented "
                "commands and never writes directly to metadata.db."
            )
        else:
            self.calibre_status.setText(
                "Calibre was not detected. Twano can still open books with "
                "the Windows default reader."
            )

    def _choose_calibre_library(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose Calibre Library",
        )
        if folder:
            self.calibre_folder.setText(folder)
            self._inspect_calibre_library()

    def _inspect_calibre_library(self) -> None:
        result = self.integration_service.inspect_calibre_library(
            self.calibre_folder.text()
        )
        self.status_label.setText(result.message)

    def _open_calibre_library(self) -> None:
        try:
            self.integration_service.open_calibre_library(
                self.calibre_folder.text()
            )
        except Exception as error:
            self.status_label.setText(str(error))

    def _add_calibre_source(self) -> None:
        result = self.integration_service.inspect_calibre_library(
            self.calibre_folder.text()
        )
        if not result.valid:
            self.status_label.setText(result.message)
            return
        self.scan_source_requested.emit(result.folder)

    def _check_network_path(self) -> None:
        path = self.network_path.text().strip()
        valid, shape = self.integration_service.network_path_shape(path)
        if not valid:
            self.status_label.setText(shape)
            return
        availability = (
            "available now" if Path(path).is_dir() else "currently offline"
        )
        self.status_label.setText(
            f"{shape}; the location is {availability}. Offline sources are "
            "kept separate from missing books."
        )


def _api_key_table_status(plugin: PluginRecord) -> str:
    """Describe credential state without exposing any credential material."""
    if not (plugin.requires_api_key or plugin.optional_api_key):
        return "None Required"
    if plugin.api_key_unreadable:
        return "Needs Re-entry"
    if plugin.api_key_configured:
        return "API Key Added"
    return "Not Added"


def _provider_health_table_status(plugin: PluginRecord) -> str:
    """Translate parser health into a short non-technical table value."""
    if not {
        "metadata_provider",
        "cover_provider",
    }.intersection(plugin.capabilities):
        return "Not Applicable"
    return {
        "healthy": "Working",
        "blocked": "Access Blocked",
        "layout_changed": "Provider Update Needed",
        "unavailable": "Temporarily Unavailable",
        "not_checked": "Not Checked Yet",
    }.get(plugin.provider_health, "Not Checked Yet")

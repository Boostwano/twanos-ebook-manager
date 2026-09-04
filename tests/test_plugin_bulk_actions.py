"""Checkbox-based plugin actions should work for safe batches."""

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from services.integration_service import IntegrationService
from services.plugin_service import PluginService
from ui.plugin_page import PluginPage


def _row_for(page: PluginPage, plugin_id: str) -> int:
    return next(
        row
        for row, plugin in enumerate(page.plugins)
        if plugin.plugin_id == plugin_id
    )


def _check(page: PluginPage, plugin_id: str) -> None:
    page.plugin_table.item(_row_for(page, plugin_id), 0).setCheckState(
        Qt.CheckState.Checked
    )


def _status(page: PluginPage, plugin_id: str) -> str:
    return page.plugin_table.item(_row_for(page, plugin_id), 4).text()


def test_checked_plugins_install_enable_disable_and_uninstall_together(
    tmp_path,
) -> None:
    application = QApplication.instance() or QApplication([])
    service = PluginService(
        tmp_path / "plugins",
        tmp_path / "state.json",
    )
    page = PluginPage(service, IntegrationService())
    _check(page, "open_library_metadata")
    _check(page, "google_books_covers")
    application.processEvents()

    assert page.install_button.isEnabled()
    page.install_button.click()
    assert _status(page, "open_library_metadata") == "Disabled"
    assert _status(page, "google_books_covers") == "Disabled"
    assert page._checked_plugin_ids() == {
        "open_library_metadata",
        "google_books_covers",
    }

    page.enable_button.click()
    assert _status(page, "open_library_metadata") == "Active"
    assert _status(page, "google_books_covers") == "Active"

    page.disable_button.click()
    assert _status(page, "open_library_metadata") == "Disabled"
    assert _status(page, "google_books_covers") == "Disabled"

    page.uninstall_button.click()
    assert _status(page, "open_library_metadata") == "Available"
    assert _status(page, "google_books_covers") == "Available"
    assert "2 plugins were uninstalled" in page.status_label.text()
    page.close()


def test_plugins_can_be_sorted_alphabetically_in_both_directions(
    tmp_path,
) -> None:
    _application = QApplication.instance() or QApplication([])
    page = PluginPage(
        PluginService(tmp_path / "plugins", tmp_path / "state.json"),
        IntegrationService(),
    )

    ascending = [plugin.name for plugin in page.plugins]
    assert ascending == sorted(ascending, key=str.casefold)

    selected_id = page.plugins[1].plugin_id
    page.plugin_table.selectRow(1)
    _check(page, page.plugins[2].plugin_id)
    checked_ids = page._checked_plugin_ids()
    page.plugin_sort_combo.setCurrentIndex(1)

    descending = [plugin.name for plugin in page.plugins]
    assert descending == sorted(
        descending,
        key=str.casefold,
        reverse=True,
    )
    assert page._selected_plugin().plugin_id == selected_id
    assert page._checked_plugin_ids() == checked_ids
    page.close()


def test_delete_checked_external_package_requires_confirmation(
    tmp_path,
    monkeypatch,
) -> None:
    _application = QApplication.instance() or QApplication([])
    plugin_folder = tmp_path / "plugins"
    package_folder = plugin_folder / "sample_external"
    package_folder.mkdir(parents=True)
    manifest = {
        "id": "sample_external",
        "name": "Sample External",
        "publisher": "Example Publisher",
        "version": "1.0",
        "api_version": 1,
        "description": "A test-only external provider.",
        "source_url": "https://example.com/plugin",
        "capabilities": ["metadata_provider"],
    }
    (package_folder / "plugin.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    service = PluginService(plugin_folder, tmp_path / "state.json")
    page = PluginPage(service, IntegrationService())
    _check(page, "sample_external")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    assert page.delete_button.isEnabled()
    page.delete_button.click()

    assert not package_folder.exists()
    assert all(
        plugin.plugin_id != "sample_external"
        for plugin in page.plugins
    )
    assert "was deleted" in page.status_label.text()
    page.close()

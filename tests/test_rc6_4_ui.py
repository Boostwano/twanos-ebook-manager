"""Offscreen PySide6 interface checks for RC6.4."""

from pathlib import Path

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyleOptionButton,
)

from main_window import MainWindow, PAGE_IDS
from database.database import DatabaseManager
from preferences import BANNER_NAMES, BannerRotation, PreferencesStore
from services.banner_service import BannerService
from services.dashboard_service import DashboardService
from services.library_service import LibraryService
from services.protection_service import ProtectionService
from services.scan_service import ScanService
from ui.dashboard import DashboardPage
from ui.sidebar import NAVIGATION_PAGE_IDS, ResponsiveSidebar
from ui.theme import APP_STYLESHEET


class FakeDatabase:
    def __init__(self) -> None:
        self.search_calls = []
        self.rows = [
            {
                "title": "Example Book",
                "file_name": "Example Book.epub",
                "author": "A. Reader",
                "isbn": "",
                "publisher": "",
                "published_date": "",
                "language": "en",
                "series": "",
                "description": "",
                "cover_path": "",
                "file_format": "EPUB",
                "file_size": 1024,
                "metadata_status": "pending",
                "review_required": 1,
                "file_path": "C:/Books/Example Book.epub",
                "library_folder": "C:/Books",
            }
        ]

    def get_dashboard_statistics(self):
        return {
            "total_books": 1,
            "embedded_metadata": 0,
            "needs_metadata": 1,
            "missing_books": 0,
            "total_size": 1024,
            "library_count": 1,
            "metadata_health": 0,
            "formats": {"EPUB": 1},
            "recent_books": (),
        }

    def get_library_filter_options(self):
        return ["EPUB"], ["pending"]

    def search_books(self, **filters):
        self.search_calls.append(filters)
        query = str(filters.get("search_text", "")).casefold()
        if query and query not in "example book a. reader":
            return []
        if (
            filters.get("metadata_attention")
            and self.rows[0]["metadata_status"] == "embedded"
        ):
            return []
        return self.rows

    def count_books(self):
        return len(self.rows)


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _preferences(tmp_path: Path) -> PreferencesStore:
    settings = QSettings(
        str(tmp_path / "preferences.ini"),
        QSettings.Format.IniFormat,
    )
    return PreferencesStore(settings)


def _background_service_factories(tmp_path: Path) -> dict[str, object]:
    """Keep MainWindow tests away from the real user catalogue."""
    database_path = tmp_path / "window-services.db"
    return {
        "scan_service_factory": lambda: ScanService(
            DatabaseManager(database_path)
        ),
        "protection_service_factory": lambda: ProtectionService(
            DatabaseManager(database_path)
        ),
    }


def _button_content_origin(button: QPushButton, *, down: bool) -> QPoint:
    button.setDown(down)
    option = QStyleOptionButton()
    button.initStyleOption(option)
    return button.style().subElementRect(
        QStyle.SubElement.SE_PushButtonContents,
        option,
        button,
    ).topLeft()


def test_all_button_styles_move_content_when_pressed(tmp_path: Path) -> None:
    application = _application()
    generic = QPushButton("Generic action")
    generic.setStyleSheet(APP_STYLESHEET)
    generic.resize(180, 52)
    generic.show()

    footer = QPushButton("Check for Updates")
    footer.setObjectName("footerUpdateAction")
    footer.setStyleSheet(APP_STYLESHEET)
    footer.resize(180, 52)
    footer.show()

    database = FakeDatabase()
    dashboard = DashboardPage(
        DashboardService(database),
        _preferences(tmp_path),
        library_service=LibraryService(database),
    )
    dashboard.resize(1000, 700)
    dashboard.show()
    application.processEvents()

    for button in (
        generic,
        footer,
        dashboard.search_button,
        dashboard.hero.scan_button,
        dashboard.action_buttons[0],
    ):
        normal = _button_content_origin(button, down=False)
        pressed = _button_content_origin(button, down=True)
        assert pressed == normal + QPoint(2, 2)
        button.setDown(False)

    generic.deleteLater()
    footer.deleteLater()
    dashboard.deleteLater()
    application.processEvents()


def test_sidebar_fits_common_desktop_heights() -> None:
    application = _application()
    sidebar = ResponsiveSidebar()

    for width, height in (
        (1280, 720),
        (1366, 768),
        (1600, 900),
        (1920, 1080),
        (2560, 1440),
    ):
        sidebar.apply_responsive_size(width, height)
        sidebar.setFixedHeight(height)
        sidebar.show()
        application.processEvents()

        assert 18 <= sidebar.brand_header.app_name.font().pointSize() <= 40
        assert "font-size:" in sidebar.brand_header.app_name.styleSheet()
        assert "font-size:" in sidebar.brand_header.app_subtitle.styleSheet()
        assert sidebar.brand_header.app_name.width() == (
            sidebar.brand_header.app_subtitle.width()
        )
        assert not sidebar.navigation.verticalScrollBar().isVisible()
        viewport_height = sidebar.navigation.viewport().height()
        for row in range(sidebar.navigation.count()):
            rectangle = sidebar.navigation.visualItemRect(
                sidebar.navigation.item(row)
            )
            assert rectangle.top() >= 0
            assert rectangle.bottom() < viewport_height

    assert sidebar.page_ids == NAVIGATION_PAGE_IDS
    assert sidebar.brand_header.app_name.text() == "Twano's"
    assert sidebar.brand_header.app_subtitle.text() == "eBook Manager"
    assert (
        sidebar.brand_header.app_name.alignment()
        & Qt.AlignmentFlag.AlignHCenter
    )
    assert (
        sidebar.brand_header.app_subtitle.alignment()
        & Qt.AlignmentFlag.AlignHCenter
    )
    sidebar.deleteLater()
    application.processEvents()


def test_home_popup_does_not_move_cards_and_escape_closes(
    tmp_path: Path,
) -> None:
    application = _application()
    database = FakeDatabase()
    page = DashboardPage(
        DashboardService(database),
        _preferences(tmp_path),
        library_service=LibraryService(database),
    )
    page.resize(1200, 760)
    page.show()
    application.processEvents()
    cards_top = page.cards_container.geometry().top()

    page.search.setFocus()
    page.search.setText("exa")
    application.processEvents()

    assert page.suggestion_popup.isVisible()
    assert page.layout_box.indexOf(page.suggestion_popup) == -1
    assert page.cards_container.geometry().top() == cards_top

    QTest.keyClick(page.search, Qt.Key.Key_Escape)
    application.processEvents()
    assert not page.suggestion_popup.isVisible()
    page.deleteLater()
    application.processEvents()


def test_home_keeps_reference_three_card_layout_without_page_scroll(
    tmp_path: Path,
) -> None:
    application = _application()
    database = FakeDatabase()
    page = DashboardPage(
        DashboardService(database),
        _preferences(tmp_path),
        library_service=LibraryService(database),
    )
    page.resize(690, 600)
    page.show()
    application.processEvents()

    cards = [
        child
        for child in page.cards_container.findChildren(
            QFrame,
            options=Qt.FindChildOption.FindDirectChildrenOnly,
        )
        if child.objectName() == "homeCard"
    ]
    assert cards == [page.summary, page.activity, page.actions]
    assert page.hero.scan_button.isVisible()
    assert page.hero.open_library_button.isVisible()
    assert page.smart_insight.parentWidget() is page.summary
    assert page.cards_container.geometry().bottom() <= page.height()
    assert not page.findChildren(QScrollArea)
    hero_requests: list[str] = []
    page.scan_requested.connect(lambda: hero_requests.append("scan"))
    page.open_library_requested.connect(
        lambda _query: hero_requests.append("library")
    )
    page.hero.scan_button.click()
    page.hero.open_library_button.click()
    assert hero_requests == ["scan", "library"]

    page.deleteLater()
    application.processEvents()


def test_hero_greetings_have_metric_safe_height(
    tmp_path: Path,
) -> None:
    application = _application()
    database = FakeDatabase()
    page = DashboardPage(
        DashboardService(database),
        _preferences(tmp_path),
        library_service=LibraryService(database),
    )
    page.resize(1000, 700)
    page.show()
    application.processEvents()

    for greeting in (
        "Good morning.",
        "Good afternoon.",
        "Good evening.",
        "Welcome back.",
    ):
        page.hero.greeting_label.setText(greeting)
        metrics = QFontMetrics(page.hero.greeting_label.font())
        assert page.hero.greeting_label.minimumHeight() > metrics.height()
        assert page.hero.greeting_label.height() >= metrics.height()

    page.deleteLater()
    application.processEvents()


def test_home_loads_selected_banner_and_exposes_two_modes(
    tmp_path: Path,
) -> None:
    application = _application()
    database = FakeDatabase()
    window = MainWindow(
        library_service=LibraryService(database),
        dashboard_service=DashboardService(database),
        preferences=_preferences(tmp_path),
        **_background_service_factories(tmp_path),
    )
    window.resize(1280, 720)
    window.show()
    application.processEvents()

    assert window.dashboard_page.hero.has_banner_image
    assert window.dashboard_page.hero.has_title_overlay
    assert (
        window.dashboard_page.hero.banner_asset_path.name
        == "grand-library.png"
    )
    assert not window.dashboard_page.hero.theme_label.isVisible()
    assert window.settings_page.banner_combo.count() == len(BANNER_NAMES)
    assert {
        window.settings_page.rotation_combo.itemData(index)
        for index in range(
            window.settings_page.rotation_combo.count()
        )
    } == {BannerRotation.FIXED, BannerRotation.STARTUP}

    window.close()
    application.processEvents()


def test_home_uses_painted_fallback_when_banner_assets_are_missing(
    tmp_path: Path,
) -> None:
    application = _application()
    database = FakeDatabase()
    page = DashboardPage(
        DashboardService(database),
        _preferences(tmp_path),
        library_service=LibraryService(database),
        banner_service=BannerService(tmp_path / "missing-banners"),
    )
    page.resize(1000, 700)
    page.show()
    application.processEvents()

    assert not page.hero.has_banner_image
    assert page.hero.banner_asset_path is None
    assert page.hero.theme_label.isVisible()
    assert not page.grab().isNull()

    page.deleteLater()
    application.processEvents()


def test_card_typography_scales_with_both_dimensions(
    tmp_path: Path,
) -> None:
    application = _application()
    database = FakeDatabase()
    page = DashboardPage(
        DashboardService(database),
        _preferences(tmp_path),
        library_service=LibraryService(database),
    )
    page.resize(900, 600)
    page.show()
    application.processEvents()
    compact_size = page.summary.title_label.font().pointSize()
    compact_action = page.action_buttons[0].minimumHeight()
    compact_cards_height = page.cards_container.height()
    compact_hero_height = page.hero.height()
    assert compact_hero_height == page.hero.responsive_height(
        page.width() - 30,
        page.height(),
    )

    page.resize(1900, 1200)
    application.processEvents()
    large_size = page.summary.title_label.font().pointSize()
    large_action = page.action_buttons[0].minimumHeight()

    assert large_size > compact_size
    assert large_action > compact_action
    assert page.hero.height() > compact_hero_height
    assert page.hero.height() <= round(
        page.height() * page.hero.MAXIMUM_PAGE_SHARE
    )
    assert page.cards_container.height() > compact_cards_height
    page.deleteLater()
    application.processEvents()


def test_enter_routes_to_search_and_home_resets(
    tmp_path: Path,
) -> None:
    application = _application()
    database = FakeDatabase()
    service = LibraryService(database)
    window = MainWindow(
        library_service=service,
        dashboard_service=DashboardService(database),
        preferences=_preferences(tmp_path),
        **_background_service_factories(tmp_path),
    )
    window.resize(1280, 720)
    window.show()
    application.processEvents()

    window.dashboard_page.search.setText("Example")
    QTest.keyClick(
        window.dashboard_page.search,
        Qt.Key.Key_Return,
    )
    application.processEvents()

    assert window._current_page_id == "search"
    assert window.search_results_page.query == "Example"

    window._show_page("home")
    application.processEvents()
    assert window.dashboard_page.search.text() == ""
    assert not window.dashboard_page.suggestion_popup.isVisible()
    assert not window.dashboard_page.search.hasFocus()
    window.close()
    application.processEvents()


def test_review_now_routes_to_filtered_review_queue(
    tmp_path: Path,
) -> None:
    application = _application()
    database = FakeDatabase()
    window = MainWindow(
        library_service=LibraryService(database),
        dashboard_service=DashboardService(database),
        preferences=_preferences(tmp_path),
        **_background_service_factories(tmp_path),
    )
    window.show()
    application.processEvents()
    database.search_calls.clear()

    assert window.dashboard_page.smart_insight.action_button.text() == (
        "Review Now"
    )
    window.dashboard_page.smart_insight.action_button.click()
    application.processEvents()

    assert window._current_page_id == "review_queue"
    assert any(
        call.get("metadata_attention") is True
        for call in database.search_calls
    )
    assert tuple(window.pages_by_id) == PAGE_IDS
    window.close()
    application.processEvents()

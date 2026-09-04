"""Twano R4 RC6.4 responsive Home and floating smart search."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from preferences import PreferencesStore
from services.banner_service import BannerService
from services.dashboard_service import DashboardData, DashboardService
from services.library_service import LibraryRecord, LibraryService
from services.welcome_service import WelcomeService
from ui.book_actions import open_book
from ui.responsive import responsive_scale, scaled
from ui.search_components import SearchField, SearchSuggestionPopup


def format_file_size(size_bytes: int) -> str:
    """Convert bytes into a compact Home summary value."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes:,} B"


class SquareHero(QWidget):
    """Banner artwork with naturally sized text and a painted fallback."""

    scan_requested = Signal()
    open_library_requested = Signal()

    FIXED_HEIGHT = 200
    MINIMUM_HEIGHT = 180
    MAXIMUM_PAGE_SHARE = 0.52
    BANNER_ASPECT_RATIO = 2048 / 682
    BANNER_MIDDLE_COLOR = QColor("#061522")

    def __init__(self) -> None:
        super().__init__()
        self.theme = "The Grand Library"
        self.banner_asset_path: Path | None = None
        self._banner_pixmap = QPixmap()
        self._background_pixmap = QPixmap()
        self._title_overlay_pixmap = QPixmap()
        self.setFixedHeight(self.FIXED_HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.greeting_label = QLabel("Welcome back.")
        self.greeting_label.setObjectName("heroGreeting")
        self.greeting_label.setWordWrap(False)
        self.summary_label = QLabel("Your library is ready.")
        self.summary_label.setObjectName("heroSummary")
        self.summary_label.setWordWrap(True)
        self.insight_label = QLabel()
        self.insight_label.setObjectName("heroInsight")
        self.insight_label.setWordWrap(True)
        self.theme_label = QLabel(self.theme.upper())
        self.theme_label.setObjectName("heroTheme")

        self.scan_button = QPushButton("Scan Library")
        self.scan_button.setObjectName("heroPrimaryAction")
        self.scan_button.clicked.connect(self.scan_requested.emit)
        self.open_library_button = QPushButton("Open Library")
        self.open_library_button.setObjectName("heroSecondaryAction")
        self.open_library_button.clicked.connect(
            self.open_library_requested.emit
        )
        self.action_row = QWidget()
        self.action_row.setObjectName("heroActions")
        self.action_layout = QHBoxLayout(self.action_row)
        self.action_layout.setContentsMargins(0, 0, 0, 0)
        self.action_layout.setSpacing(10)
        self.action_layout.addWidget(self.scan_button)
        self.action_layout.addWidget(self.open_library_button)
        self.action_layout.addStretch()

        self.content_layout = QVBoxLayout(self)
        self.content_layout.addWidget(self.greeting_label)
        self.content_layout.addWidget(self.summary_label)
        self.content_layout.addWidget(self.insight_label)
        self.content_layout.addWidget(self.action_row)
        self.content_layout.addStretch()
        self.content_layout.addWidget(self.theme_label)
        self.set_responsive_scale(0.8)

    def set_content(
        self,
        theme: str,
        greeting: str,
        summary: str,
        insight: str,
        banner_asset_path: Path | None = None,
    ) -> None:
        self.theme = theme
        self.banner_asset_path = banner_asset_path
        self._banner_pixmap = (
            QPixmap(str(banner_asset_path))
            if banner_asset_path is not None
            else QPixmap()
        )
        background_path = self._background_path(banner_asset_path)
        self._background_pixmap = (
            QPixmap(str(background_path))
            if background_path is not None
            else QPixmap()
        )
        title_overlay_path = self._title_overlay_path(banner_asset_path)
        self._title_overlay_pixmap = (
            QPixmap(str(title_overlay_path))
            if title_overlay_path is not None
            else QPixmap()
        )
        self.greeting_label.setText(greeting)
        self.summary_label.setText(summary)
        self.insight_label.setText(insight)
        self.insight_label.setVisible(bool(insight))
        self.theme_label.setText(theme.upper())
        self.theme_label.setVisible(not self.has_title_overlay)
        self.update()

    @property
    def has_banner_image(self) -> bool:
        """Return whether the selected image loaded successfully."""
        return not self._background_pixmap.isNull() or not (
            self._banner_pixmap.isNull()
        )

    @property
    def has_title_overlay(self) -> bool:
        """Return whether the selected banner has transparent title art."""
        return not self._title_overlay_pixmap.isNull()

    @staticmethod
    def _title_overlay_path(
        banner_asset_path: Path | None,
    ) -> Path | None:
        """Resolve the matching transparent title PNG for a banner."""
        if banner_asset_path is None:
            return None
        return (
            banner_asset_path.parent.parent
            / "banner-title-overlays"
            / f"{banner_asset_path.stem}-title.png"
        )

    @staticmethod
    def _background_path(
        banner_asset_path: Path | None,
    ) -> Path | None:
        """Resolve the matching title-free faded banner background."""
        if banner_asset_path is None:
            return None
        return (
            banner_asset_path.parent.parent
            / "banner-backgrounds"
            / f"{banner_asset_path.stem}-background.png"
        )

    @classmethod
    def responsive_height(
        cls,
        width: int,
        available_height: int,
    ) -> int:
        """Preserve banner proportions without crowding the Home cards."""
        ideal_height = round(max(0, width) / cls.BANNER_ASPECT_RATIO)
        maximum_height = max(
            cls.MINIMUM_HEIGHT,
            round(max(0, available_height) * cls.MAXIMUM_PAGE_SHARE),
        )
        return max(
            cls.MINIMUM_HEIGHT,
            min(ideal_height, maximum_height),
        )

    def set_responsive_scale(self, scale: float) -> None:
        """Update fonts and use metrics for safe greeting height."""
        greeting_font = QFont(
            "Segoe UI",
            scaled(scale, 38, 25, 50),
            QFont.Weight.Bold,
        )
        self.greeting_label.setFont(greeting_font)
        greeting_metrics = QFontMetrics(greeting_font)
        self.greeting_label.setMinimumHeight(
            greeting_metrics.height() + scaled(scale, 8, 5, 12)
        )
        self.summary_label.setFont(
            QFont("Segoe UI", scaled(scale, 17, 12, 22))
        )
        self.insight_label.setFont(
            QFont(
                "Segoe UI",
                scaled(scale, 14, 11, 18),
                QFont.Weight.DemiBold,
            )
        )
        self.theme_label.setFont(
            QFont(
                "Segoe UI",
                scaled(scale, 11, 9, 14),
                QFont.Weight.DemiBold,
            )
        )
        action_font = QFont(
            "Segoe UI",
            scaled(scale, 13, 10, 16),
            QFont.Weight.DemiBold,
        )
        action_height = scaled(scale, 34, 29, 42)
        for button in (self.scan_button, self.open_library_button):
            button.setFont(action_font)
            button.setMinimumHeight(action_height)
        horizontal = scaled(scale, 34, 22, 48)
        vertical = scaled(scale, 18, 12, 24)
        self.content_layout.setContentsMargins(
            horizontal,
            vertical,
            horizontal,
            vertical,
        )
        self.content_layout.setSpacing(scaled(scale, 6, 3, 9))
        self.action_layout.setSpacing(scaled(scale, 10, 6, 14))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        text_width = max(250, int(self.width() * 0.57))
        for label in (
            self.greeting_label,
            self.summary_label,
            self.insight_label,
            self.theme_label,
        ):
            label.setMaximumWidth(text_width)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform
        )
        rectangle = self.rect().adjusted(1, 1, -1, -1)

        if self.has_banner_image:
            self._paint_banner_image(painter, rectangle)
        else:
            self._paint_fallback_scene(painter, rectangle)

        backdrop_rectangle = QRect(
            rectangle.left(),
            rectangle.top(),
            int(rectangle.width() * 0.64),
            rectangle.height(),
        )
        text_backdrop = QLinearGradient(
            backdrop_rectangle.topLeft(),
            backdrop_rectangle.topRight(),
        )
        text_backdrop.setColorAt(0, QColor(4, 10, 15, 145))
        text_backdrop.setColorAt(0.58, QColor(4, 10, 15, 72))
        text_backdrop.setColorAt(0.82, QColor(4, 10, 15, 20))
        text_backdrop.setColorAt(1, QColor(4, 10, 15, 0))
        painter.fillRect(backdrop_rectangle, text_backdrop)
        self._paint_title_overlay(painter, rectangle)
        painter.setPen(QPen(QColor("#31546a"), 1))
        painter.drawRect(rectangle)
        painter.end()

    def _paint_banner_image(
        self,
        painter: QPainter,
        rectangle: QRect,
    ) -> None:
        """Compose a seamless banner scene with transparent title art."""
        painter.fillRect(rectangle, self.BANNER_MIDDLE_COLOR)
        artwork = (
            self._background_pixmap
            if not self._background_pixmap.isNull()
            else self._banner_pixmap
        )
        source = artwork.rect()
        scale = rectangle.height() / max(1, source.height())
        left_source_width = round(source.width() * 0.44)
        right_source_left = round(source.width() * 0.42)
        left_target_width = round(left_source_width * scale)
        right_target_width = round(
            (source.width() - right_source_left) * scale
        )

        if left_target_width + right_target_width >= rectangle.width():
            scaled_banner = artwork.scaled(
                rectangle.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            target = QRect(
                rectangle.left()
                + (rectangle.width() - scaled_banner.width()) // 2,
                rectangle.top()
                + (rectangle.height() - scaled_banner.height()) // 2,
                scaled_banner.width(),
                scaled_banner.height(),
            )
            painter.drawPixmap(target, scaled_banner)
            return

        left_target = QRect(
            rectangle.left(),
            rectangle.top(),
            left_target_width,
            rectangle.height(),
        )
        right_target = QRect(
            rectangle.right() - right_target_width + 1,
            rectangle.top(),
            right_target_width,
            rectangle.height(),
        )
        painter.drawPixmap(
            left_target,
            artwork,
            QRect(0, 0, left_source_width, source.height()),
        )
        painter.drawPixmap(
            right_target,
            artwork,
            QRect(
                right_source_left,
                0,
                source.width() - right_source_left,
                source.height(),
            ),
        )

        fade_width = max(36, min(120, round(rectangle.width() * 0.06)))
        left_fade = QRect(
            left_target.right() - fade_width + 1,
            rectangle.top(),
            fade_width,
            rectangle.height(),
        )
        left_gradient = QLinearGradient(
            left_fade.topLeft(),
            left_fade.topRight(),
        )
        left_gradient.setColorAt(
            0,
            QColor(
                self.BANNER_MIDDLE_COLOR.red(),
                self.BANNER_MIDDLE_COLOR.green(),
                self.BANNER_MIDDLE_COLOR.blue(),
                0,
            ),
        )
        left_gradient.setColorAt(1, self.BANNER_MIDDLE_COLOR)
        painter.fillRect(left_fade, left_gradient)

        right_fade = QRect(
            right_target.left(),
            rectangle.top(),
            fade_width,
            rectangle.height(),
        )
        right_gradient = QLinearGradient(
            right_fade.topLeft(),
            right_fade.topRight(),
        )
        right_gradient.setColorAt(0, self.BANNER_MIDDLE_COLOR)
        right_gradient.setColorAt(
            1,
            QColor(
                self.BANNER_MIDDLE_COLOR.red(),
                self.BANNER_MIDDLE_COLOR.green(),
                self.BANNER_MIDDLE_COLOR.blue(),
                0,
            ),
        )
        painter.fillRect(right_fade, right_gradient)

    def _paint_title_overlay(
        self,
        painter: QPainter,
        rectangle: QRect,
    ) -> None:
        """Paint gold title art above readability shading."""
        if not self.has_title_overlay:
            return
        maximum_width = max(180, round(rectangle.width() * 0.38))
        maximum_height = max(58, round(rectangle.height() * 0.43))
        title = self._title_overlay_pixmap.scaled(
            maximum_width,
            maximum_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        horizontal_margin = max(20, round(rectangle.width() * 0.025))
        bottom_margin = max(12, round(rectangle.height() * 0.055))
        title_target = QRect(
            rectangle.left() + horizontal_margin,
            rectangle.bottom() - bottom_margin - title.height() + 1,
            title.width(),
            title.height(),
        )
        painter.drawPixmap(title_target, title)

    @staticmethod
    def _paint_fallback_scene(
        painter: QPainter,
        rectangle: QRect,
    ) -> None:
        """Retain the safe painted scene when no image can be loaded."""
        gradient = QLinearGradient(
            rectangle.topLeft(),
            rectangle.bottomRight(),
        )
        gradient.setColorAt(0, QColor("#07131d"))
        gradient.setColorAt(0.55, QColor("#102b3e"))
        gradient.setColorAt(1, QColor("#25190f"))
        painter.fillRect(rectangle, gradient)

        painter.setPen(QPen(QColor("#335a72"), 1))
        shelf_spacing = max(30, int(rectangle.height() / 5))
        for row in range(4):
            y = rectangle.bottom() - 28 - row * shelf_spacing
            painter.drawLine(
                int(rectangle.width() * 0.58),
                y,
                rectangle.right() - 28,
                y,
            )
            book_spacing = max(16, int(rectangle.width() * 0.018))
            for column in range(10):
                x = (
                    int(rectangle.width() * 0.60)
                    + column * book_spacing
                )
                book_height = (
                    20 + ((row * 7 + column * 5) % 18)
                )
                painter.fillRect(
                    x,
                    y - book_height,
                    10 + (column % 3) * 3,
                    book_height,
                    QColor(
                        44 + column * 5,
                        84 + row * 10,
                        110 + column * 3,
                        170,
                    ),
                )


class ResponsiveCard(QFrame):
    """Home card whose title, padding, and spacing scale together."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("homeCard")
        self.layout_box = QVBoxLayout(self)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("homeCardTitle")
        self.layout_box.addWidget(self.title_label)

    def apply_scale(self, scale: float) -> None:
        self.title_label.setFont(
            QFont(
                "Segoe UI",
                scaled(scale, 19, 15, 25),
                QFont.Weight.Bold,
            )
        )
        horizontal = scaled(scale, 18, 11, 28)
        vertical = scaled(scale, 15, 9, 23)
        self.layout_box.setContentsMargins(
            horizontal,
            vertical,
            horizontal,
            vertical,
        )
        self.layout_box.setSpacing(scaled(scale, 9, 5, 14))


class SmartInsight(QFrame):
    """A status message whose next action is always explicit."""

    action_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("statusBanner")
        self.action_id = ""
        self.icon_label = QLabel("●")
        self.icon_label.setObjectName("statusIcon")
        self.text_label = QLabel()
        self.text_label.setObjectName("statusText")
        self.text_label.setWordWrap(True)
        self.action_button = QPushButton()
        self.action_button.setObjectName("secondaryButton")
        self.action_button.clicked.connect(self._request_action)

        message_row = QHBoxLayout()
        message_row.setContentsMargins(0, 0, 0, 0)
        message_row.setSpacing(7)
        message_row.addWidget(self.icon_label)
        message_row.addWidget(self.text_label, 1)

        self.layout_box = QVBoxLayout(self)
        self.layout_box.addLayout(message_row)
        self.layout_box.addWidget(self.action_button)

    def set_content(
        self,
        text: str,
        *,
        action_id: str,
        action_text: str,
    ) -> None:
        self.text_label.setText(text)
        self.action_id = action_id
        self.icon_label.setText(
            {
                "review_queue": "✎",
                "library_health": "⚠",
                "scan": "⌕",
            }.get(action_id, "●")
        )
        self.action_button.setText(action_text)
        self.action_button.setVisible(bool(action_id and action_text))

    def apply_scale(self, scale: float) -> None:
        self.icon_label.setFont(
            QFont(
                "Segoe UI Symbol",
                scaled(scale, 20, 15, 27),
                QFont.Weight.DemiBold,
            )
        )
        self.text_label.setFont(
            QFont(
                "Segoe UI",
                scaled(scale, 15, 12, 19),
                QFont.Weight.DemiBold,
            )
        )
        self.action_button.setFont(
            QFont("Segoe UI", scaled(scale, 14, 11, 18))
        )
        self.action_button.setMinimumHeight(
            scaled(scale, 34, 29, 45)
        )
        horizontal = scaled(scale, 12, 8, 16)
        vertical = scaled(scale, 9, 6, 12)
        self.layout_box.setContentsMargins(
            horizontal,
            vertical,
            horizontal,
            vertical,
        )
        self.layout_box.setSpacing(scaled(scale, 10, 6, 16))

    def _request_action(self) -> None:
        if self.action_id:
            self.action_requested.emit(self.action_id)


class DashboardPage(QWidget):
    """Welcoming Home page with stationary layout and overlay search."""

    open_library_requested = Signal(str)
    search_requested = Signal(str)
    scan_requested = Signal()
    settings_requested = Signal()
    health_requested = Signal()
    metadata_requested = Signal()
    review_queue_requested = Signal()

    def __init__(
        self,
        service: DashboardService,
        preferences: PreferencesStore | None = None,
        welcome_service: WelcomeService | None = None,
        library_service: LibraryService | None = None,
        banner_service: BannerService | None = None,
    ) -> None:
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.service = service
        self.preferences = preferences or PreferencesStore()
        self.welcome_service = welcome_service or WelcomeService()
        self.library_service = library_service or LibraryService()
        self.banner_service = banner_service or BannerService()
        self._results: tuple[LibraryRecord, ...] = ()
        self.responsive_scale = 0.76

        self.hero = SquareHero()
        self.hero.scan_requested.connect(self.scan_requested.emit)
        self.hero.open_library_requested.connect(
            lambda: self.open_library_requested.emit("")
        )

        self.search = SearchField()
        self.search.setObjectName("homeSearch")
        self.search.setPlaceholderText(
            "Search by title, author, ISBN, publisher or filename…"
        )
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._live_search)
        self.search.submitted.connect(self._submit_search)
        self.search.dismissed.connect(self.close_suggestions)
        self.search.selection_requested.connect(
            self._move_suggestion_selection
        )

        self.search_button = QPushButton("Find a Book")
        self.search_button.setObjectName("primaryButton")
        self.search_button.clicked.connect(self._request_full_search)

        self.search_row = QWidget()
        search_layout = QHBoxLayout(self.search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)
        search_layout.addWidget(self.search, 1)
        search_layout.addWidget(self.search_button)

        self.smart_insight = SmartInsight()
        self.smart_insight.action_requested.connect(
            self._route_insight_action
        )

        self.summary = ResponsiveCard("▥  Library Summary")
        self.summary_labels: list[QLabel] = []
        for _ in range(4):
            label = QLabel()
            label.setObjectName("summaryMetric")
            self.summary.layout_box.addWidget(label)
            self.summary_labels.append(label)
        self.summary.layout_box.addStretch()
        self.summary.layout_box.addWidget(self.smart_insight)

        self.activity = ResponsiveCard("◷  Recent Activity")
        self.activity_labels: list[QLabel] = []
        for _ in range(4):
            label = QLabel()
            label.setObjectName("activityItem")
            label.setWordWrap(True)
            self.activity.layout_box.addWidget(label)
            self.activity_labels.append(label)
        self.activity.layout_box.addStretch()

        self.actions = ResponsiveCard("↗  Quick Links")
        self.action_buttons: list[QPushButton] = []
        actions = (
            ("⌕   Scan Library", self.scan_requested.emit),
            (
                "▤   Open Library",
                lambda: self.open_library_requested.emit(""),
            ),
            ("✎   Review Metadata", self.metadata_requested.emit),
            ("♥   Library Health", self.health_requested.emit),
            ("⚙   Settings", self.settings_requested.emit),
        )
        for text, slot in actions:
            button = QPushButton(text)
            button.setObjectName("homeAction")
            button.clicked.connect(
                lambda checked=False, callback=slot: callback()
            )
            self.actions.layout_box.addWidget(button)
            self.action_buttons.append(button)
        self.actions.layout_box.addStretch()

        self.cards_container = QWidget()
        self.cards_layout = QHBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addWidget(self.summary, 1)
        self.cards_layout.addWidget(self.activity, 1)
        self.cards_layout.addWidget(self.actions, 1)

        self.layout_box = QVBoxLayout(self)
        self.layout_box.setContentsMargins(20, 16, 20, 16)
        self.layout_box.setSpacing(12)
        self.layout_box.addWidget(self.hero)
        self.layout_box.addWidget(self.search_row)
        self.layout_box.addWidget(self.cards_container, 1)

        self.suggestion_popup = SearchSuggestionPopup(
            self,
            self.search,
        )
        self.suggestion_popup.book_requested.connect(
            self._open_suggested_book
        )
        self.suggestion_popup.all_results_requested.connect(
            self._open_all_results
        )

        self.setStyleSheet(self._style())
        self.refresh_dashboard()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_size()
        self.suggestion_popup.reposition()

    def _apply_responsive_size(self) -> None:
        width, height = self.width(), self.height()
        scale = responsive_scale(width, height)
        self.responsive_scale = scale

        horizontal_margin = scaled(scale, 20, 12, 30)
        vertical_margin = scaled(scale, 16, 9, 25)
        spacing = scaled(scale, 12, 7, 18)
        hero_width = max(1, width - (horizontal_margin * 2))
        self.hero.setFixedHeight(
            SquareHero.responsive_height(hero_width, height)
        )
        self.hero.set_responsive_scale(min(scale, 1.0))

        for card in (self.summary, self.activity, self.actions):
            card.apply_scale(scale)

        summary_size = scaled(scale, 16, 12, 21)
        for label in self.summary_labels:
            label.setFont(QFont("Segoe UI", summary_size))

        activity_size = scaled(scale, 14, 11, 18)
        for label in self.activity_labels:
            label.setFont(QFont("Segoe UI", activity_size))

        action_size = scaled(scale, 15, 11, 19)
        action_height = scaled(scale, 38, 29, 50)
        for button in self.action_buttons:
            button.setFont(
                QFont(
                    "Segoe UI",
                    action_size,
                    QFont.Weight.DemiBold,
                )
            )
            button.setMinimumHeight(action_height)

        search_size = scaled(scale, 15, 12, 19)
        search_height = scaled(scale, 38, 32, 50)
        self.search.setFont(QFont("Segoe UI", search_size))
        self.search.setMinimumHeight(search_height)
        self.search_button.setFont(
            QFont(
                "Segoe UI",
                action_size,
                QFont.Weight.Bold,
            )
        )
        self.search_button.setMinimumHeight(search_height)
        self.smart_insight.apply_scale(scale)

        self.layout_box.setContentsMargins(
            horizontal_margin,
            vertical_margin,
            horizontal_margin,
            vertical_margin,
        )
        self.layout_box.setSpacing(spacing)
        self.cards_layout.setSpacing(spacing)

    def refresh_dashboard(self) -> None:
        snapshot = self.service.get_dashboard_data()
        preferences = self.preferences.load_home_preferences()
        welcome = self.welcome_service.build(snapshot, preferences)
        banner = self.banner_service.resolve(preferences)
        self.hero.set_content(
            banner.name,
            welcome.greeting,
            welcome.summary,
            welcome.insight,
            banner.asset_path,
        )
        self._populate(snapshot)

    def activate(self) -> None:
        """Restore a clean default Home every time it is revisited."""
        self.reset_home()
        self.refresh_dashboard()

    def deactivate(self) -> None:
        """Close transient overlays before another page is shown."""
        self.close_suggestions()

    def reset_home(self) -> None:
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._results = ()
        self.close_suggestions()
        self.search.clearFocus()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _populate(self, snapshot: DashboardData) -> None:
        self.summary_labels[0].setText(
            f"📚  {snapshot.total_books:,} books"
        )
        self.summary_labels[1].setText(
            f"🗂  {snapshot.library_count:,} locations"
        )
        self.summary_labels[2].setText(
            f"💾  {format_file_size(snapshot.total_size)}"
        )
        self.summary_labels[3].setText(
            f"✓  {snapshot.metadata_health}% metadata health"
        )

        activities: list[str] = []
        if snapshot.last_scanned_at:
            try:
                scanned_at = datetime.fromisoformat(
                    snapshot.last_scanned_at
                ).astimezone()
                activities.append(
                    "✓ Scan completed · "
                    + scanned_at.strftime("%d %b, %I:%M %p")
                )
            except ValueError:
                activities.append("✓ Library scan completed")
        if snapshot.books_this_week:
            activities.append(
                f"✓ {snapshot.books_this_week:,} books added this week"
            )
        activities.extend(
            f"✓ Added {book.title}"
            for book in snapshot.recent_books[:3]
        )
        if not activities:
            activities = [
                "Your activity will appear here after the first scan."
            ]
        for index, label in enumerate(self.activity_labels):
            visible = index < len(activities)
            label.setText(activities[index] if visible else "")
            label.setVisible(visible)

        if snapshot.missing_books:
            self.smart_insight.set_content(
                f"{snapshot.missing_books:,} books could not be located. "
                "Review their locations before making changes.",
                action_id="library_health",
                action_text="Review Library Health",
            )
        elif snapshot.needs_metadata:
            noun = "book" if snapshot.needs_metadata == 1 else "books"
            self.smart_insight.set_content(
                f"{snapshot.needs_metadata:,} {noun} need metadata "
                "improvements.",
                action_id="review_queue",
                action_text="Review Now",
            )
        elif snapshot.total_books:
            self.smart_insight.set_content(
                "Your library is looking great. All files are accounted "
                f"for and metadata health is {snapshot.metadata_health}%.",
                action_id="library_health",
                action_text="Open Library Health",
            )
        else:
            self.smart_insight.set_content(
                "Welcome to Twano. Scan a library folder when you are "
                "ready to bring your collection to life.",
                action_id="scan",
                action_text="Scan Library",
            )

    def _live_search(self, text: str) -> None:
        query = text.strip()
        if len(query) >= 2:
            self._show_suggestions(query)
        else:
            self._results = ()
            self.close_suggestions()

    def _show_suggestions(self, query: str) -> None:
        result = self.library_service.get_library(search_text=query)
        self._results = result.records[:5]
        self.suggestion_popup.show_results(query, self._results)

    def _move_suggestion_selection(self, direction: int) -> None:
        if (
            not self.suggestion_popup.isVisible()
            and len(self.search.text().strip()) >= 2
        ):
            self._show_suggestions(self.search.text().strip())
        self.suggestion_popup.select_relative(direction)

    def _submit_search(self) -> None:
        if (
            self.suggestion_popup.isVisible()
            and self.suggestion_popup.activate_selected()
        ):
            return
        self._request_full_search()

    def _request_full_search(self) -> None:
        query = self.search.text().strip()
        self.close_suggestions()
        self.search_requested.emit(query)

    def _open_all_results(self, query: str) -> None:
        self.search_requested.emit(query)

    def _open_suggested_book(self, book: LibraryRecord) -> None:
        open_book(self, book, self.preferences)

    def close_suggestions(self) -> None:
        self.suggestion_popup.close_popup()

    def _route_insight_action(self, action_id: str) -> None:
        if action_id == "review_queue":
            self.review_queue_requested.emit()
        elif action_id == "library_health":
            self.health_requested.emit()
        elif action_id == "scan":
            self.scan_requested.emit()

    @staticmethod
    def _style() -> str:
        return """
        #heroGreeting { color: #f0f4f6; background: transparent; }
        #heroSummary { color: #c0cbd2; background: transparent; }
        #heroInsight { color: #7bc1ef; background: transparent; }
        #heroTheme { color: #8297a5; background: transparent; }
        #heroActions { background: transparent; }
        #heroPrimaryAction, #heroSecondaryAction {
            color: #ffffff;
            border-radius: 5px;
            padding: 6px 16px;
            font-weight: 600;
        }
        #heroPrimaryAction {
            background: #246fc1;
            border: 1px solid #4c94dc;
        }
        #heroPrimaryAction:hover { background: #2e80d2; }
        #heroPrimaryAction:pressed, #heroSecondaryAction:pressed {
            padding: 8px 14px 4px 18px;
            border-style: inset;
        }
        #heroPrimaryAction:pressed { background: #1f64a8; }
        #heroSecondaryAction:pressed { background: #101a22; }
        #heroSecondaryAction {
            background: #17232e;
            border: 1px solid #465b6c;
        }
        #heroSecondaryAction:hover {
            background: #21313e;
            border-color: #638096;
        }
        #homeCard {
            background: #0f1821;
            border: 1px solid #304354;
            border-radius: 8px;
        }
        #homeCardTitle {
            color: #f1f6fa;
            font-weight: 700;
            border-bottom: 1px solid #263641;
            padding-bottom: 8px;
        }
        #summaryMetric { color: #d7e1e8; padding: 4px 2px; }
        #activityItem {
            color: #c1ccd5;
            padding: 4px 2px;
            border-bottom: 1px solid #202e38;
        }
        #homeSearch {
            background: #0a131c;
            color: #edf2f5;
            border: 1px solid #355269;
            border-radius: 4px;
            padding: 8px 12px;
        }
        #homeSearch:focus { border-color: #58a9de; }
        #searchSuggestionPopup {
            background: #0c141a;
            border: 1px solid #426176;
            border-radius: 4px;
        }
        #suggestionList {
            background: #0c141a;
            border: none;
            outline: none;
        }
        #suggestionList::item {
            color: #dce9f0;
            border-bottom: 1px solid #263743;
        }
        #suggestionList::item:selected {
            background: #205eae;
            color: #ffffff;
        }
        #suggestionTitle { color: #edf3f7; background: transparent; }
        #suggestionDetails { color: #93a8b7; background: transparent; }
        #resultCover {
            background: #285d7c;
            color: white;
            border: 1px solid #4b7d99;
            border-radius: 2px;
            font-weight: 700;
        }
        #homeAction {
            background: #15283a;
            color: #d9e4ea;
            border: 1px solid #304654;
            border-radius: 4px;
            padding: 8px 13px;
            text-align: left;
            font-weight: 600;
        }
        #homeAction:hover {
            background: #213746;
            border-color: #4e7890;
        }
        #homeAction:pressed {
            background: #102334;
            padding: 10px 11px 6px 15px;
            border-style: inset;
        }
        #statusBanner {
            background: #142536;
            border: 1px solid #31536a;
            border-radius: 5px;
        }
        #statusText { color: #cbd9e3; font-weight: 600; }
        #statusIcon { color: #70bced; background: transparent; }
        #secondaryButton {
            background: #162630;
            color: #dce6ec;
            border: 1px solid #385464;
            border-radius: 4px;
            padding: 6px 11px;
        }
        #secondaryButton:pressed {
            background: #0f2029;
            padding: 8px 9px 4px 13px;
            border-style: inset;
        }
        #primaryButton {
            background: #237db4;
            color: white;
            border: 1px solid #4095c7;
            border-radius: 4px;
            padding: 8px 14px;
            font-weight: 700;
        }
        #primaryButton:pressed {
            background: #1b628f;
            padding: 10px 12px 6px 16px;
            border-style: inset;
        }
        """

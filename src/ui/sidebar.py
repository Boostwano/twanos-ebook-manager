"""Responsive Twano branding and calm page-ID based navigation."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from preferences import ProtectionMode
from ui.branding import branding_asset_path
from ui.responsive import clamp, responsive_scale, scaled


@dataclass(frozen=True)
class NavigationEntry:
    """One visible destination in the sidebar."""

    page_id: str
    label: str
    icon_kind: str
    colour: str


# The everyday navigation intentionally omits secondary workflow pages. Review
# Queue is reached from Metadata/Library, Protection from the safety card, and
# detailed analytics from Library Health.
PRIMARY_NAVIGATION = (
    NavigationEntry("home", "Home", "home", "#ffffff"),
    NavigationEntry("library", "Library", "book", "#b8c9e8"),
    NavigationEntry(
        "library_health",
        "Library Health",
        "health",
        "#8bd66f",
    ),
    NavigationEntry("scan", "Scan", "search", "#69b7ff"),
    NavigationEntry(
        "metadata",
        "Metadata & Covers",
        "metadata",
        "#78b7ff",
    ),
    NavigationEntry("plugins", "Plugins", "plugins", "#a993ff"),
    NavigationEntry("settings", "Settings", "settings", "#7fb4df"),
)

SUPPORT_NAVIGATION = (
    NavigationEntry("user_guide", "User Guide", "book", "#b8c9e8"),
    NavigationEntry("whats_new", "What's New", "spark", "#69b7ff"),
    NavigationEntry("about", "About", "about", "#b8c9e8"),
)

NAVIGATION_PAGE_IDS = tuple(
    entry.page_id for entry in PRIMARY_NAVIGATION + SUPPORT_NAVIGATION
)


class BrandLogo(QWidget):
    """Scalable approved open leather-book mark."""

    def __init__(self) -> None:
        super().__init__()
        self._pixmap = QPixmap(
            str(branding_asset_path("twano-book-logo.png"))
        )
        self.setToolTip("Twano — Your Library, Beautifully Organised")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._pixmap.isNull():
            painter.setPen(QColor("#d6ad69"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "TWANO",
            )
        else:
            scaled_pixmap = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled_pixmap.width()) // 2
            y = (self.height() - scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, scaled_pixmap)
        painter.end()


class BrandHeader(QWidget):
    """Responsive logo, product name, and subtitle."""

    def __init__(self) -> None:
        super().__init__()
        self.logo = BrandLogo()
        self.logo.setObjectName("brandIcon")
        self.app_name = QLabel("Twano's")
        self.app_name.setObjectName("appName")
        self.app_name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.app_subtitle = QLabel("eBook Manager")
        self.app_subtitle.setObjectName("appSubtitle")
        self.app_subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        text_layout.addWidget(self.app_name)
        text_layout.addWidget(self.app_subtitle)

        self.layout_box = QHBoxLayout(self)
        self.layout_box.setContentsMargins(0, 0, 0, 0)
        self.layout_box.addWidget(self.logo)
        self.layout_box.addLayout(text_layout, 1)

    @staticmethod
    def _fitted_font_size(
        text: str,
        family: str,
        weight: QFont.Weight,
        preferred_size: int,
        minimum_size: int,
        available_width: int,
    ) -> int:
        """Return the largest readable point size that fits the text column."""
        safe_width = max(1, available_width - 6)
        for point_size in range(preferred_size, minimum_size - 1, -1):
            font = QFont(family, point_size, weight)
            if QFontMetrics(font).horizontalAdvance(text) <= safe_width:
                return point_size
        return minimum_size

    def apply_scale(self, scale: float, available_width: int) -> int:
        """Match the generous proportions of the accepted reference design."""
        logo_size = scaled(scale, 72, 56, 88)
        self.logo.setFixedSize(logo_size, logo_size)
        spacing = scaled(scale, 12, 8, 16)
        text_width = max(92, available_width - logo_size - spacing)
        self.app_name.setFixedWidth(text_width)
        self.app_subtitle.setFixedWidth(text_width)

        name_size = self._fitted_font_size(
            self.app_name.text(),
            "Georgia",
            QFont.Weight.Bold,
            scaled(scale, 37, 28, 40),
            18,
            text_width,
        )
        self.app_name.setFont(
            QFont(
                "Georgia",
                name_size,
                QFont.Weight.Bold,
            )
        )
        # Qt's application stylesheet supplies a default pixel size to every
        # widget.  A widget font alone does not override that stylesheet, so
        # keep the responsive branding size explicit on these two labels.
        self.app_name.setStyleSheet(
            "background: transparent; color: #f5e5c5; "
            'font-family: "Georgia"; '
            f"font-size: {name_size}pt; font-weight: 700; "
            "letter-spacing: 0.4px;"
        )
        subtitle_size = self._fitted_font_size(
            self.app_subtitle.text(),
            "Segoe UI",
            QFont.Weight.Normal,
            scaled(scale, 15, 12, 18),
            10,
            text_width,
        )
        self.app_subtitle.setFont(
            QFont("Segoe UI", subtitle_size)
        )
        self.app_subtitle.setStyleSheet(
            "background: transparent; color: #d6c3a5; "
            'font-family: "Segoe UI"; '
            f"font-size: {subtitle_size}pt;"
        )
        self.layout_box.setSpacing(spacing)
        header_height = logo_size + scaled(scale, 4, 2, 8)
        self.setFixedHeight(header_height)
        return header_height


class ClickableFrame(QFrame):
    """Keyboard-neutral status card that opens its related page."""

    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ResponsiveSidebar(QFrame):
    """Navigation that fits normal desktop heights without scrolling."""

    page_requested = Signal(str)
    diagnostic_report_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setMinimumWidth(205)
        self.setMaximumWidth(325)

        self.brand_header = BrandHeader()

        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.navigation.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.navigation.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.navigation.setVerticalScrollMode(
            QListWidget.ScrollMode.ScrollPerPixel
        )
        self.navigation.setSpacing(0)

        for entry in PRIMARY_NAVIGATION:
            self._add_navigation_item(entry)
        self._add_navigation_separator()
        for entry in SUPPORT_NAVIGATION:
            self._add_navigation_item(entry)

        self.navigation.currentItemChanged.connect(
            self._navigation_changed
        )

        self.protection_panel = ClickableFrame()
        self.protection_panel.setObjectName("protectionPanel")
        self.protection_panel.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.protection_panel.clicked.connect(
            lambda: self.page_requested.emit("protection")
        )
        self.protection_layout = QHBoxLayout(self.protection_panel)
        self.protection_icon = QLabel()
        self.protection_icon.setObjectName("protectionIcon")
        self.protection_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        protection_text = QVBoxLayout()
        protection_text.setContentsMargins(0, 0, 0, 0)
        protection_text.setSpacing(1)
        self.protection_label = QLabel()
        self.protection_label.setObjectName("protectionLabel")
        self.protection_detail = QLabel()
        self.protection_detail.setObjectName("protectionDetail")
        self.protection_detail.setWordWrap(True)
        protection_text.addWidget(self.protection_label)
        protection_text.addWidget(self.protection_detail)
        self.protection_layout.addWidget(self.protection_icon)
        self.protection_layout.addLayout(protection_text, 1)

        self.diagnostic_report_button = QPushButton("Diagnostic Report")
        self.diagnostic_report_button.setObjectName(
            "diagnosticReportAction"
        )
        self.diagnostic_report_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.diagnostic_report_button.setToolTip(
            "Save a text file describing your setup and recent activity, "
            "to send along if you report a problem."
        )
        self.diagnostic_report_button.clicked.connect(
            self.diagnostic_report_requested.emit
        )

        self.layout_box = QVBoxLayout(self)
        self.layout_box.setSpacing(0)
        self.layout_box.addWidget(self.brand_header)
        self.brand_gap = QSpacerItem(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )
        self.layout_box.addItem(self.brand_gap)
        self.layout_box.addWidget(self.navigation, 1)
        self.lower_gap = QSpacerItem(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )
        self.layout_box.addItem(self.lower_gap)
        self.layout_box.addWidget(self.diagnostic_report_button)
        self.layout_box.addSpacing(6)
        self.layout_box.addWidget(self.protection_panel)

    @staticmethod
    def _navigation_icon(
        icon_kind: str,
        colour: str,
        size: int = 36,
    ) -> QIcon:
        icon = QIcon()
        for mode, icon_colour in (
            (QIcon.Mode.Normal, QColor(colour)),
            (QIcon.Mode.Active, QColor(colour).lighter(125)),
            (QIcon.Mode.Selected, QColor("#ffffff")),
        ):
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(icon_colour, max(1.7, size / 16.0))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            ResponsiveSidebar._draw_navigation_symbol(
                painter,
                icon_kind,
                float(size),
            )
            painter.end()
            icon.addPixmap(pixmap, mode, QIcon.State.Off)
        return icon

    @staticmethod
    def _draw_navigation_symbol(
        painter: QPainter,
        icon_kind: str,
        size: float,
    ) -> None:
        """Draw stable line icons matching the original Twano artwork."""
        factor = size / 36.0

        def point(x: float, y: float) -> QPointF:
            return QPointF(x * factor, y * factor)

        def rect(
            x: float,
            y: float,
            width: float,
            height: float,
        ) -> QRectF:
            return QRectF(
                x * factor,
                y * factor,
                width * factor,
                height * factor,
            )

        if icon_kind == "home":
            painter.drawPolyline(
                QPolygonF([point(6, 17), point(18, 7), point(30, 17)])
            )
            painter.drawRoundedRect(rect(9, 15, 18, 15), 1.5, 1.5)
            painter.drawRect(rect(16, 22, 5, 8))
        elif icon_kind == "book":
            left = QPainterPath(point(18, 11))
            left.cubicTo(point(14, 8), point(9, 8), point(6, 10))
            left.lineTo(point(6, 27))
            left.cubicTo(point(10, 25), point(14, 26), point(18, 29))
            right = QPainterPath(point(18, 11))
            right.cubicTo(point(22, 8), point(27, 8), point(30, 10))
            right.lineTo(point(30, 27))
            right.cubicTo(point(26, 25), point(22, 26), point(18, 29))
            painter.drawPath(left)
            painter.drawPath(right)
            painter.drawLine(point(18, 11), point(18, 29))
        elif icon_kind == "search":
            painter.drawEllipse(rect(6, 6, 18, 18))
            painter.drawLine(point(22, 22), point(31, 31))
        elif icon_kind == "metadata":
            painter.drawLine(point(8, 29), point(25, 12))
            painter.drawLine(point(12, 31), point(29, 14))
            painter.drawLine(point(8, 29), point(12, 31))
            painter.drawLine(point(25, 12), point(29, 14))
            for x, y in ((10, 10), (25, 7), (29, 25)):
                painter.drawLine(point(x - 2, y), point(x + 2, y))
                painter.drawLine(point(x, y - 2), point(x, y + 2))
        elif icon_kind == "health":
            heart = QPainterPath(point(18, 30))
            heart.cubicTo(point(14, 26), point(6, 21), point(6, 14))
            heart.cubicTo(point(6, 7), point(15, 6), point(18, 12))
            heart.cubicTo(point(21, 6), point(30, 7), point(30, 14))
            heart.cubicTo(point(30, 21), point(22, 26), point(18, 30))
            painter.drawPath(heart)
            painter.drawPolyline(
                QPolygonF(
                    [
                        point(7, 18),
                        point(12, 18),
                        point(15, 13),
                        point(19, 23),
                        point(22, 18),
                        point(29, 18),
                    ]
                )
            )
        elif icon_kind == "plugins":
            painter.drawRoundedRect(rect(8, 8, 20, 20), 3, 3)
            painter.drawLine(point(18, 8), point(18, 13))
            painter.drawEllipse(rect(15, 3, 6, 6))
            painter.drawLine(point(28, 18), point(23, 18))
            painter.drawEllipse(rect(27, 15, 6, 6))
            painter.drawLine(point(18, 28), point(18, 23))
            painter.drawLine(point(8, 18), point(13, 18))
        elif icon_kind == "settings":
            painter.drawEllipse(rect(11, 11, 14, 14))
            painter.drawEllipse(rect(16, 16, 4, 4))
            for x1, y1, x2, y2 in (
                (18, 5, 18, 10),
                (18, 26, 18, 31),
                (5, 18, 10, 18),
                (26, 18, 31, 18),
                (9, 9, 12.5, 12.5),
                (23.5, 23.5, 27, 27),
                (27, 9, 23.5, 12.5),
                (12.5, 23.5, 9, 27),
            ):
                painter.drawLine(point(x1, y1), point(x2, y2))
        elif icon_kind == "spark":
            painter.drawLine(point(9, 27), point(27, 9))
            painter.drawEllipse(rect(6, 24, 6, 6))
            painter.drawLine(point(20, 7), point(20, 13))
            painter.drawLine(point(17, 10), point(23, 10))
            painter.drawLine(point(27, 21), point(27, 29))
            painter.drawLine(point(23, 25), point(31, 25))
        else:
            painter.drawEllipse(rect(7, 7, 22, 22))
            painter.drawEllipse(rect(16.5, 11, 3, 3))
            painter.drawLine(point(18, 17), point(18, 25))

    def _add_navigation_item(self, entry: NavigationEntry) -> None:
        item = QListWidgetItem(
            self._navigation_icon(entry.icon_kind, entry.colour),
            entry.label,
            self.navigation,
        )
        item.setData(Qt.ItemDataRole.UserRole, entry.page_id)
        item.setToolTip(entry.label)

    def _add_navigation_separator(self) -> None:
        item = QListWidgetItem(self.navigation)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setData(Qt.ItemDataRole.UserRole, "")
        divider = QFrame()
        divider.setObjectName("navigationDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        self.navigation.setItemWidget(item, divider)
        item.setSizeHint(QSize(0, 10))

    def _navigation_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        page_id = current.data(Qt.ItemDataRole.UserRole)
        if isinstance(page_id, str) and page_id:
            self.page_requested.emit(page_id)

    @property
    def page_ids(self) -> tuple[str, ...]:
        """Return visible destinations in display order."""
        return NAVIGATION_PAGE_IDS

    def select_page(self, page_id: str) -> bool:
        """Select a visible page ID, returning false for hidden pages."""
        for row in range(self.navigation.count()):
            item = self.navigation.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == page_id:
                self.navigation.setCurrentItem(item)
                return True
        return False

    def clear_selection(self) -> None:
        self.navigation.clearSelection()
        self.navigation.setCurrentItem(None)

    def set_protection_mode(self, mode: ProtectionMode) -> None:
        """Update the protection indicator without restarting."""
        if ProtectionMode(mode) == ProtectionMode.READ_ONLY:
            self.protection_icon.setText("🔒")
            self.protection_label.setText("Read-Only")
            self.protection_detail.setText(
                "Browsing only. No files will be changed."
            )
            tooltip = (
                "Browsing, scanning, search and reports only. Select to "
                "open Protection & Undo."
            )
        else:
            self.protection_icon.setText("🛡")
            self.protection_label.setText("Standard")
            self.protection_detail.setText(
                "Backups and Undo are available."
            )
            tooltip = (
                "Verified backups, Restore and protected Undo are ready. "
                "Select to open Protection & Undo."
            )
        self.protection_panel.setToolTip(tooltip)

    def apply_responsive_size(
        self,
        window_width: int,
        window_height: int,
    ) -> None:
        """Resize every sidebar element from the real window dimensions."""
        scale = responsive_scale(
            window_width,
            window_height,
            reference_width=1920,
            reference_height=1080,
            minimum=0.72,
            maximum=1.34,
        )
        sidebar_width = scaled(scale, 274, 210, 320)
        self.setFixedWidth(sidebar_width)

        horizontal_margin = scaled(scale, 16, 9, 22)
        vertical_margin = scaled(scale, 16, 8, 22)
        self.layout_box.setContentsMargins(
            horizontal_margin,
            vertical_margin,
            horizontal_margin,
            vertical_margin,
        )

        brand_available_width = sidebar_width - horizontal_margin * 2
        brand_height = self.brand_header.apply_scale(
            scale,
            brand_available_width,
        )
        brand_gap = scaled(scale, 14, 5, 22)
        lower_gap = scaled(scale, 9, 4, 14)
        self.brand_gap.changeSize(0, brand_gap)
        self.lower_gap.changeSize(0, lower_gap)

        nav_font_size = scaled(scale, 16, 12, 20)
        icon_size = scaled(scale, 31, 23, 40)
        self.navigation.setFont(
            QFont("Segoe UI", nav_font_size, QFont.Weight.DemiBold)
        )
        self.navigation.setIconSize(QSize(icon_size, icon_size))

        diagnostic_button_height = scaled(scale, 34, 26, 42)
        diagnostic_button_gap = 6
        self.diagnostic_report_button.setFixedHeight(
            diagnostic_button_height
        )

        protection_height = scaled(scale, 68, 51, 88)
        self.protection_panel.setFixedHeight(protection_height)
        protection_margin_x = scaled(scale, 12, 7, 16)
        protection_margin_y = scaled(scale, 9, 4, 12)
        self.protection_layout.setContentsMargins(
            protection_margin_x,
            protection_margin_y,
            protection_margin_x,
            protection_margin_y,
        )
        self.protection_layout.setSpacing(scaled(scale, 9, 5, 12))
        self.protection_icon.setFont(
            QFont("Segoe UI Emoji", scaled(scale, 19, 14, 25))
        )
        self.protection_label.setFont(
            QFont(
                "Segoe UI",
                scaled(scale, 11, 9, 14),
                QFont.Weight.DemiBold,
            )
        )
        self.protection_detail.setFont(
            QFont("Segoe UI", scaled(scale, 9, 7, 11))
        )

        fixed_height = (
            vertical_margin * 2
            + brand_height
            + brand_gap
            + lower_gap
            + diagnostic_button_height
            + diagnostic_button_gap
            + protection_height
        )
        available_navigation = max(0, window_height - fixed_height)
        divider_height = scaled(scale, 13, 8, 19)
        page_count = len(NAVIGATION_PAGE_IDS)
        viewport_safety_margin = 4
        calculated_row_height = (
            (
                available_navigation
                - divider_height
                - viewport_safety_margin
            )
            / page_count
            if page_count
            else 0
        )
        item_height = int(clamp(30, calculated_row_height, 62))

        for index in range(self.navigation.count()):
            item = self.navigation.item(index)
            if item.data(Qt.ItemDataRole.UserRole):
                item.setSizeHint(QSize(0, item_height))
            else:
                item.setSizeHint(QSize(0, divider_height))

        self.layout_box.invalidate()

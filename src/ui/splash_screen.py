"""Approved branded splash screen shown while Twano starts."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from ui.branding import branding_asset_path

SPLASH_DISPLAY_MS = 5_000


class TwanoSplashScreen(QSplashScreen):
    """Display the approved RC1 artwork before the main window is ready."""

    FADE_DURATION_MS = 650
    SOURCE_CORNER_RADIUS = 22
    SOURCE_FRAME_WIDTH = 4
    FRAME_COLOR = QColor("#39ace7")
    SOURCE_FRAME_CROP = (0, 0, 0, 0)

    def __init__(self) -> None:
        source = QPixmap(
            str(branding_asset_path("twano-splash-panel-rc1.png"))
        )
        if source.isNull():
            source = self._fallback_pixmap()
        else:
            source = self._crop_to_blue_frame(source)
        source = self._square_pixmap(source)

        screen = QApplication.primaryScreen()
        available_width = (
            screen.availableGeometry().width() if screen else source.width()
        )
        target_width = min(
            source.width(),
            max(320, int(available_width * 0.80)),
        )
        scaled_pixmap = source.scaledToWidth(
            target_width,
            Qt.TransformationMode.SmoothTransformation,
        )
        pixmap = scaled_pixmap
        super().__init__(
            pixmap,
            (
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            ),
        )
        self.setObjectName("twanoSplashScreen")
        self._fade_animation: QPropertyAnimation | None = None

    def fade_out(self, finished_callback: Callable[[], None]) -> None:
        """Fade away smoothly, then invoke the startup completion callback."""
        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(self.FADE_DURATION_MS)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(finished_callback)
        self._fade_animation = animation
        animation.start()

    @staticmethod
    def _fallback_pixmap() -> QPixmap:
        pixmap = QPixmap(840, 472)
        pixmap.fill(QColor("#08131f"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#f5e5c5"))
        painter.drawText(
            pixmap.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "Twano's\n\neBook Manager",
        )
        painter.end()
        return pixmap

    @classmethod
    def _square_pixmap(cls, source: QPixmap) -> QPixmap:
        """Replace authored rounded corners with one crisp square frame."""
        image = source.toImage()
        corner = min(
            cls.SOURCE_CORNER_RADIUS + cls.SOURCE_FRAME_WIDTH,
            source.width() // 2,
            source.height() // 2,
        )
        corner_rectangles = (
            (
                0,
                0,
                corner,
                corner,
                corner,
                corner,
                cls.SOURCE_CORNER_RADIUS,
                cls.SOURCE_CORNER_RADIUS,
            ),
            (
                source.width() - corner,
                0,
                corner,
                corner,
                source.width() - corner - 1,
                corner,
                source.width() - 1 - cls.SOURCE_CORNER_RADIUS,
                cls.SOURCE_CORNER_RADIUS,
            ),
            (
                0,
                source.height() - corner,
                corner,
                corner,
                corner,
                source.height() - corner - 1,
                cls.SOURCE_CORNER_RADIUS,
                source.height() - 1 - cls.SOURCE_CORNER_RADIUS,
            ),
            (
                source.width() - corner,
                source.height() - corner,
                corner,
                corner,
                source.width() - corner - 1,
                source.height() - corner - 1,
                source.width() - 1 - cls.SOURCE_CORNER_RADIUS,
                source.height() - 1 - cls.SOURCE_CORNER_RADIUS,
            ),
        )
        ring_radius = max(1, cls.SOURCE_CORNER_RADIUS - 5)
        for (
            x,
            y,
            width,
            height,
            sample_x,
            sample_y,
            centre_x,
            centre_y,
        ) in corner_rectangles:
            fill = image.pixelColor(sample_x, sample_y)
            fill.setAlpha(255)
            for pixel_y in range(y, y + height):
                for pixel_x in range(x, x + width):
                    colour = image.pixelColor(pixel_x, pixel_y)
                    outside_old_curve = (
                        (pixel_x - centre_x) ** 2
                        + (pixel_y - centre_y) ** 2
                        >= ring_radius**2
                    )
                    if colour.alpha() < 250 or outside_old_curve:
                        image.setPixelColor(pixel_x, pixel_y, fill)
        squared = QPixmap.fromImage(image)
        painter = QPainter(squared)
        frame = cls.SOURCE_FRAME_WIDTH
        painter.fillRect(0, 0, source.width(), frame, cls.FRAME_COLOR)
        painter.fillRect(
            0,
            source.height() - frame,
            source.width(),
            frame,
            cls.FRAME_COLOR,
        )
        painter.fillRect(0, 0, frame, source.height(), cls.FRAME_COLOR)
        painter.fillRect(
            source.width() - frame,
            0,
            frame,
            source.height(),
            cls.FRAME_COLOR,
        )
        painter.end()
        return squared

    @classmethod
    def _crop_to_blue_frame(cls, source: QPixmap) -> QPixmap:
        """Remove pixels outside the authored light-blue panel outline."""
        left, top, right, bottom = cls.SOURCE_FRAME_CROP
        width = source.width() - left - right
        height = source.height() - top - bottom
        if width <= 0 or height <= 0:
            return source
        return source.copy(left, top, width, height)

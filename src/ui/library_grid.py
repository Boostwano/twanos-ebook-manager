"""Painted Library cover cards for the shared paged model."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from preferences import LibraryDensity
from services.library_service import LibraryRecord
from ui.library_format import display_series
from ui.library_model import LIBRARY_RECORD_ROLE
from ui.thumbnail_cache import ThumbnailCache


_CARD_SIZES = {
    LibraryDensity.COMPACT: QSize(148, 246),
    LibraryDensity.COMFORTABLE: QSize(182, 294),
    LibraryDensity.SPACIOUS: QSize(220, 350),
}


class LibraryGridDelegate(QStyledItemDelegate):
    """Draw responsive cards and request only visible cover thumbnails."""

    def __init__(
        self,
        cache: ThumbnailCache,
        density: LibraryDensity = LibraryDensity.COMFORTABLE,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cache = cache
        self._density = LibraryDensity(density)

    @property
    def density(self) -> LibraryDensity:
        return self._density

    @property
    def item_size(self) -> QSize:
        return _CARD_SIZES[self._density]

    def set_density(self, density: LibraryDensity) -> None:
        self._density = LibraryDensity(density)

    def sizeHint(self, option, index) -> QSize:
        return self.item_size

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        book = index.data(LIBRARY_RECORD_ROLE)
        if not isinstance(book, LibraryRecord):
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(
            option.state & QStyle.StateFlag.State_Selected
        )
        hovered = bool(
            option.state & QStyle.StateFlag.State_MouseOver
        )
        card = option.rect.adjusted(5, 5, -5, -5)
        painter.setPen(
            QPen(
                QColor("#4ca3e6" if selected else "#355066"),
                2 if selected else 1,
            )
        )
        painter.setBrush(
            QColor(
                "#17324a"
                if selected
                else "#152431"
                if hovered
                else "#101a24"
            )
        )
        painter.drawRoundedRect(card, 8, 8)

        inner = card.adjusted(10, 10, -10, -10)
        text_height = 76 if self._density == LibraryDensity.COMPACT else 88
        cover_area = QRect(
            inner.left(),
            inner.top(),
            inner.width(),
            max(60, inner.height() - text_height),
        )
        cover_size = QSize(
            max(1, cover_area.width()),
            max(1, cover_area.height()),
        )
        pixmap = self._cache.get_thumbnail(book, cover_size)
        if pixmap is not None:
            target = self._centred_rect(pixmap.size(), cover_area)
            painter.drawPixmap(target, pixmap)
        else:
            self._paint_cover_state(
                painter,
                cover_area,
                self._cache.state(book, cover_size),
                book.file_format,
            )

        text_top = cover_area.bottom() + 7
        text_rect = QRect(
            inner.left(),
            text_top,
            inner.width(),
            inner.bottom() - text_top + 1,
        )
        self._paint_text(painter, text_rect, book)
        painter.restore()

    @staticmethod
    def _centred_rect(source: QSize, target: QRect) -> QRect:
        left = target.left() + (target.width() - source.width()) // 2
        top = target.top() + (target.height() - source.height()) // 2
        return QRect(left, top, source.width(), source.height())

    @staticmethod
    def _paint_cover_state(
        painter: QPainter,
        rect: QRect,
        state: str,
        file_format: str,
    ) -> None:
        painter.setPen(QPen(QColor("#41647c"), 1))
        painter.setBrush(QColor("#1c3d52"))
        painter.drawRoundedRect(rect, 4, 4)
        labels = {
            "missing": "NO COVER",
            "failed": "COVER ERROR",
            "loading": "LOADING",
        }
        painter.setPen(QColor("#a9c8da"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(
            rect.adjusted(4, 4, -4, -4),
            int(Qt.AlignmentFlag.AlignCenter),
            f"{file_format or 'BOOK'}\n{labels.get(state, 'NO COVER')}",
        )

    @staticmethod
    def _paint_text(
        painter: QPainter,
        rect: QRect,
        book: LibraryRecord,
    ) -> None:
        metrics = painter.fontMetrics()
        title_font = QFont(painter.font())
        title_font.setBold(True)
        title_font.setPointSize(10)
        painter.setFont(title_font)
        painter.setPen(QColor("#f0f5f8"))
        title = painter.fontMetrics().elidedText(
            book.title,
            Qt.TextElideMode.ElideRight,
            rect.width(),
        )
        painter.drawText(
            QRect(rect.left(), rect.top(), rect.width(), 20),
            int(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter
            ),
            title,
        )

        painter.setFont(QFont(painter.font().family(), 9))
        painter.setPen(QColor("#bdcbd5"))
        author = painter.fontMetrics().elidedText(
            book.author,
            Qt.TextElideMode.ElideRight,
            rect.width(),
        )
        painter.drawText(
            QRect(rect.left(), rect.top() + 21, rect.width(), 18),
            int(Qt.AlignmentFlag.AlignLeft),
            author,
        )

        series = display_series(book)
        facts = " • ".join(
            value
            for value in (series, book.file_format)
            if value
        )
        painter.setPen(QColor("#8fb7d1"))
        facts = painter.fontMetrics().elidedText(
            facts,
            Qt.TextElideMode.ElideRight,
            rect.width(),
        )
        painter.drawText(
            QRect(rect.left(), rect.top() + 42, rect.width(), 18),
            int(Qt.AlignmentFlag.AlignLeft),
            facts,
        )

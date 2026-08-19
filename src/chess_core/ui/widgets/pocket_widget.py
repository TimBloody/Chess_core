"""Crazyhouse strip pocket and shogi komadai: miniature pieces, no type labels."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QSizePolicy, QWidget

from chess_core.core.piece import PieceSide
from chess_core.ui.assets_loader import AssetsLoader, shogi_piece_set

_STRIP_TOKEN = 36
_GRID_TOKEN = 40
_PAD = 8
_GAP = 4

_WHITE_FILL = QColor(209, 227, 198)
_WHITE_BORDER = QColor(122, 148, 110)
_BLACK_FILL = QColor(47, 58, 74)
_BLACK_BORDER = QColor(122, 138, 158)
_SELECT = QColor(246, 220, 90, 210)
_COUNT_FILL = QColor(30, 30, 30, 200)


@dataclass(frozen=True)
class PocketStack:
    piece_key: str
    piece_type: str
    count: int


class PocketWidget(QWidget):
    """Presentation-only hand tray. Emits ``piece_type`` name on click.

    Strip mode is a single row sized for every droppable type (crazyhouse).
    Grid mode is a square komadai that wraps tokens in columns (shogi).
    """

    piece_clicked = pyqtSignal(str)

    def __init__(
        self,
        side: PieceSide,
        parent: QWidget | None = None,
        assets_loader: AssetsLoader | None = None,
    ) -> None:
        super().__init__(parent)
        self._side = side
        self._stacks: tuple[PocketStack, ...] = ()
        self._selected: str | None = None
        self._interactive = False
        self._rotate_pieces = False
        self._grid = False
        self._columns = 3
        self._capacity = 1
        self._assets = assets_loader or AssetsLoader()
        self._renderers: dict[str, QSvgRenderer] = {}
        self._apply_size_policy()
        self.setCursor(Qt.CursorShape.ArrowCursor)

    @property
    def side(self) -> PieceSide:
        return self._side

    @property
    def is_grid(self) -> bool:
        return self._grid

    def set_stacks(self, stacks: tuple[PocketStack, ...]) -> None:
        cleaned = tuple(stack for stack in stacks if stack.count > 0)
        if cleaned != self._stacks:
            self._stacks = cleaned
            self.update()
        self._refresh_cursor()

    def set_selected(self, piece_type: str | None) -> None:
        if piece_type != self._selected:
            self._selected = piece_type
            self.update()

    def set_interactive(self, enabled: bool) -> None:
        if enabled != self._interactive:
            self._interactive = enabled
            self._refresh_cursor()
            self.update()

    def set_rotate_pieces(self, enabled: bool) -> None:
        if enabled != self._rotate_pieces:
            self._rotate_pieces = enabled
            self.update()

    def set_capacity(self, capacity: int) -> None:
        slots = max(1, capacity)
        if slots != self._capacity:
            self._capacity = slots
            self._apply_size_policy()

    def set_grid(self, enabled: bool, *, columns: int = 3) -> None:
        cols = max(1, columns)
        if enabled != self._grid or cols != self._columns:
            self._grid = enabled
            self._columns = cols
            self._apply_size_policy()
            self.update()

    def invalidate_renderers(self) -> None:
        self._renderers.clear()
        self.update()

    def sizeHint(self) -> QSize:
        return self._desired_size()

    def minimumSizeHint(self) -> QSize:
        return self._desired_size()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._interactive:
            return
        index = self._token_at(event.position())
        if index is None:
            return
        self.piece_clicked.emit(self._stacks[index].piece_type)

    def paintEvent(self, event) -> None:  # noqa: ANN001
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = _WHITE_FILL if self._side is PieceSide.WHITE else _BLACK_FILL
        border = _WHITE_BORDER if self._side is PieceSide.WHITE else _BLACK_BORDER
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(fill)
        painter.setPen(border)
        painter.drawRoundedRect(rect, 8, 8)

        for index, stack in enumerate(self._stacks):
            token = self._token_rect(index)
            if stack.piece_type == self._selected and self._interactive:
                painter.setBrush(QColor(0, 0, 0, 0))
                painter.setPen(_SELECT)
                painter.drawRoundedRect(token.adjusted(-3, -3, 3, 3), 6, 6)
            renderer = self._renderer(stack.piece_key)
            token_inner = token.adjusted(2, 2, -2, -2)
            if self._rotate_pieces:
                painter.save()
                painter.translate(token_inner.center())
                painter.rotate(180)
                painter.translate(-token_inner.center())
                renderer.render(painter, token_inner)
                painter.restore()
            else:
                renderer.render(painter, token_inner)
            if stack.count > 1:
                self._draw_count(painter, token, stack.count)

    def _draw_count(self, painter: QPainter, token: QRectF, count: int) -> None:
        badge = QRectF(token.right() - 16, token.bottom() - 16, 16, 16)
        painter.setBrush(_COUNT_FILL)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(badge)
        font = QFont(painter.font())
        font.setBold(True)
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(count))

    def _token_rect(self, index: int) -> QRectF:
        token, pad, gap = self._metrics()
        if self._grid:
            col = index % self._columns
            row = index // self._columns
            return QRectF(pad + col * (token + gap), pad + row * (token + gap), token, token)
        return QRectF(pad + index * (token + gap), pad, token, token)

    def _token_at(self, point: QPointF) -> int | None:
        for index in range(len(self._stacks)):
            if self._token_rect(index).contains(point):
                return index
        return None

    def _metrics(self) -> tuple[int, int, int]:
        token = _GRID_TOKEN if self._grid else _STRIP_TOKEN
        return token, _PAD, _GAP

    def _slot_count(self) -> int:
        return max(self._capacity, len(self._stacks), 1)

    def _desired_size(self) -> QSize:
        token, pad, gap = self._metrics()
        slots = self._slot_count()
        if self._grid:
            cols = min(self._columns, slots)
            rows = max(1, ceil(slots / self._columns))
            width = pad * 2 + cols * (token + gap) - gap
            height = pad * 2 + rows * (token + gap) - gap
            side = max(width, height)
            return QSize(side, side)
        width = pad * 2 + slots * (token + gap) - gap
        return QSize(width, token + pad * 2)

    def _apply_size_policy(self) -> None:
        size = self._desired_size()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        if self._grid:
            self.setFixedSize(size)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        else:
            self.setFixedHeight(size.height())
            self.setFixedWidth(size.width())
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.updateGeometry()

    def _refresh_cursor(self) -> None:
        if self._interactive and self._stacks:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _renderer(self, piece_key: str) -> QSvgRenderer:
        cache_key = f"{shogi_piece_set()}:{piece_key}"
        renderer = self._renderers.get(cache_key)
        if renderer is None:
            renderer = QSvgRenderer(str(self._assets.piece_path(piece_key)))
            if not renderer.isValid():
                raise ValueError(f"Invalid SVG asset: {piece_key}")
            self._renderers[cache_key] = renderer
        return renderer

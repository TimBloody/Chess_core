"""Visual piece palette for the board editor (SVG tokens, not text)."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QSizePolicy, QWidget

from chess_core.core.piece import PieceSide
from chess_core.ui.assets_loader import AssetsLoader, shogi_piece_set

_TOKEN = 48
_PAD = 6
_GAP = 4
_FILL = QColor(236, 232, 220)
_BORDER = QColor(170, 162, 140)
_SELECT = QColor(232, 176, 64)


@dataclass(frozen=True)
class PaletteToken:
    piece_id: str
    side: PieceSide
    piece_key: str


class EditorPaletteStrip(QWidget):
    """One row/wrap of piece SVGs for a single side."""

    token_clicked = pyqtSignal(str, object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        assets_loader: AssetsLoader | None = None,
    ) -> None:
        super().__init__(parent)
        self._tokens: tuple[PaletteToken, ...] = ()
        self._selected: tuple[str, PieceSide] | None = None
        self._rotate = False
        self._columns = 6
        self._assets = assets_loader or AssetsLoader()
        self._renderers: dict[str, QSvgRenderer] = {}
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    @property
    def tokens(self) -> tuple[PaletteToken, ...]:
        return self._tokens

    def set_tokens(self, tokens: tuple[PaletteToken, ...]) -> None:
        if tokens != self._tokens:
            self._tokens = tokens
            self._columns = max(4, min(6, len(tokens) or 1))
            self._apply_size()
            self.update()

    def set_selected(self, piece_id: str | None, side: PieceSide | None) -> None:
        selected = None if piece_id is None or side is None else (piece_id, side)
        if selected != self._selected:
            self._selected = selected
            self.update()

    def set_rotate_pieces(self, enabled: bool) -> None:
        if enabled != self._rotate:
            self._rotate = enabled
            self.update()

    def invalidate_renderers(self) -> None:
        self._renderers.clear()
        self.update()

    def sizeHint(self) -> QSize:
        return self._desired_size()

    def minimumSizeHint(self) -> QSize:
        return self._desired_size()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        token = self._token_at(event.position())
        if token is None:
            return
        self.token_clicked.emit(token.piece_id, token.side)

    def paintEvent(self, event) -> None:  # noqa: ANN001
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(_FILL)
        painter.setPen(_BORDER)
        painter.drawRoundedRect(outer, 8, 8)
        for index, token in enumerate(self._tokens):
            rect = self._token_rect(index)
            if self._selected == (token.piece_id, token.side):
                painter.setBrush(QColor(0, 0, 0, 0))
                painter.setPen(_SELECT)
                painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 6, 6)
            inner = rect.adjusted(3, 3, -3, -3)
            renderer = self._renderer(token.piece_key)
            if renderer is None:
                painter.setPen(QColor(80, 80, 80))
                painter.drawText(inner, Qt.AlignmentFlag.AlignCenter, "?")
                continue
            if self._rotate:
                painter.save()
                painter.translate(inner.center())
                painter.rotate(180)
                painter.translate(-inner.center())
                renderer.render(painter, inner)
                painter.restore()
            else:
                renderer.render(painter, inner)

    def _token_at(self, point: QPointF) -> PaletteToken | None:
        for index, token in enumerate(self._tokens):
            if self._token_rect(index).contains(point):
                return token
        return None

    def _token_rect(self, index: int) -> QRectF:
        cols = max(1, self._columns)
        col = index % cols
        row = index // cols
        return QRectF(
            _PAD + col * (_TOKEN + _GAP),
            _PAD + row * (_TOKEN + _GAP),
            _TOKEN,
            _TOKEN,
        )

    def _desired_size(self) -> QSize:
        count = max(1, len(self._tokens))
        cols = min(self._columns, count)
        rows = (count + cols - 1) // cols
        width = _PAD * 2 + cols * (_TOKEN + _GAP) - _GAP
        height = _PAD * 2 + rows * (_TOKEN + _GAP) - _GAP
        return QSize(width, height)

    def _apply_size(self) -> None:
        size = self._desired_size()
        self.setFixedHeight(size.height())
        self.setMinimumWidth(size.width())
        self.updateGeometry()

    def _renderer(self, piece_key: str) -> QSvgRenderer | None:
        cache_key = f"{shogi_piece_set()}:{piece_key}"
        renderer = self._renderers.get(cache_key)
        if renderer is not None:
            return renderer
        try:
            path = str(self._assets.piece_path(piece_key))
        except FileNotFoundError:
            return None
        renderer = QSvgRenderer(path)
        if not renderer.isValid():
            return None
        self._renderers[cache_key] = renderer
        return renderer

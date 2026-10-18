"""Komadai / pocket tray: only pieces in hand, drawn as miniature SVGs."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QSizePolicy, QWidget

from chess_core.core.piece import PieceSide
from chess_core.core.state import HandsState
from chess_core.ui.assets_loader import AssetsLoader
from chess_core.ui.piece_keys import (
    FACING_ASSET_FAMILIES,
    hand_piece_key,
    should_rotate_facing_art,
)

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
    """Presentation-only hand tray. Emits the piece-type name on click.

    Empty types are omitted. Grid mode is a compact rectangular komadai;
    strip mode is a single row of owned pieces.
    """

    piece_chosen = pyqtSignal(str)

    def __init__(
        self,
        side: PieceSide = PieceSide.WHITE,
        parent: QWidget | None = None,
        assets_loader: AssetsLoader | None = None,
    ) -> None:
        super().__init__(parent)
        self._side = side
        self._stacks: tuple[PocketStack, ...] = ()
        self._selected: str | None = None
        self._interactive = False
        self._grid = False
        self._columns = 3
        self._asset_family = "chess"
        self._facing_black = False
        self._flip_map: dict[str, str] = {}
        self._shown_face: dict[str, str] = {}
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

    @property
    def visible_types(self) -> tuple[str, ...]:
        return tuple(stack.piece_type for stack in self._stacks)

    def set_hands(
        self,
        hands: HandsState | None,
        side: PieceSide,
        *,
        enabled: bool = True,
        types: tuple[str, ...] = ("pawn", "knight", "bishop", "rook", "queen"),
        asset_family: str = "chess",
        grid: bool | None = None,
        labels: dict[str, str] | None = None,
        flip_map: dict[str, str] | None = None,
        facing_black: bool = False,
    ) -> None:
        del labels
        self._side = side
        self._asset_family = asset_family
        self._facing_black = facing_black
        self._flip_map = dict(flip_map or {})
        counts: dict[str, int] = {}
        if hands is not None:
            for piece in hands.by_side.get(side, ()):
                name = piece.piece_type.name
                if name in types:
                    counts[name] = counts.get(name, 0) + 1
        stacks: list[PocketStack] = []
        for name in types:
            count = counts.get(name, 0)
            if count <= 0:
                continue
            key = hand_piece_key(name, side, asset_family)
            if key is None:
                continue
            stacks.append(PocketStack(piece_key=key, piece_type=name, count=count))
        self._shown_face = {
            name: face
            for name, face in self._shown_face.items()
            if name in {stack.piece_type for stack in stacks}
        }
        use_grid = asset_family in FACING_ASSET_FAMILIES if grid is None else grid
        columns = 2 if asset_family == "dobutsu" else 3
        self.set_grid(use_grid, columns=columns)
        self.set_stacks(tuple(stacks))
        self.set_interactive(enabled)
        if self._selected is not None and self._selected not in self.visible_types:
            self.clear_selection()
        else:
            self.update()

    def set_stacks(self, stacks: tuple[PocketStack, ...]) -> None:
        cleaned = tuple(stack for stack in stacks if stack.count > 0)
        if cleaned != self._stacks:
            self._stacks = cleaned
            self._apply_size_policy()
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

    def set_grid(self, enabled: bool, *, columns: int = 3) -> None:
        cols = max(1, columns)
        if enabled != self._grid or cols != self._columns:
            self._grid = enabled
            self._columns = cols
            self._apply_size_policy()
            self.update()

    def selected_type(self) -> str | None:
        return self._selected

    def selected_face(self) -> str | None:
        if self._selected is None:
            return None
        return self._shown_face.get(self._selected, self._selected)

    def shown_face(self, piece_type: str) -> str:
        return self._shown_face.get(piece_type, piece_type)

    @property
    def facing_black(self) -> bool:
        return self._facing_black

    def should_rotate_key(self, piece_key: str) -> bool:
        return should_rotate_facing_art(piece_key, facing_black=self._facing_black)

    def clear_selection(self) -> None:
        self.set_selected(None)

    def sizeHint(self) -> QSize:
        return self._desired_size()

    def minimumSizeHint(self) -> QSize:
        return self._desired_size()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._interactive:
            return
        index = self._token_at(event.position())
        if index is None:
            return
        name = self._stacks[index].piece_type
        if event.button() == Qt.MouseButton.RightButton:
            self._flip_stack(name)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._selected == name:
            self.clear_selection()
            return
        self._selected = name
        self.update()
        self.piece_chosen.emit(name)

    def _flip_stack(self, piece_type: str) -> None:
        pair = self._flip_map.get(piece_type)
        if pair is None:
            return
        current = self.shown_face(piece_type)
        self._shown_face[piece_type] = pair if current == piece_type else piece_type
        self.update()
        if self._selected == piece_type:
            self.piece_chosen.emit(piece_type)

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
            display_key = self._display_key(stack)
            renderer = self._renderer(display_key)
            token_inner = token.adjusted(2, 2, -2, -2)
            if self.should_rotate_key(display_key):
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

    def _display_key(self, stack: PocketStack) -> str:
        face = self.shown_face(stack.piece_type)
        return hand_piece_key(face, self._side, self._asset_family) or stack.piece_key

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
        return max(len(self._stacks), 1)

    def _desired_size(self) -> QSize:
        token, pad, gap = self._metrics()
        slots = self._slot_count()
        if self._grid:
            cols = min(self._columns, slots)
            rows = max(1, ceil(slots / self._columns))
            width = pad * 2 + cols * (token + gap) - gap
            height = pad * 2 + rows * (token + gap) - gap
            return QSize(width, height)
        width = pad * 2 + slots * (token + gap) - gap
        return QSize(width, token + pad * 2)

    def _apply_size_policy(self) -> None:
        size = self._desired_size()
        self.setFixedSize(size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.updateGeometry()

    def _refresh_cursor(self) -> None:
        if self._interactive and self._stacks:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _renderer(self, piece_key: str) -> QSvgRenderer:
        renderer = self._renderers.get(piece_key)
        if renderer is None:
            renderer = QSvgRenderer(str(self._assets.piece_path(piece_key)))
            if not renderer.isValid():
                raise ValueError(f"Invalid SVG asset: {piece_key}")
            self._renderers[piece_key] = renderer
        return renderer

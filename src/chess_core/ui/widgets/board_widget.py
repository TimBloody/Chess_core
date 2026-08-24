"""Board drawing widget for arbitrary rectangular boards."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QPointF, QSize, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QSizePolicy, QWidget

from chess_core.core.piece import PieceSide
from chess_core.ui.assets_loader import AssetsLoader
from chess_core.ui.piece_keys import parse_display_key


class BoardOrientation(Enum):
    WHITE = "white"
    BLACK = "black"


@dataclass(frozen=True)
class BoardTransform:
    """Convert between logical and displayed coordinates for one orientation."""

    files: int
    ranks: int
    orientation: BoardOrientation

    def logical_to_display(self, file: int, rank: int) -> tuple[int, int]:
        self._validate_coordinates(file, rank)
        if self.orientation is BoardOrientation.WHITE:
            return file, rank
        return self.files - 1 - file, self.ranks - 1 - rank

    def display_to_logical(self, file: int, rank: int) -> tuple[int, int]:
        # A 180-degree rotation is its own inverse.
        return self.logical_to_display(file, rank)

    def logical_index_to_display(self, square: int) -> int:
        file, rank = self._coordinates(square)
        display_file, display_rank = self.logical_to_display(file, rank)
        return display_rank * self.files + display_file

    def display_index_to_logical(self, square: int) -> int:
        file, rank = self._coordinates(square)
        logical_file, logical_rank = self.display_to_logical(file, rank)
        return logical_rank * self.files + logical_file

    def _coordinates(self, square: int) -> tuple[int, int]:
        if not isinstance(square, int):
            raise TypeError("Square index must be an integer")
        if not 0 <= square < self.files * self.ranks:
            raise ValueError("Square index out of board bounds")
        return square % self.files, square // self.files

    def _validate_coordinates(self, file: int, rank: int) -> None:
        if not 0 <= file < self.files or not 0 <= rank < self.ranks:
            raise ValueError("Board coordinates out of bounds")


@dataclass(frozen=True)
class BoardNotation:
    """Coordinate labels for arbitrary rectangular boards."""

    file_labels: tuple[str, ...]
    rank_labels: tuple[str, ...]

    @classmethod
    def for_shape(
        cls,
        files: int,
        ranks: int,
        *,
        file_labels: Iterable[str] | None = None,
        rank_labels: Iterable[str] | None = None,
    ) -> "BoardNotation":
        files_tuple = (
            tuple(file_labels)
            if file_labels is not None
            else tuple(cls.default_file_labels(files))
        )
        ranks_tuple = (
            tuple(rank_labels)
            if rank_labels is not None
            else tuple(str(rank + 1) for rank in range(ranks))
        )
        if len(files_tuple) != files:
            raise ValueError("File labels count must match board files")
        if len(ranks_tuple) != ranks:
            raise ValueError("Rank labels count must match board ranks")
        if any(not isinstance(label, str) for label in files_tuple + ranks_tuple):
            raise TypeError("Coordinate labels must be strings")
        if any(label == "" for label in files_tuple + ranks_tuple):
            raise ValueError("Coordinate labels must not be empty")
        return cls(files_tuple, ranks_tuple)

    @staticmethod
    def default_file_labels(files: int) -> list[str]:
        labels: list[str] = []
        for index in range(files):
            value = index
            chars: list[str] = []
            while True:
                value, remainder = divmod(value, 26)
                chars.append(chr(ord("a") + remainder))
                if value == 0:
                    break
                value -= 1
            labels.append("".join(reversed(chars)))
        return labels

    def matches_shape(self, files: int, ranks: int) -> bool:
        return len(self.file_labels) == files and len(self.rank_labels) == ranks

    def file_label(self, file: int) -> str:
        return self.file_labels[file]

    def rank_label(self, rank: int) -> str:
        return self.rank_labels[rank]


class BoardWidget(QWidget):
    """Render a board grid and SVG pieces without embedding game rules."""

    square_clicked = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None, assets_loader: AssetsLoader | None = None) -> None:
        super().__init__(parent)
        self._files = 8
        self._ranks = 8
        self._position: dict[int, str] = {}
        self._selected_square: int | None = None
        self._legal_destinations: set[int] = set()
        self._check_squares: set[int] = set()
        self._blocked_squares: set[int] = set()
        self._type_highlights: set[int] = set()
        self._last_move_squares: set[int] = set()
        self._engine_squares: set[int] = set()
        self._lit_squares: set[int] = set()
        self._error_squares: set[int] = set()
        self._mismatch_squares: set[int] = set()
        self._missed_squares: set[int] = set()
        self._orientation = BoardOrientation.WHITE
        self._transform = BoardTransform(self._files, self._ranks, self._orientation)
        self._coordinates_visible = True
        self._notation = BoardNotation.for_shape(self._files, self._ranks)
        self._assets_loader = assets_loader or AssetsLoader()
        self._renderers: dict[str, QSvgRenderer] = {}

        self.setMinimumSize(QSize(160, 160))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_shape(self, files: int, ranks: int) -> None:
        """Set board dimensions in files x ranks."""

        if files <= 0 or ranks <= 0:
            raise ValueError("Board shape dimensions must be positive")

        self._files = files
        self._ranks = ranks
        self._transform = BoardTransform(files, ranks, self._orientation)
        if not self._notation.matches_shape(files, ranks):
            self._notation = BoardNotation.for_shape(files, ranks)
        self._position = {
            square: piece_key
            for square, piece_key in self._position.items()
            if 0 <= square < self._cell_count
        }
        self.clear_highlights()
        self.update()

    def set_position(self, position: Mapping[int, str]) -> None:
        """Set pieces as a mapping of row-major square index to piece key."""

        normalized: dict[int, str] = {}
        for square, piece_key in position.items():
            if not isinstance(square, int):
                raise TypeError("Position square indices must be integers")
            if not isinstance(piece_key, str):
                raise TypeError("Position piece keys must be strings")
            if not 0 <= square < self._cell_count:
                raise ValueError(f"Square index out of board bounds: {square}")
            normalized[square] = piece_key

        if normalized != self._position:
            self._position = normalized
            self.update()

    def set_highlights(
        self,
        *,
        selected: int | None = None,
        legal_destinations: Iterable[int] = (),
        check_squares: Iterable[int] = (),
        blocked_squares: Iterable[int] = (),
        type_highlights: Iterable[int] = (),
        last_move_squares: Iterable[int] = (),
        engine_squares: Iterable[int] = (),
        lit_squares: Iterable[int] = (),
        error_squares: Iterable[int] = (),
        mismatch_squares: Iterable[int] = (),
        missed_squares: Iterable[int] = (),
    ) -> None:
        """Set presentation-only square highlights."""

        squares = set(legal_destinations)
        checks = set(check_squares)
        blocked = set(blocked_squares)
        typed = set(type_highlights)
        last_moves = set(last_move_squares)
        engine = set(engine_squares)
        lit = set(lit_squares)
        errors = set(error_squares)
        mismatches = set(mismatch_squares)
        missed = set(missed_squares)
        values = (
            squares
            | checks
            | blocked
            | typed
            | last_moves
            | engine
            | lit
            | errors
            | mismatches
            | missed
            | ({selected} if selected is not None else set())
        )
        if any(not 0 <= square < self._cell_count for square in values):
            raise ValueError("Highlight square index out of board bounds")
        if (
            selected != self._selected_square
            or squares != self._legal_destinations
            or checks != self._check_squares
            or blocked != self._blocked_squares
            or typed != self._type_highlights
            or last_moves != self._last_move_squares
            or engine != self._engine_squares
            or lit != self._lit_squares
            or errors != self._error_squares
            or mismatches != self._mismatch_squares
            or missed != self._missed_squares
        ):
            self._selected_square = selected
            self._legal_destinations = squares
            self._check_squares = checks
            self._blocked_squares = blocked
            self._type_highlights = typed
            self._last_move_squares = last_moves
            self._engine_squares = engine
            self._lit_squares = lit
            self._error_squares = errors
            self._mismatch_squares = mismatches
            self._missed_squares = missed
            self.update()

    def clear_highlights(self) -> None:
        self._selected_square = None
        self._legal_destinations.clear()
        self._check_squares.clear()
        self._blocked_squares.clear()
        self._type_highlights.clear()
        self._last_move_squares.clear()
        self._engine_squares.clear()
        self._lit_squares.clear()
        self._error_squares.clear()
        self._mismatch_squares.clear()
        self._missed_squares.clear()
        self.update()

    @property
    def files(self) -> int:
        return self._files

    @property
    def ranks(self) -> int:
        return self._ranks

    @property
    def position(self) -> dict[int, str]:
        return dict(self._position)

    @property
    def orientation(self) -> BoardOrientation:
        return self._orientation

    @property
    def coordinates_visible(self) -> bool:
        return self._coordinates_visible

    @property
    def notation(self) -> BoardNotation:
        return self._notation

    @property
    def transform(self) -> BoardTransform:
        return self._transform

    def set_orientation(self, orientation: BoardOrientation) -> None:
        """Set which side is viewed from, without changing logical position data."""
        if not isinstance(orientation, BoardOrientation):
            raise TypeError("orientation must be a BoardOrientation")
        if orientation is not self._orientation:
            self._orientation = orientation
            self._transform = BoardTransform(self._files, self._ranks, orientation)
            self.update()

    def flip_orientation(self) -> None:
        """Rotate square positions 180 degrees while keeping piece art upright."""
        self.set_orientation(
            BoardOrientation.BLACK
            if self._orientation is BoardOrientation.WHITE
            else BoardOrientation.WHITE
        )

    def set_coordinates_visible(self, visible: bool) -> None:
        if visible != self._coordinates_visible:
            self._coordinates_visible = visible
            self.update()

    def set_notation(
        self,
        *,
        file_labels: Iterable[str] | None = None,
        rank_labels: Iterable[str] | None = None,
    ) -> None:
        """Set coordinate labels; omitted axes use generic defaults."""

        notation = BoardNotation.for_shape(
            self._files,
            self._ranks,
            file_labels=file_labels,
            rank_labels=rank_labels,
        )
        if notation != self._notation:
            self._notation = notation
            self.update()

    def logical_to_display_square(self, square: int) -> int:
        """Map a logical row-major square to display row-major coordinates."""
        return self._transform.logical_index_to_display(square)

    def display_to_logical_square(self, square: int) -> int:
        """Map display row-major coordinates back to a logical square."""
        return self._transform.display_index_to_logical(square)

    def edge_labels(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return bottom files left-to-right and left ranks bottom-to-top."""
        bottom_files = tuple(
            self._notation.file_label(
                self._transform.display_to_logical(display_file, 0)[0]
            )
            for display_file in range(self._files)
        )
        left_ranks = tuple(
            self._notation.rank_label(
                self._transform.display_to_logical(0, display_rank)[1]
            )
            for display_rank in range(self._ranks)
        )
        return bottom_files, left_ranks

    def sizeHint(self) -> QSize:
        return QSize(480, 480)

    def paintEvent(self, event) -> None:  # noqa: ANN001 - Qt override signature
        del event

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        board_rect, cell_size = self._board_geometry()
        self._draw_squares(painter, board_rect, cell_size)
        self._draw_highlights(painter, board_rect, cell_size)
        self._draw_pieces(painter, board_rect, cell_size)
        self._draw_coordinates(painter, board_rect, cell_size)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001 - Qt override signature
        square = self.square_at_position(event.position())
        if square is not None:
            self.square_clicked.emit(square)
        super().mousePressEvent(event)

    def square_at_position(self, point: QPointF) -> int | None:
        """Map a widget point to a logical row-major square."""
        board_rect, cell_size = self._board_geometry()
        if not board_rect.contains(point):
            return None
        file = min(
            self._files - 1, int((point.x() - board_rect.left()) / cell_size)
        )
        visual_rank = min(
            self._ranks - 1, int((point.y() - board_rect.top()) / cell_size)
        )
        display_rank = self._ranks - 1 - visual_rank
        return self.display_to_logical_square(display_rank * self._files + file)

    def is_light_square(self, square: int) -> bool:
        """Return board-color parity; a1/index 0 is dark."""
        if not 0 <= square < self._cell_count:
            raise ValueError("Square index out of board bounds")
        return ((square % self._files) + (square // self._files)) % 2 == 1

    @property
    def _cell_count(self) -> int:
        return self._files * self._ranks

    def _board_geometry(self) -> tuple[QRectF, float]:
        left_units, bottom_units = self._notation_gutter_units()
        cell_size = min(
            self.width() / (self._files + left_units),
            self.height() / (self._ranks + bottom_units),
        )
        board_width = cell_size * self._files
        board_height = cell_size * self._ranks
        footprint_width = board_width + cell_size * left_units
        footprint_height = board_height + cell_size * bottom_units
        left = (self.width() - footprint_width) / 2 + cell_size * left_units
        top = (self.height() - footprint_height) / 2
        return QRectF(left, top, board_width, board_height), cell_size

    def _notation_gutter_units(self) -> tuple[float, float]:
        if not self._coordinates_visible:
            return 0.0, 0.0
        longest_rank = max(map(len, self._notation.rank_labels), default=1)
        return max(0.42, 0.16 * longest_rank + 0.16), 0.42

    def _draw_squares(self, painter: QPainter, board_rect: QRectF, cell_size: float) -> None:
        light = self._renderer("board:light", str(self._assets_loader.light_square_path))
        dark = self._renderer("board:dark", str(self._assets_loader.dark_square_path))

        for rank in range(self._ranks):
            for file in range(self._files):
                square = rank * self._files + file
                renderer = (
                    light
                    if self.is_light_square(square)
                    else dark
                )
                renderer.render(
                    painter, self._logical_square_rect(board_rect, cell_size, square)
                )

    def _draw_pieces(self, painter: QPainter, board_rect: QRectF, cell_size: float) -> None:
        piece_margin = cell_size * 0.08

        for square, piece_key in self._position.items():
            square_rect = self._logical_square_rect(board_rect, cell_size, square)
            piece_rect = square_rect.adjusted(piece_margin, piece_margin, -piece_margin, -piece_margin)
            renderer = self._renderer(f"piece:{piece_key}", str(self._assets_loader.piece_path(piece_key)))
            if self._should_rotate_piece(piece_key):
                painter.save()
                painter.translate(piece_rect.center())
                painter.rotate(180)
                painter.translate(-piece_rect.center())
                renderer.render(painter, piece_rect)
                painter.restore()
            else:
                renderer.render(painter, piece_rect)

    def _should_rotate_piece(self, piece_key: str) -> bool:
        _stem, owner = parse_display_key(piece_key)
        if owner is None:
            return False
        facing_black = self._orientation is BoardOrientation.BLACK
        if facing_black:
            return owner is PieceSide.WHITE
        return owner is PieceSide.BLACK

    def _draw_highlights(self, painter: QPainter, board_rect: QRectF, cell_size: float) -> None:
        for square in self._blocked_squares:
            self._fill_square(
                painter, board_rect, cell_size, square, QColor(40, 40, 40, 110)
            )
        for square in self._type_highlights:
            self._fill_square(
                painter, board_rect, cell_size, square, QColor(80, 170, 255, 120)
            )
        for square in self._missed_squares:
            self._fill_square(
                painter, board_rect, cell_size, square, QColor(70, 170, 90, 155)
            )
        for square in self._lit_squares:
            self._fill_square(
                painter, board_rect, cell_size, square, QColor(70, 150, 230, 170)
            )
        for square in self._last_move_squares:
            self._fill_square(
                painter, board_rect, cell_size, square, QColor(205, 210, 106, 165)
            )
        for square in self._engine_squares:
            self._fill_square(
                painter, board_rect, cell_size, square, QColor(156, 80, 220, 180)
            )
        for square in self._mismatch_squares:
            self._fill_square(
                painter, board_rect, cell_size, square, QColor(232, 196, 48, 185)
            )
        if self._selected_square is not None:
            self._fill_square(
                painter, board_rect, cell_size, self._selected_square, QColor(246, 246, 105, 170)
            )
        for square in self._legal_destinations:
            rect = self._logical_square_rect(board_rect, cell_size, square)
            diameter = cell_size * (0.34 if square not in self._position else 0.82)
            marker = QRectF(
                rect.center().x() - diameter / 2,
                rect.center().y() - diameter / 2,
                diameter,
                diameter,
            )
            painter.setBrush(QColor(40, 40, 40, 80))
            painter.setPen(QColor(40, 40, 40, 100))
            painter.drawEllipse(marker)
        for square in self._check_squares:
            self._fill_square(
                painter, board_rect, cell_size, square, QColor(220, 40, 40, 145)
            )
        for square in self._error_squares:
            self._fill_square(
                painter, board_rect, cell_size, square, QColor(220, 40, 40, 165)
            )

    def _draw_coordinates(self, painter: QPainter, board_rect: QRectF, cell_size: float) -> None:
        if not self._coordinates_visible:
            return

        font = QFont(painter.font())
        font.setBold(True)
        font.setPixelSize(max(1, min(18, int(cell_size * 0.20))))
        painter.setFont(font)
        painter.setPen(self.palette().color(self.foregroundRole()))
        left_units, bottom_units = self._notation_gutter_units()
        bottom_files, left_ranks = self.edge_labels()

        left_gutter = cell_size * left_units
        for display_rank, label in enumerate(left_ranks):
            rect = self._square_rect(board_rect, cell_size, 0, display_rank)
            painter.drawText(
                QRectF(
                    board_rect.left() - left_gutter,
                    rect.top(),
                    left_gutter * 0.88,
                    cell_size,
                ),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                label,
            )

        bottom_gutter = cell_size * bottom_units
        for display_file, label in enumerate(bottom_files):
            rect = self._square_rect(board_rect, cell_size, display_file, 0)
            painter.drawText(
                QRectF(
                    rect.left(),
                    board_rect.bottom(),
                    cell_size,
                    bottom_gutter,
                ),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label,
            )

    def _fill_square(
        self,
        painter: QPainter,
        board_rect: QRectF,
        cell_size: float,
        square: int,
        color: QColor,
    ) -> None:
        painter.fillRect(
            self._logical_square_rect(board_rect, cell_size, square),
            color,
        )

    def _logical_square_rect(
        self, board_rect: QRectF, cell_size: float, square: int
    ) -> QRectF:
        display_square = self.logical_to_display_square(square)
        return self._square_rect(
            board_rect,
            cell_size,
            display_square % self._files,
            display_square // self._files,
        )

    def _square_rect(self, board_rect: QRectF, cell_size: float, file: int, rank: int) -> QRectF:
        x = board_rect.left() + file * cell_size
        y = board_rect.top() + (self._ranks - 1 - rank) * cell_size
        return QRectF(x, y, cell_size, cell_size)

    def _validate_square(self, square: int) -> None:
        self._transform.logical_index_to_display(square)

    def _renderer(self, cache_key: str, path: str) -> QSvgRenderer:
        renderer = self._renderers.get(cache_key)
        if renderer is None:
            renderer = QSvgRenderer(path)
            if not renderer.isValid():
                raise ValueError(f"Invalid SVG asset: {path}")
            self._renderers[cache_key] = renderer
        return renderer

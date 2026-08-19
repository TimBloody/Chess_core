"""Memory mini-games: shape recall, sequence recall, and position reconstruction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from random import Random

from chess_core.app.editor import BoardEditorService
from chess_core.app.memory import MemoryTrainingService
from chess_core.core.gamemode import GameMode
from chess_core.core.piece import Piece, PieceSide
from chess_core.core.state import GameState
from chess_core.modes.chess import classic_chess


class MemoryFormat(str, Enum):
    SHAPE = "shape"
    SEQUENCE = "sequence"
    POSITION = "position"


@dataclass(frozen=True)
class ShapePrompt:
    """A figure of lit cells on an n×n grid."""

    size: int
    cells: frozenset[int]
    reveal_ms: int


@dataclass(frozen=True)
class SequencePrompt:
    """Cells that light one after another; the player repeats the order."""

    size: int
    sequence: tuple[int, ...]
    step_ms: int


class ShapeMemoryService:
    """Generate and grade connected figures on a square grid."""

    def generate(
        self,
        size: int,
        cell_count: int,
        reveal_ms: int = 2500,
        rng: Random | None = None,
    ) -> ShapePrompt:
        if size < 2:
            raise ValueError("size must be at least 2")
        if cell_count < 1:
            raise ValueError("cell_count must be positive")
        if reveal_ms < 0:
            raise ValueError("reveal_ms must be non-negative")
        total = size * size
        if cell_count > total:
            raise ValueError("cell_count exceeds the grid")
        rng = rng or Random()
        cells = _grow_polyomino(size, cell_count, rng)
        return ShapePrompt(size=size, cells=frozenset(cells), reveal_ms=reveal_ms)

    def grade(self, prompt: ShapePrompt, attempt: set[int] | frozenset[int]) -> float:
        if any(not 0 <= index < prompt.size * prompt.size for index in attempt):
            raise ValueError("attempt contains a square outside the grid")
        if not prompt.cells and not attempt:
            return 1.0
        union = prompt.cells | frozenset(attempt)
        if not union:
            return 1.0
        return len(prompt.cells & frozenset(attempt)) / len(union)

    def is_perfect(self, prompt: ShapePrompt, attempt: set[int] | frozenset[int]) -> bool:
        return frozenset(attempt) == prompt.cells


class SequenceMemoryService:
    """Generate and grade ordered cell flashes."""

    def generate(
        self,
        size: int,
        length: int,
        step_ms: int = 700,
        *,
        allow_repeats: bool = False,
        rng: Random | None = None,
    ) -> SequencePrompt:
        if size < 2:
            raise ValueError("size must be at least 2")
        if length < 1:
            raise ValueError("length must be positive")
        if step_ms < 0:
            raise ValueError("step_ms must be non-negative")
        total = size * size
        rng = rng or Random()
        if allow_repeats:
            sequence = tuple(rng.randrange(total) for _ in range(length))
        else:
            if length > total:
                raise ValueError("length exceeds the grid")
            sequence = tuple(rng.sample(range(total), length))
        return SequencePrompt(size=size, sequence=sequence, step_ms=step_ms)

    def grade(self, prompt: SequencePrompt, attempt: list[int] | tuple[int, ...]) -> float:
        if any(not 0 <= index < prompt.size * prompt.size for index in attempt):
            raise ValueError("attempt contains a square outside the grid")
        expected = prompt.sequence
        if not expected:
            return 1.0
        matched = 0
        for left, right in zip(expected, attempt, strict=False):
            if left != right:
                break
            matched += 1
        return matched / len(expected)

    def is_perfect(
        self, prompt: SequencePrompt, attempt: list[int] | tuple[int, ...]
    ) -> bool:
        return tuple(attempt) == prompt.sequence


@dataclass(frozen=True)
class PositionDiff:
    """Per-square reconstruction errors against the remembered position."""

    extra: frozenset[int]
    mismatch: frozenset[int]
    missed: frozenset[int]
    score: float


class PositionMemoryService:
    """Show a chess-like position, then grade reconstruction via the editor service."""

    def __init__(self, grader: MemoryTrainingService | None = None) -> None:
        self._grader = grader or MemoryTrainingService()

    def generate(
        self,
        mode: GameMode | None = None,
        piece_count: int = 8,
        reveal_seconds: float = 4.0,
        rng: Random | None = None,
    ) -> GameState:
        if piece_count < 1:
            raise ValueError("piece_count must be positive")
        if reveal_seconds < 0:
            raise ValueError("reveal_seconds must be non-negative")
        active = mode or classic_chess()
        rng = rng or Random()
        state = _random_position(active, piece_count, rng)
        self._grader.start_round(state, reveal_seconds)
        return state

    def grade(self, target: GameState, attempt: GameState) -> float:
        return self.compare(target, attempt).score

    def compare(self, target: GameState, attempt: GameState) -> PositionDiff:
        if target.board_state.board.shape != attempt.board_state.board.shape:
            raise ValueError("target and attempt board shapes differ")
        cell_count = target.board_state.board.shape.cell_count
        if cell_count == 0:
            return PositionDiff(extra=frozenset(), mismatch=frozenset(), missed=frozenset(), score=1.0)

        extra: set[int] = set()
        mismatch: set[int] = set()
        missed: set[int] = set()
        correct = 0
        for square_index in range(cell_count):
            expected = _piece_key(target.board_state.cells.get(square_index))
            actual = _piece_key(attempt.board_state.cells.get(square_index))
            if expected == actual:
                correct += 1
                continue
            if expected is None:
                extra.add(square_index)
            elif actual is None:
                missed.add(square_index)
            else:
                mismatch.add(square_index)
        return PositionDiff(
            extra=frozenset(extra),
            mismatch=frozenset(mismatch),
            missed=frozenset(missed),
            score=correct / cell_count,
        )


def _grow_polyomino(size: int, cell_count: int, rng: Random) -> set[int]:
    total = size * size
    start = rng.randrange(total)
    cells = {start}
    while len(cells) < cell_count:
        frontier: list[int] = []
        for index in cells:
            frontier.extend(
                neighbor
                for neighbor in _orthogonal_neighbors(index, size)
                if neighbor not in cells
            )
        if not frontier:
            leftover = [index for index in range(total) if index not in cells]
            cells.add(rng.choice(leftover))
            continue
        cells.add(rng.choice(frontier))
    return cells


def _orthogonal_neighbors(index: int, size: int) -> list[int]:
    file, rank = index % size, index // size
    neighbors: list[int] = []
    for df, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        next_file, next_rank = file + df, rank + dr
        if 0 <= next_file < size and 0 <= next_rank < size:
            neighbors.append(next_rank * size + next_file)
    return neighbors


def _random_position(mode: GameMode, piece_count: int, rng: Random) -> GameState:
    editor = BoardEditorService(mode)
    editor.new_empty_position()
    cell_count = mode.board.shape.cell_count
    count = min(piece_count, cell_count)
    squares = list(range(cell_count))
    rng.shuffle(squares)
    types = [
        piece_type
        for piece_type in mode.pieces.all_types()
        if not piece_type.demotes_to
    ]
    if not types:
        raise ValueError("mode has no placeable piece types")
    royals = [piece_type.id.name for piece_type in types if piece_type.is_royal]
    others = [piece_type.id.name for piece_type in types if not piece_type.is_royal]
    sides = (PieceSide.WHITE, PieceSide.BLACK)
    placed = 0
    for royal in royals:
        for side in sides:
            if placed >= count:
                return editor.state
            editor.set_piece(squares[placed], royal, side.name.lower())
            placed += 1
    pool = others or [piece_type.id.name for piece_type in types]
    while placed < count:
        editor.set_piece(squares[placed], rng.choice(pool), rng.choice(sides).name.lower())
        placed += 1
    return editor.state


def _piece_key(piece: Piece | None) -> tuple[str, str] | None:
    if piece is None:
        return None
    return (piece.piece_type.name, piece.side.name)


def _piece_key(piece: Piece | None) -> tuple[str, str] | None:
    if piece is None:
        return None
    return (piece.piece_type.name, piece.side.name)

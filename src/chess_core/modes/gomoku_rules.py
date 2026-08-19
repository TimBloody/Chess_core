"""Rules strategy for freestyle Gomoku on a 15x15 board."""

from __future__ import annotations

from chess_core.core.board import Square
from chess_core.core.move import PlaceAction, Turn
from chess_core.core.notation import NotationStyle, format_turn
from chess_core.core.outcome import GameOutcome, OutcomeStatus
from chess_core.core.piece import PieceSide, PieceTypeId
from chess_core.core.state import GameState

STONE = PieceTypeId("stone")

_AXES = ((1, 0), (0, 1), (1, 1), (1, -1))
_WIN_LENGTH = 5


class GomokuRulesStrategy:
    """Place stones on empty cells; five-or-more in a line wins."""

    def legal_turns(self, state: GameState) -> list[Turn]:
        if self.outcome(state).is_finished:
            return []
        shape = state.board_state.board.shape
        side = state.side_to_move
        turns: list[Turn] = []
        for index in range(shape.cell_count):
            if state.board_state.piece_at(index) is None:
                square = Square.from_index(index, shape.files, shape.ranks)
                turns.append(Turn(side, [PlaceAction(STONE, square)]))
        return turns

    def apply_turn(
        self, state: GameState, turn: Turn, *, record_history: bool = True
    ) -> GameState:
        return state.apply_turn(turn, record_history=record_history)

    def outcome(self, state: GameState) -> GameOutcome:
        for side in (PieceSide.BLACK, PieceSide.WHITE):
            if _side_has_winning_line(state, side):
                return GameOutcome(
                    status=OutcomeStatus.WIN,
                    winner=side,
                    reason="five-in-a-row",
                )
        if _board_full(state):
            return GameOutcome(status=OutcomeStatus.DRAW, reason="board-full")
        return GameOutcome(status=OutcomeStatus.ACTIVE)

    def format_turn(
        self,
        turn: Turn,
        *,
        before: GameState,
        after: GameState,
        style: NotationStyle = NotationStyle.FROM_TO,
    ) -> str:
        return format_turn(turn, before=before, after=after, style=style)


def _board_full(state: GameState) -> bool:
    return all(piece is not None for piece in state.board_state.cells.values())


def _side_has_winning_line(state: GameState, side: PieceSide) -> bool:
    shape = state.board_state.board.shape
    files = shape.files
    ranks = shape.ranks
    for index, piece in state.board_state.cells.items():
        if piece is None or piece.side is not side:
            continue
        square = Square.from_index(index, files, ranks)
        for df, dr in _AXES:
            if _line_length(state, square, side, df, dr, files, ranks) >= _WIN_LENGTH:
                return True
    return False


def _line_length(
    state: GameState,
    origin: Square,
    side: PieceSide,
    df: int,
    dr: int,
    files: int,
    ranks: int,
) -> int:
    count = 1
    file = origin.file + df
    rank = origin.rank + dr
    while 0 <= file < files and 0 <= rank < ranks:
        piece = state.board_state.piece_at(rank * files + file)
        if piece is None or piece.side is not side:
            break
        count += 1
        file += df
        rank += dr
    file = origin.file - df
    rank = origin.rank - dr
    while 0 <= file < files and 0 <= rank < ranks:
        piece = state.board_state.piece_at(rank * files + file)
        if piece is None or piece.side is not side:
            break
        count += 1
        file -= df
        rank -= dr
    return count

"""Move generation and rules strategy for Russian Corners (Уголки)."""

from __future__ import annotations

from chess_core.core.board import Square
from chess_core.core.move import Action, MoveAction, Turn
from chess_core.core.notation import NotationStyle, format_turn
from chess_core.core.outcome import GameOutcome, OutcomeStatus
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import GameState

CORNER = PieceTypeId("corner")
ORTHOGONALS = ((0, 1), (0, -1), (1, 0), (-1, 0))


class CornersMoveProvider:
    """Orthogonal steps and jump chains without captures."""

    def pseudo_legal(self, state: object) -> list[Action]:
        if not isinstance(state, GameState):
            raise TypeError("corners move provider requires GameState")

        moves: list[MoveAction] = []
        for index, piece in state.board_state.cells.items():
            if piece is None or piece.side is not state.side_to_move:
                continue
            origin = Square.from_index(
                index,
                state.board_state.board.shape.files,
                state.board_state.board.shape.ranks,
            )
            moves.extend(self._quiet_moves(state, origin))
            moves.extend(self._jump_sequences(state, origin))
        return moves

    def _quiet_moves(
        self, state: GameState, origin: Square
    ) -> list[MoveAction]:
        moves: list[MoveAction] = []
        for df, dr in ORTHOGONALS:
            target = self._step(state, origin, df, dr)
            if target is not None and self._empty(state, target, origin, origin):
                moves.append(
                    MoveAction(origin, target, path=(target,), captured_squares=())
                )
        return moves

    def _jump_sequences(
        self, state: GameState, origin: Square
    ) -> list[MoveAction]:
        results: list[MoveAction] = []
        self._search_jumps(
            state=state,
            origin=origin,
            current=origin,
            path=(),
            visited=frozenset({origin}),
            results=results,
        )
        return results

    def _search_jumps(
        self,
        *,
        state: GameState,
        origin: Square,
        current: Square,
        path: tuple[Square, ...],
        visited: frozenset[Square],
        results: list[MoveAction],
    ) -> None:
        continuations = [
            landing
            for landing in self._single_jumps(state, origin, current)
            if landing not in visited
        ]
        if not continuations:
            if path:
                results.append(
                    MoveAction(
                        origin,
                        current,
                        path=path,
                        captured_squares=(),
                    )
                )
            return

        for landing in continuations:
            self._search_jumps(
                state=state,
                origin=origin,
                current=landing,
                path=path + (landing,),
                visited=visited | {landing},
                results=results,
            )

    def _single_jumps(
        self, state: GameState, origin: Square, current: Square
    ) -> list[Square]:
        results: list[Square] = []
        for df, dr in ORTHOGONALS:
            hurdle = self._step(state, current, df, dr)
            if hurdle is None:
                continue
            if self._occupant(state, hurdle, origin, current) is None:
                continue
            landing = self._step(state, hurdle, df, dr)
            if landing is None:
                continue
            if self._empty(state, landing, origin, current):
                results.append(landing)
        return results

    @staticmethod
    def _step(
        state: GameState, square: Square, df: int, dr: int
    ) -> Square | None:
        file = square.file + df
        rank = square.rank + dr
        shape = state.board_state.board.shape
        if 0 <= file < shape.files and 0 <= rank < shape.ranks:
            return Square(file, rank)
        return None

    def _empty(
        self,
        state: GameState,
        square: Square,
        origin: Square,
        current: Square,
    ) -> bool:
        return self._occupant(state, square, origin, current) is None

    @staticmethod
    def _occupant(
        state: GameState,
        square: Square,
        origin: Square,
        current: Square,
    ) -> Piece | None:
        if square == origin or square == current:
            return None
        return state.board_state.piece_at(
            square.index(state.board_state.board.shape.files)
        )


class CornersRulesStrategy:
    """Custom legal turns and home-corner victory detection."""

    def __init__(self) -> None:
        self._provider = CornersMoveProvider()

    def legal_turns(self, state: GameState) -> list[Turn]:
        if self.outcome(state).is_finished:
            return []
        side = state.side_to_move
        return [
            Turn(side, [action])
            for action in self._provider.pseudo_legal(state)
            if isinstance(action, MoveAction)
        ]

    def apply_turn(
        self, state: GameState, turn: Turn, *, record_history: bool = True
    ) -> GameState:
        return state.apply_turn(turn, record_history=record_history)

    def outcome(self, state: GameState) -> GameOutcome:
        white_home = state.extras.get("white_home")
        black_home = state.extras.get("black_home")
        if not isinstance(white_home, frozenset) or not isinstance(
            black_home, frozenset
        ):
            return GameOutcome(status=OutcomeStatus.ACTIVE)

        if _all_pieces_in_zone(state, PieceSide.WHITE, black_home):
            return GameOutcome(
                status=OutcomeStatus.WIN,
                winner=PieceSide.WHITE,
                reason="home",
            )
        if _all_pieces_in_zone(state, PieceSide.BLACK, white_home):
            return GameOutcome(
                status=OutcomeStatus.WIN,
                winner=PieceSide.BLACK,
                reason="home",
            )
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


def _all_pieces_in_zone(
    state: GameState, side: PieceSide, zone: frozenset[int]
) -> bool:
    found = False
    for index, piece in state.board_state.cells.items():
        if piece is None or piece.side is not side:
            continue
        found = True
        if index not in zone:
            return False
    return found


def layout_homes(layout: str) -> tuple[frozenset[int], frozenset[int]]:
    """Return ``(white_home, black_home)`` square-index sets for a layout."""
    if layout == "3x3":
        white = _rect_indices(range(5, 8), range(0, 3))
        black = _rect_indices(range(0, 3), range(5, 8))
    elif layout == "3x4":
        white = _rect_indices(range(5, 8), range(0, 4))
        black = _rect_indices(range(0, 3), range(4, 8))
    elif layout == "1234":
        white = frozenset(
            {
                *_rect_indices(range(4, 8), range(0, 1)),
                *_rect_indices(range(5, 8), range(1, 2)),
                *_rect_indices(range(6, 8), range(2, 3)),
                _algebraic_index("h4"),
            }
        )
        black = frozenset(
            {
                *_rect_indices(range(0, 4), range(7, 8)),
                *_rect_indices(range(0, 3), range(6, 7)),
                *_rect_indices(range(0, 2), range(5, 6)),
                _algebraic_index("a5"),
            }
        )
    else:
        raise ValueError(f"unknown corners layout: {layout}")
    return white, black


def _rect_indices(
    files: range, ranks: range, *, board_files: int = 8
) -> frozenset[int]:
    return frozenset(
        rank * board_files + file for rank in ranks for file in files
    )


def _algebraic_index(label: str) -> int:
    file = ord(label[0]) - ord("a")
    rank = int(label[1]) - 1
    return rank * 8 + file

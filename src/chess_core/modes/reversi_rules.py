"""Rules strategy for 8x8 Reversi / Othello (WOF)."""

from __future__ import annotations

from chess_core.core.board import Square
from chess_core.core.move import PassAction, PlaceAction, Turn
from chess_core.core.notation import NotationStyle, format_turn
from chess_core.core.outcome import GameOutcome, OutcomeStatus
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import GameState

DISC = PieceTypeId("reversi_disc")

DIRECTIONS = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)


def _opponent(side: PieceSide) -> PieceSide:
    return PieceSide.BLACK if side is PieceSide.WHITE else PieceSide.WHITE


def _disc_counts(state: GameState) -> tuple[int, int]:
    white = 0
    black = 0
    for piece in state.board_state.cells.values():
        if piece is None:
            continue
        if piece.side is PieceSide.WHITE:
            white += 1
        elif piece.side is PieceSide.BLACK:
            black += 1
    return white, black


def _on_board(state: GameState, file: int, rank: int) -> bool:
    shape = state.board_state.board.shape
    return 0 <= file < shape.files and 0 <= rank < shape.ranks


def _flips_in_direction(
    state: GameState, square: Square, side: PieceSide, df: int, dr: int
) -> list[int]:
    shape = state.board_state.board.shape
    files = shape.files
    opponent = _opponent(side)
    flips: list[int] = []
    file = square.file + df
    rank = square.rank + dr
    while _on_board(state, file, rank):
        index = Square(file, rank).index(files)
        piece = state.board_state.piece_at(index)
        if piece is None:
            return []
        if piece.side is opponent:
            flips.append(index)
        elif piece.side is side:
            return flips
        else:
            return []
        file += df
        rank += dr
    return []


def flips_for_placement(
    state: GameState, square: Square, side: PieceSide
) -> tuple[int, ...]:
    """Indices of opponent discs flipped by placing on ``square`` for ``side``."""
    shape = state.board_state.board.shape
    target = square.index(shape.files)
    if state.board_state.piece_at(target) is not None:
        return ()
    seen: set[int] = set()
    ordered: list[int] = []
    for df, dr in DIRECTIONS:
        for index in _flips_in_direction(state, square, side, df, dr):
            if index not in seen:
                seen.add(index)
                ordered.append(index)
    return tuple(ordered)


def legal_placements(state: GameState, side: PieceSide) -> list[PlaceAction]:
    shape = state.board_state.board.shape
    actions: list[PlaceAction] = []
    for index in range(shape.cell_count):
        if state.board_state.piece_at(index) is not None:
            continue
        square = Square.from_index(index, shape.files, shape.ranks)
        if flips_for_placement(state, square, side):
            actions.append(PlaceAction(DISC, square))
    return actions


class ReversiRulesStrategy:
    """Place discs with bracket capture; pass when blocked; count discs at end."""

    def legal_turns(self, state: GameState) -> list[Turn]:
        side = state.side_to_move
        placements = legal_placements(state, side)
        if placements:
            return [Turn(side, [action]) for action in placements]
        opponent = _opponent(side)
        if legal_placements(state, opponent):
            return [Turn(side, [PassAction()])]
        return []

    def apply_turn(
        self, state: GameState, turn: Turn, *, record_history: bool = True
    ) -> GameState:
        if turn.side is not state.side_to_move:
            raise ValueError("turn side does not match side_to_move")
        if not turn.actions:
            raise ValueError("turn must contain at least one action")

        mode = state.extras.get("mode")
        if mode is not None and not mode.turn_scenario.validate_turn(turn):
            raise ValueError("turn does not match the game mode turn scenario")

        legal = {self._turn_key(candidate) for candidate in self.legal_turns(state)}
        if self._turn_key(turn) not in legal:
            raise ValueError("turn is not legal")

        result = state.clone(include_history=record_history)
        turn_actions: list[object] = []
        shape = result.board_state.board.shape
        files = shape.files

        for action in turn.actions:
            if isinstance(action, PlaceAction):
                target = action.to_square.index(files)
                if state.board_state.piece_at(target) is not None:
                    raise ValueError("cannot place onto an occupied square")
                flips = flips_for_placement(state, action.to_square, turn.side)
                if not flips:
                    raise ValueError("placement does not outflank any disc")
                result.board_state.cells[target] = Piece(DISC, turn.side)
                for index in flips:
                    result.board_state.cells[index] = Piece(DISC, turn.side)
            elif isinstance(action, PassAction):
                if legal_placements(state, turn.side):
                    raise ValueError("cannot pass while a placement is available")
                if not legal_placements(state, _opponent(turn.side)):
                    raise ValueError("cannot pass when the game is over")
            else:
                raise TypeError(f"unsupported action: {type(action).__name__}")
            turn_actions.append(action)

        if record_history:
            result.history.actions.extend(turn_actions)
            result.history.metadata.append({"turn_side": turn.side.name})

        if mode is not None:
            result.side_to_move = mode.turn_order.next_side(result.side_to_move)
        else:
            result.side_to_move = _opponent(result.side_to_move)
        return result

    def outcome(self, state: GameState) -> GameOutcome:
        side = state.side_to_move
        if legal_placements(state, side) or legal_placements(state, _opponent(side)):
            return GameOutcome(status=OutcomeStatus.ACTIVE)

        white, black = _disc_counts(state)
        score = (white, black)
        if white > black:
            return GameOutcome(
                status=OutcomeStatus.WIN,
                winner=PieceSide.WHITE,
                reason="disc_count",
                score=score,
            )
        if black > white:
            return GameOutcome(
                status=OutcomeStatus.WIN,
                winner=PieceSide.BLACK,
                reason="disc_count",
                score=score,
            )
        return GameOutcome(
            status=OutcomeStatus.DRAW,
            reason="disc_count",
            score=score,
        )

    def format_turn(
        self,
        turn: Turn,
        *,
        before: GameState,
        after: GameState,
        style: NotationStyle = NotationStyle.FROM_TO,
    ) -> str:
        return format_turn(turn, before=before, after=after, style=style)

    @staticmethod
    def _action_key(action: object) -> tuple[object, ...]:
        if isinstance(action, PlaceAction):
            return ("place", action.to_square.file, action.to_square.rank)
        if isinstance(action, PassAction):
            return ("pass",)
        return (type(action).__name__,)

    @classmethod
    def _turn_key(cls, turn: Turn) -> tuple[object, tuple[tuple[object, ...], ...]]:
        return (turn.side, tuple(cls._action_key(action) for action in turn.actions))

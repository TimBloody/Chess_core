"""Game position and history."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from chess_core.core.board import Board, Square
from chess_core.core.move import (
    Action,
    DropAction,
    MoveAction,
    PassAction,
    PlaceAction,
    PlaceBlockerAction,
    TransformAction,
    Turn,
)
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import CastlingPath

_ROOK_HOME_RIGHTS = {0: "Q", 7: "K", 56: "q", 63: "k"}


@dataclass
class BoardState:
    board: Board
    cells: dict[int, Piece | None]

    def piece_at(self, square_index: int) -> Piece | None:
        if not 0 <= square_index < self.board.shape.cell_count:
            raise ValueError("square_index is outside board cells")
        return self.cells.get(square_index)

    def iter_occupied(self):
        """Yield ``(index, piece)`` for occupied cells only."""
        for index, piece in self.cells.items():
            if piece is not None:
                yield index, piece


@dataclass
class HandsState:
    """Captured pieces in hand (shogi, crazyhouse)."""

    by_side: dict[PieceSide, list[Piece]] = field(default_factory=dict)

    def count(self, side: PieceSide, piece_type_name: str) -> int:
        return sum(
            piece.piece_type.name == piece_type_name
            for piece in self.by_side.get(side, ())
        )

    def add(self, side: PieceSide, piece: Piece) -> None:
        captured = deepcopy(piece)
        captured.side = side
        original = None
        if captured.state:
            original = captured.state.get("promoted_from")
            if original is None and captured.state.get("promoted"):
                original = "pawn"
        if original:
            captured.piece_type = PieceTypeId(str(original))
            captured.state = None
        self.by_side.setdefault(side, []).append(captured)


@dataclass
class HistoryState:
    actions: list[Action] = field(default_factory=list)
    metadata: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GameState:
    board_state: BoardState
    side_to_move: PieceSide
    hands: HandsState | None = None
    history: HistoryState = field(default_factory=HistoryState)
    extras: dict[str, Any] = field(default_factory=dict)

    def clone(self, *, include_history: bool = True) -> GameState:
        # A GameMode is position-independent configuration and can be large
        # (ray/mask tables).  Copy position-owned data, but deliberately share
        # the mode instead of recursively copying the complete ruleset for
        # every legality probe.
        extras = {
            key: value if key == "mode" else deepcopy(value)
            for key, value in self.extras.items()
        }
        history = (
            HistoryState(
                actions=list(self.history.actions),
                metadata=deepcopy(self.history.metadata),
            )
            if include_history
            else HistoryState()
        )
        return GameState(
            board_state=BoardState(
                self.board_state.board,
                {
                    index: _clone_piece(piece) if piece is not None else None
                    for index, piece in self.board_state.cells.items()
                },
            ),
            side_to_move=self.side_to_move,
            hands=(
                HandsState(
                    {
                        side: [_clone_piece(piece) for piece in pieces]
                        for side, pieces in self.hands.by_side.items()
                    }
                )
                if self.hands is not None
                else None
            ),
            history=history,
            extras=extras,
        )

    def apply_turn(
        self,
        turn: Turn,
        *,
        record_history: bool = True,
        validate_scenario: bool = True,
        switch_side: bool = True,
    ) -> GameState:
        if turn.side is not self.side_to_move:
            raise ValueError("turn side does not match side_to_move")
        if not turn.actions:
            raise ValueError("turn must contain at least one action")

        result = self.clone(include_history=True)
        mode = result.extras.get("mode")
        turn_actions: list[Action] = []
        policy = getattr(mode, "turn_policy", None) if mode is not None else None
        if validate_scenario and mode is not None:
            scenario = (
                policy.scenario_for(self)
                if policy is not None
                else mode.turn_scenario
            )
            if policy is not None:
                if not scenario.matches_prefix(turn):
                    raise ValueError("turn does not match the game mode turn scenario")
            elif not scenario.validate_turn(turn):
                raise ValueError("turn does not match the game mode turn scenario")
        shape = result.board_state.board.shape
        for action in turn.actions:
            if isinstance(action, MoveAction):
                source = action.from_square.index(shape.files)
                target = action.to_square.index(shape.files)
                piece = result.board_state.piece_at(source)
                if piece is None:
                    raise ValueError("cannot move from an empty square")
                if piece.side is not turn.side:
                    raise ValueError("cannot move another side's piece")
                castle = _decode_castling(action, result, mode)
                captured = None
                if castle is not None:
                    _apply_castling(result, castle)
                    target = castle.king_to.index(shape.files)
                    piece = result.board_state.piece_at(target)
                else:
                    captured = result.board_state.piece_at(target)
                    if captured is not None and captured.side is turn.side:
                        raise ValueError("cannot capture a friendly piece")
                    if captured is not None and captured.side is PieceSide.NEUTRAL:
                        raise ValueError("cannot capture a neutral blocker")
                    if action.captured_squares:
                        if captured is not None:
                            raise ValueError("capture sequence must land on an empty square")
                        captured_indices = [
                            square.index(shape.files) for square in action.captured_squares
                        ]
                        if len(set(captured_indices)) != len(captured_indices):
                            raise ValueError("capture sequence cannot capture a piece twice")
                        for captured_index in captured_indices:
                            victim = result.board_state.piece_at(captured_index)
                            if (
                                victim is None
                                or victim.side is turn.side
                                or victim.side is PieceSide.NEUTRAL
                            ):
                                raise ValueError("invalid capture sequence")
                            if result.hands is not None:
                                result.hands.add(turn.side, _hand_piece(victim, mode))
                            result.board_state.cells[captured_index] = None
                    if (
                        not action.captured_squares
                        and piece.piece_type.name == "pawn"
                        and captured is None
                        and action.from_square.file != action.to_square.file
                        and action.to_square == result.extras.get("en_passant")
                    ):
                        captured_index = target - shape.files * turn.side.forward_delta()
                        captured = result.board_state.piece_at(captured_index)
                        if (
                            captured is None
                            or captured.piece_type.name != "pawn"
                            or captured.side is turn.side
                            or captured.side is PieceSide.NEUTRAL
                        ):
                            raise ValueError("invalid en passant capture")
                        result.board_state.cells[captured_index] = None
                    if captured is not None and result.hands is not None:
                        captured = _hand_piece(captured, mode)
                        result.hands.add(turn.side, captured)
                    result.board_state.cells[source] = None
                    if action.promotion_choice is not None:
                        original_name = piece.piece_type.name
                        piece = deepcopy(piece)
                        piece.piece_type = action.promotion_choice
                        flags = dict(piece.state or {})
                        flags["promoted_from"] = original_name
                        piece.state = flags
                    result.board_state.cells[target] = piece
                rights = set(result.extras.get("castling_rights", ()))
                if piece is not None and piece.piece_type.name == "king":
                    rights -= {"K", "Q"} if turn.side is PieceSide.WHITE else {"k", "q"}
                if piece is not None and piece.piece_type.name == "rook":
                    rights.discard(_ROOK_HOME_RIGHTS.get(source, ""))
                if castle is not None:
                    rights.discard(
                        _ROOK_HOME_RIGHTS.get(castle.rook_from.index(shape.files), "")
                    )
                if captured is not None and captured.piece_type.name == "rook":
                    rights.discard(_ROOK_HOME_RIGHTS.get(target, ""))
                result.extras["castling_rights"] = rights
                result.extras["en_passant"] = (
                    Square(
                        action.from_square.file,
                        (action.from_square.rank + action.to_square.rank) // 2,
                    )
                    if (
                        castle is None
                        and piece is not None
                        and piece.piece_type.name == "pawn"
                        and abs(action.to_square.rank - action.from_square.rank) == 2
                    )
                    else None
                )
                if mode is not None and castle is None and piece is not None:
                    definition = mode.pieces.get(piece.piece_type)
                    if definition.transforms_on_move is not None:
                        context = _TransformContext(
                            action.to_square,
                            len(result.history.actions),
                            len(result.history.actions),
                        )
                        transformed = deepcopy(result.board_state.cells[target])
                        transformed.piece_type = definition.transforms_on_move.apply(
                            piece.piece_type, context
                        )
                        result.board_state.cells[target] = transformed
            elif isinstance(action, DropAction):
                target = action.to_square.index(shape.files)
                if result.board_state.piece_at(target) is not None:
                    raise ValueError("cannot drop onto an occupied square")
                if result.hands is None:
                    raise ValueError("position does not support pieces in hand")
                if mode is not None and mode.drop_rule is not None:
                    if not mode.drop_rule.can_drop(action.piece_type, target, result):
                        raise ValueError("drop is forbidden by game mode")
                    faces = mode.drop_rule.allowed_faces(action.piece_type)
                    if faces is not None and action.face not in faces:
                        raise ValueError("invalid drop face")
                hand = result.hands.by_side.get(turn.side, [])
                index = next(
                    (
                        index
                        for index, piece in enumerate(hand)
                        if piece.piece_type == action.piece_type
                    ),
                    None,
                )
                if index is None:
                    raise ValueError("piece is not available in hand")
                dropped = hand.pop(index)
                if action.face is not None:
                    dropped.piece_type = PieceTypeId(action.face)
                result.board_state.cells[target] = dropped
            elif isinstance(action, PlaceAction):
                from chess_core.core.rules_strategy import apply_place_action

                apply_place_action(result, turn, action)
            elif isinstance(action, TransformAction):
                target = action.square.index(shape.files)
                piece = result.board_state.piece_at(target)
                if piece is None:
                    raise ValueError("cannot transform an empty square")
                piece = deepcopy(piece)
                piece.piece_type = action.new_type
                result.board_state.cells[target] = piece
            elif isinstance(action, PlaceBlockerAction):
                target = action.square.index(shape.files)
                if result.board_state.piece_at(target) is not None:
                    raise ValueError("cannot place blocker onto an occupied square")
                for index, occupant in result.board_state.cells.items():
                    if occupant is not None and occupant.side is PieceSide.NEUTRAL:
                        result.board_state.cells[index] = None
                result.board_state.cells[target] = Piece(
                    PieceTypeId("blocker"), PieceSide.NEUTRAL
                )
            elif not isinstance(action, PassAction):
                raise TypeError(f"unsupported action: {type(action).__name__}")
            turn_actions.append(action)
            if mode is not None:
                for transition in mode.transitions:
                    transitioned = transition.apply_after_action(action, result)
                    if not isinstance(transitioned, GameState):
                        raise TypeError("state transition must return GameState")
                    result = transitioned

        if validate_scenario and policy is not None:
            end = policy.should_end_turn(result, turn.actions)
            required = policy.scenario_for(self).required_action_count()
            if len(turn.actions) >= required:
                end = True
            if not end:
                raise ValueError("turn does not match the game mode turn scenario")
        if record_history:
            result.history.actions.extend(turn_actions)
            result.history.metadata.append({"turn_side": turn.side.name})
            result.extras["committed_turns"] = len(result.history.metadata)
        if switch_side:
            result.side_to_move = (
                mode.turn_order.next_side(result.side_to_move)
                if mode is not None
                else result.side_to_move.opponent()
            )
        return result


@dataclass(frozen=True, slots=True)
class _TransformContext:
    _square: Square
    _move_count: int
    _ply: int

    def square(self) -> Square:
        return self._square

    def move_count_for_piece(self) -> int:
        return self._move_count

    def game_ply(self) -> int:
        return self._ply


def _decode_castling(action: MoveAction, state: GameState, mode: object) -> CastlingPath | None:
    rule = getattr(mode, "castling_rule", None) if mode is not None else None
    if rule is None:
        return None
    return rule.decode(action, state)


def _apply_castling(state: GameState, path: CastlingPath) -> None:
    files = state.board_state.board.shape.files
    king_from = path.king_from.index(files)
    rook_from = path.rook_from.index(files)
    king_to = path.king_to.index(files)
    rook_to = path.rook_to.index(files)
    king = state.board_state.piece_at(king_from)
    rook = state.board_state.piece_at(rook_from)
    if king is None or king.piece_type.name != "king":
        raise ValueError("invalid castling king")
    if rook is None or rook.piece_type.name != "rook" or rook.side is not king.side:
        raise ValueError("invalid castling rook")
    state.board_state.cells[king_from] = None
    state.board_state.cells[rook_from] = None
    state.board_state.cells[king_to] = king
    state.board_state.cells[rook_to] = rook


def _clone_piece(piece: Piece) -> Piece:
    """Copy mutable per-piece state while sharing immutable identifiers."""
    return Piece(piece.piece_type, piece.side, deepcopy(piece.state))


def _hand_piece(piece: Piece, mode: object) -> Piece:
    captured = deepcopy(piece)
    if captured.state and captured.state.get("promoted_from"):
        return captured
    catalog = getattr(mode, "pieces", None)
    if catalog is None:
        return captured
    try:
        demotes_to = catalog.get(captured.piece_type).demotes_to
    except KeyError:
        return captured
    if demotes_to:
        flags = dict(captured.state or {})
        flags["promoted_from"] = demotes_to
        captured.state = flags
    return captured

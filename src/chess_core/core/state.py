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
    PlaceBlockerAction,
    TransformAction,
    Turn,
)
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import CaptureSink


@dataclass
class BoardState:
    board: Board
    cells: dict[int, Piece | None]

    def piece_at(self, square_index: int) -> Piece | None:
        if not 0 <= square_index < self.board.shape.cell_count:
            raise ValueError("square_index is outside board cells")
        return self.cells.get(square_index)


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
        self.by_side.setdefault(side, []).append(captured)

    def remove_type(self, side: PieceSide, piece_type_name: str) -> Piece | None:
        hand = self.by_side.get(side, [])
        for index, piece in enumerate(hand):
            if piece.piece_type.name == piece_type_name:
                return hand.pop(index)
        return None

    def remove_gift(self, side: PieceSide, gift_id: str) -> Piece | None:
        hand = self.by_side.get(side, [])
        for index, piece in enumerate(hand):
            if piece.state and piece.state.get("gift_id") == gift_id:
                return hand.pop(index)
        return None


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
    repetition_log: tuple[object, ...] = ()

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
            repetition_log=self.repetition_log,
        )

    def apply_turn(
        self, turn: Turn, *, record_history: bool = True, require_complete: bool = True
    ) -> GameState:
        if turn.side is not self.side_to_move:
            raise ValueError("turn side does not match side_to_move")
        if not turn.actions:
            raise ValueError("turn must contain at least one action")

        result = self.clone(include_history=record_history)
        mode = result.extras.get("mode")
        result.extras["outbound_gifts"] = []
        turn_actions: list[Action] = []
        if (
            require_complete
            and mode is not None
            and not mode.turn_scenario.validate_turn(turn)
        ):
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
                if _uses_stack_covers(mode):
                    _apply_stack_move(result, source, target, piece)
                    turn_actions.append(action)
                    if mode is not None:
                        for transition in mode.transitions:
                            transitioned = transition.apply_after_action(action, result)
                            if not isinstance(transitioned, GameState):
                                raise TypeError("state transition must return GameState")
                            result = transitioned
                    continue
                captured = result.board_state.piece_at(target)
                if _is_chess960_castle(piece, captured, result.extras):
                    _apply_chess960_castle(result, action, piece, captured, shape)
                    turn_actions.append(action)
                    if mode is not None:
                        for transition in mode.transitions:
                            transitioned = transition.apply_after_action(action, result)
                            if not isinstance(transitioned, GameState):
                                raise TypeError("state transition must return GameState")
                            result = transitioned
                    continue
                if action.jumped:
                    if captured is not None:
                        raise ValueError("jump landing must be empty")
                    for jumped_square in action.jumped:
                        jumped_index = jumped_square.index(shape.files)
                        victim = result.board_state.piece_at(jumped_index)
                        if (
                            victim is None
                            or victim.side is turn.side
                            or victim.side is PieceSide.NEUTRAL
                        ):
                            raise ValueError("invalid jump capture")
                        _deposit_capture(result, turn.side, victim, mode)
                        result.board_state.cells[jumped_index] = None
                elif captured is not None and captured.side is turn.side:
                    raise ValueError("cannot capture a friendly piece")
                if captured is not None and captured.side is PieceSide.NEUTRAL:
                    raise ValueError("cannot capture a neutral blocker")
                if (
                    piece.piece_type.name == "pawn"
                    and captured is None
                    and action.from_square.file != action.to_square.file
                    and action.to_square == result.extras.get("en_passant")
                ):
                    captured_index = target - shape.files if turn.side is PieceSide.WHITE else target + shape.files
                    captured = result.board_state.piece_at(captured_index)
                    if (
                        captured is None
                        or captured.piece_type.name != "pawn"
                        or captured.side is turn.side
                        or captured.side is PieceSide.NEUTRAL
                    ):
                        raise ValueError("invalid en passant capture")
                    result.board_state.cells[captured_index] = None
                if captured is not None:
                    _deposit_capture(result, turn.side, captured, mode)
                result.board_state.cells[source] = None
                if action.promotion_choice is not None:
                    piece = deepcopy(piece)
                    original_name = piece.piece_type.name
                    piece.piece_type = action.promotion_choice
                    piece.state = dict(piece.state or {})
                    piece.state["promoted_from"] = original_name
                result.board_state.cells[target] = piece
                if piece.piece_type.name == "king" and abs(action.to_square.file - action.from_square.file) == 2:
                    rook_from_file = shape.files - 1 if action.to_square.file > action.from_square.file else 0
                    rook_to_file = action.to_square.file - 1 if rook_from_file else action.to_square.file + 1
                    rook_from = action.from_square.rank * shape.files + rook_from_file
                    rook_to = action.from_square.rank * shape.files + rook_to_file
                    rook = result.board_state.piece_at(rook_from)
                    if rook is None or rook.piece_type.name != "rook" or rook.side is not turn.side:
                        raise ValueError("invalid castling rook")
                    result.board_state.cells[rook_from] = None
                    result.board_state.cells[rook_to] = rook
                rights = set(result.extras.get("castling_rights", ()))
                rook_files = result.extras.get("castling_rooks")
                if piece.piece_type.name == "king":
                    rights -= {"K", "Q"} if turn.side is PieceSide.WHITE else {"k", "q"}
                if piece.piece_type.name == "rook":
                    rights.discard(_rook_right_for_square(source, shape.files, rook_files))
                if captured is not None and captured.piece_type.name == "rook":
                    rights.discard(_rook_right_for_square(target, shape.files, rook_files))
                result.extras["castling_rights"] = rights
                result.extras["en_passant"] = (
                    Square(action.from_square.file, (action.from_square.rank + action.to_square.rank) // 2)
                    if piece.piece_type.name == "pawn"
                    and abs(action.to_square.rank - action.from_square.rank) == 2
                    else None
                )
                if mode is not None:
                    definition = mode.pieces.get(piece.piece_type)
                    if definition.transforms_on_move is not None:
                        context = _TransformContext(action.to_square, len(result.history.actions), len(result.history.actions))
                        transformed = deepcopy(result.board_state.cells[target])
                        transformed.piece_type = definition.transforms_on_move.apply(piece.piece_type, context)
                        result.board_state.cells[target] = transformed
            elif isinstance(action, DropAction):
                target = action.to_square.index(shape.files)
                covering = _uses_stack_covers(mode)
                if result.board_state.piece_at(target) is not None and not covering:
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
                if covering:
                    _stack_push(result, target, dropped)
                else:
                    result.board_state.cells[target] = dropped
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

        if record_history:
            result.history.actions.extend(turn_actions)
            result.history.metadata.append({"turn_side": turn.side.name})
        result.side_to_move = (
            mode.turn_order.next_side(result.side_to_move)
            if mode is not None
            else PieceSide.BLACK
            if result.side_to_move is PieceSide.WHITE
            else PieceSide.WHITE
        )
        from chess_core.core.repetition import position_key

        before = position_key(self)
        if self.repetition_log and self.repetition_log[-1] == before:
            prior = self.repetition_log
        elif self.repetition_log:
            prior = (*self.repetition_log, before)
        else:
            prior = (before,)
        result.repetition_log = (*prior, position_key(result))
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


def _clone_piece(piece: Piece) -> Piece:
    """Copy mutable per-piece state while sharing immutable identifiers."""
    return Piece(piece.piece_type, piece.side, deepcopy(piece.state))


def _uses_stack_covers(mode: object) -> bool:
    extras = getattr(mode, "initial_extras", None)
    return bool(isinstance(extras, dict) and extras.get("stack_covers"))


def _cover_sizes(mode: object) -> dict[str, int]:
    extras = getattr(mode, "initial_extras", None)
    raw = extras.get("cover_sizes") if isinstance(extras, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {str(name): int(value) for name, value in raw.items()}


def _cell_stack(state: GameState, index: int) -> list[Piece]:
    stacks = state.extras.setdefault("stacks", {})
    if not isinstance(stacks, dict):
        raise TypeError("extras['stacks'] must be a dict")
    if index not in stacks:
        occupant = state.board_state.piece_at(index)
        stacks[index] = [_clone_piece(occupant)] if occupant is not None else []
    return stacks[index]


def _sync_stack_cell(state: GameState, index: int) -> None:
    stack = _cell_stack(state, index)
    state.board_state.cells[index] = _clone_piece(stack[-1]) if stack else None


def _can_cover_piece(moving: Piece, occupant: Piece | None, sizes: dict[str, int]) -> bool:
    if occupant is None:
        return True
    return sizes.get(moving.piece_type.name, 0) > sizes.get(occupant.piece_type.name, 0)


def _stack_push(state: GameState, index: int, piece: Piece) -> None:
    mode = state.extras.get("mode")
    sizes = _cover_sizes(mode)
    stack = _cell_stack(state, index)
    top = stack[-1] if stack else None
    if not _can_cover_piece(piece, top, sizes):
        raise ValueError("cannot cover this piece")
    stack.append(_clone_piece(piece))
    _sync_stack_cell(state, index)


def _apply_stack_move(state: GameState, source: int, target: int, piece: Piece) -> None:
    if source == target:
        raise ValueError("cannot move to the same square")
    from_stack = _cell_stack(state, source)
    if not from_stack or from_stack[-1].side is not piece.side:
        raise ValueError("cannot move from this square")
    moving = from_stack.pop()
    _sync_stack_cell(state, source)
    _stack_push(state, target, moving)


def _deposit_capture(state: GameState, mover: PieceSide, captured: Piece, mode: object) -> None:
    piece = deepcopy(captured)
    drop_rule = getattr(mode, "drop_rule", None) if mode is not None else None
    captured_as = getattr(drop_rule, "captured_as", None)
    if callable(captured_as):
        piece = captured_as(piece)
    sink = _capture_sink(mode, state)
    if sink is CaptureSink.DESTROY:
        return
    if sink is CaptureSink.PARTNER_OUTBOUND:
        gifts = list(state.extras.get("outbound_gifts") or [])
        gifts.append(piece)
        state.extras["outbound_gifts"] = gifts
        return
    if state.hands is None:
        return
    state.hands.add(mover, piece)


def _capture_sink(mode: object, state: GameState) -> CaptureSink:
    configured = getattr(mode, "capture_sink", None) if mode is not None else None
    if configured is not None:
        return configured
    if state.hands is not None:
        return CaptureSink.MOVER_HAND
    return CaptureSink.DESTROY


def _is_chess960_castle(piece: Piece, captured: Piece | None, extras: dict[str, Any]) -> bool:
    return (
        piece.piece_type.name == "king"
        and captured is not None
        and captured.piece_type.name == "rook"
        and captured.side is piece.side
        and isinstance(extras.get("castling_rooks"), dict)
    )


def _apply_chess960_castle(
    state: GameState,
    action: MoveAction,
    king: Piece,
    rook: Piece,
    shape,
) -> None:
    kingside = action.to_square.file > action.from_square.file
    king_file = 6 if kingside else 2
    rook_file = 5 if kingside else 3
    source = action.from_square.index(shape.files)
    target = action.to_square.index(shape.files)
    state.board_state.cells[source] = None
    state.board_state.cells[target] = None
    state.board_state.cells[action.from_square.rank * shape.files + king_file] = king
    state.board_state.cells[action.from_square.rank * shape.files + rook_file] = rook
    rights = set(state.extras.get("castling_rights", ()))
    rights -= {"K", "Q"} if king.side is PieceSide.WHITE else {"k", "q"}
    state.extras["castling_rights"] = rights
    state.extras["en_passant"] = None


def _rook_right_for_square(index: int, files: int, rook_files: object) -> str:
    file = index % files
    rank_start = index // files == 0
    if isinstance(rook_files, dict):
        if rank_start:
            if file == rook_files.get("K"):
                return "K"
            if file == rook_files.get("Q"):
                return "Q"
        else:
            if file == rook_files.get("k"):
                return "k"
            if file == rook_files.get("q"):
                return "q"
        return ""
    return {0: "Q", 7: "K", 56: "q", 63: "k"}.get(index, "")

"""Multi-board / multi-role match controllers (application layer)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from uuid import uuid4

from chess_core.app.clock import ClockSnapshot, GameClockService, MonotonicClock
from chess_core.app.seats import (
    BOARD_A,
    BOARD_B,
    BOARD_MAIN,
    SeatDuty,
    SeatSpec,
    partner_board,
    partner_side,
    seats_for_match_kind,
)
from chess_core.core.gamemode import GameMode
from chess_core.core.move import DropAction, MoveAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide
from chess_core.core.state import GameState
from chess_core.core.time_control import TimeControlConfig


class MatchKind(Enum):
    SINGLE = auto()
    BUGHOUSE = auto()
    HAND_AND_BRAIN = auto()


class MatchPhase(Enum):
    LOBBY = auto()
    PLAYING = auto()
    ENDED = auto()


def match_kind_from_mode(mode: GameMode | None) -> MatchKind:
    raw = "single"
    if mode is not None:
        raw = str(mode.initial_extras.get("match_kind", "single"))
    mapping = {
        "bughouse": MatchKind.BUGHOUSE,
        "hand_and_brain": MatchKind.HAND_AND_BRAIN,
    }
    return mapping.get(raw, MatchKind.SINGLE)


def match_kind_key(kind: MatchKind) -> str:
    return {
        MatchKind.SINGLE: "single",
        MatchKind.BUGHOUSE: "bughouse",
        MatchKind.HAND_AND_BRAIN: "hand_and_brain",
    }[kind]


@dataclass
class MatchPly:
    board_id: str
    turn: Turn
    gift_ids: tuple[str, ...]
    partner_board_id: str | None
    partner_side: PieceSide | None


@dataclass
class MatchResult:
    winner_team: str | None
    reason: str
    board_id: str | None = None


@dataclass
class MatchState:
    kind: MatchKind
    phase: MatchPhase
    boards: dict[str, GameState]
    chosen_piece_type: str | None = None
    result: MatchResult | None = None
    plies: list[MatchPly] = field(default_factory=list)

    @property
    def primary_state(self) -> GameState:
        if BOARD_MAIN in self.boards:
            return self.boards[BOARD_MAIN]
        return self.boards[BOARD_A]


class MatchController:
    """Authoritative match rules on top of one or two GameState boards."""

    def __init__(
        self,
        mode: GameMode,
        initial_state: GameState,
        *,
        clock: MonotonicClock,
        time_control: TimeControlConfig | None = None,
    ) -> None:
        self.mode = mode
        self.kind = match_kind_from_mode(mode)
        self.player_seats = seats_for_match_kind(match_kind_key(self.kind))
        self._generator = MoveGenerator(mode)
        self._clock = clock
        if self.kind is MatchKind.BUGHOUSE:
            partner = initial_state.clone()
            self.state = MatchState(
                kind=self.kind,
                phase=MatchPhase.LOBBY,
                boards={BOARD_A: initial_state.clone(), BOARD_B: partner},
            )
            self._clocks = {
                BOARD_A: GameClockService(time_control, clock) if time_control else None,
                BOARD_B: GameClockService(time_control, clock) if time_control else None,
            }
            self._turn_started = {BOARD_A: clock.now_ms(), BOARD_B: clock.now_ms()}
        else:
            self.state = MatchState(
                kind=self.kind,
                phase=MatchPhase.LOBBY,
                boards={BOARD_MAIN: initial_state.clone()},
            )
            self._clocks = {
                BOARD_MAIN: GameClockService(time_control, clock) if time_control else None
            }
            self._turn_started = {BOARD_MAIN: clock.now_ms()}
        self._board_snapshots: dict[str, list[GameState]] = {
            board_id: [board.clone(include_history=False)]
            for board_id, board in self.state.boards.items()
        }

    def start(self) -> None:
        if self.state.phase is not MatchPhase.LOBBY:
            raise RuntimeError("match already started")
        self.state.phase = MatchPhase.PLAYING
        now = self._clock.now_ms()
        for board_id in self._turn_started:
            self._turn_started[board_id] = now

    def board(self, board_id: str) -> GameState:
        try:
            return self.state.boards[board_id]
        except KeyError as exc:
            raise ValueError(f"unknown board: {board_id}") from exc

    def clock_snapshots(self) -> dict[str, ClockSnapshot]:
        return {
            board_id: service.snapshot()
            for board_id, service in self._clocks.items()
            if service is not None
        }

    def legal_actions(self, board_id: str, *, chosen_type: str | None = None) -> list:
        state = self.board(board_id)
        legal = self._generator.generate_legal(state)
        if chosen_type is None:
            return legal
        return [action for action in legal if _action_piece_type(action, state) == chosen_type]

    def brain_select(self, spec: SeatSpec, piece_type: str) -> None:
        self._require_playing()
        if spec.duty is not SeatDuty.BRAIN:
            raise PermissionError("only Brain can select a piece type")
        board = self.board(spec.board_id)
        if board.side_to_move is not spec.side:
            raise PermissionError("not this team's turn")
        if not any(
            _action_piece_type(action, board) == piece_type
            for action in self._generator.generate_legal(board)
        ):
            raise ValueError("selected piece type has no legal moves")
        self.state.chosen_piece_type = piece_type
        board.extras["chosen_piece_type"] = piece_type

    def apply_turn(self, spec: SeatSpec, turn: Turn, *, board_id: str | None = None) -> GameState:
        self._require_playing()
        target = board_id or spec.board_id
        if spec.board_id != target:
            raise PermissionError("client cannot play on another board")
        if turn.side is not spec.side:
            raise PermissionError("client cannot submit the other side's turn")
        board = self.board(target)
        if turn.side is not board.side_to_move:
            raise ValueError("turn side does not match position")
        if spec.duty is SeatDuty.BRAIN:
            raise PermissionError("Brain cannot submit a move")
        if spec.duty is SeatDuty.HAND:
            if self.state.chosen_piece_type is None:
                raise PermissionError("Hand cannot move before Brain selects a type")
            first = turn.actions[0] if turn.actions else None
            if _action_piece_type(first, board) != self.state.chosen_piece_type:
                raise ValueError("move does not match Brain's piece type")
        elif spec.duty is not SeatDuty.MOVER:
            raise PermissionError("this seat cannot submit a turn")
        self._validate_turn(board, turn)
        think_ms = max(0, self._clock.now_ms() - self._turn_started[target])
        next_state = board.apply_turn(turn)
        gifts = list(next_state.extras.get("outbound_gifts") or [])
        next_state.extras["outbound_gifts"] = []
        next_state.extras.pop("chosen_piece_type", None)
        gift_ids = self._deliver_gifts(target, turn.side, gifts)
        self.state.boards[target] = next_state
        self._board_snapshots[target].append(next_state.clone(include_history=False))
        self.state.plies.append(
            MatchPly(
                board_id=target,
                turn=turn,
                gift_ids=tuple(gift_ids),
                partner_board_id=partner_board(target) if self.kind is MatchKind.BUGHOUSE else None,
                partner_side=partner_side(turn.side) if self.kind is MatchKind.BUGHOUSE else None,
            )
        )
        clock = self._clocks.get(target)
        if clock is not None:
            charged = 0 if not clock.has_started else think_ms
            clock.on_move_committed(turn.side, charged)
        self._turn_started[target] = self._clock.now_ms()
        self.state.chosen_piece_type = None
        self._check_end(target)
        return next_state.clone()

    def can_undo_last_on(self, board_id: str) -> bool:
        ply = self._last_ply(board_id)
        if ply is None:
            return False
        if not ply.gift_ids:
            return True
        if ply.partner_board_id is None or ply.partner_side is None:
            return True
        partner = self.board(ply.partner_board_id)
        if partner.hands is None:
            return False
        for gift_id in ply.gift_ids:
            if not any(
                piece.state and piece.state.get("gift_id") == gift_id
                for piece in partner.hands.by_side.get(ply.partner_side, ())
            ):
                return False
        return True

    def undo_last_on(self, board_id: str) -> GameState:
        if not self.can_undo_last_on(board_id):
            raise ValueError("cannot undo: partner already used the captured piece")
        ply = self._last_ply(board_id)
        if ply is None:
            raise ValueError("not enough moves to undo")
        snapshots = self._board_snapshots[board_id]
        if len(snapshots) <= 1:
            raise ValueError("not enough moves to undo")
        snapshots.pop()
        restored = snapshots[-1].clone()
        restored.extras.pop("chosen_piece_type", None)
        self.state.boards[board_id] = restored
        if ply.partner_board_id is not None and ply.partner_side is not None:
            partner = self.board(ply.partner_board_id)
            if partner.hands is not None:
                for gift_id in ply.gift_ids:
                    partner.hands.remove_gift(ply.partner_side, gift_id)
        index = max(
            index
            for index, item in enumerate(self.state.plies)
            if item.board_id == board_id
        )
        self.state.plies.pop(index)
        self.state.chosen_piece_type = None
        clock = self._clocks.get(board_id)
        if clock is not None:
            clock.on_undo()
        self._turn_started[board_id] = self._clock.now_ms()
        return restored.clone()

    def _last_ply(self, board_id: str) -> MatchPly | None:
        for ply in reversed(self.state.plies):
            if ply.board_id == board_id:
                return ply
        return None

    def _deliver_gifts(
        self, from_board: str, mover: PieceSide, gifts: list[Piece]
    ) -> list[str]:
        if self.kind is not MatchKind.BUGHOUSE or not gifts:
            return []
        other = partner_board(from_board)
        receiver = partner_side(mover)
        partner = self.board(other)
        if partner.hands is None:
            partner.hands = type(self.board(from_board).hands)()
        ids: list[str] = []
        for gift in gifts:
            gift_id = uuid4().hex
            tagged = Piece(gift.piece_type, receiver, dict(gift.state or {}))
            tagged.state = dict(tagged.state or {})
            tagged.state["gift_id"] = gift_id
            partner.hands.add(receiver, tagged)
            ids.append(gift_id)
        return ids

    def _validate_turn(self, board: GameState, turn: Turn) -> None:
        legal = self._generator.generate_legal(board)
        if self.state.chosen_piece_type is not None:
            legal = [
                action
                for action in legal
                if _action_piece_type(action, board) == self.state.chosen_piece_type
            ]
        if not turn.actions:
            raise ValueError("turn has no actions")
        first = turn.actions[0]
        if first not in legal:
            raise ValueError("turn is not legal")

    def _check_end(self, board_id: str) -> None:
        board = self.board(board_id)
        if self._generator.is_checkmate(board):
            loser = board.side_to_move
            self._end(board_id, loser, "checkmate")
            return
        if self._generator.is_stalemate(board):
            self._end(board_id, board.side_to_move, "stalemate")
            return
        clock = self._clocks.get(board_id)
        if clock is None:
            return
        snap = clock.snapshot()
        if snap.white_remaining_ms <= 0:
            self._end(board_id, PieceSide.WHITE, "flag")
        elif snap.black_remaining_ms <= 0:
            self._end(board_id, PieceSide.BLACK, "flag")

    def _end(self, board_id: str, loser: PieceSide, reason: str) -> None:
        self.state.phase = MatchPhase.ENDED
        if self.kind is MatchKind.BUGHOUSE:
            mapping = {
                (BOARD_A, PieceSide.WHITE): "team_light",
                (BOARD_B, PieceSide.BLACK): "team_light",
                (BOARD_A, PieceSide.BLACK): "team_dark",
                (BOARD_B, PieceSide.WHITE): "team_dark",
            }
            loser_team = mapping[(board_id, loser)]
            winner = "team_dark" if loser_team == "team_light" else "team_light"
        else:
            winner = "black" if loser is PieceSide.WHITE else "white"
        self.state.result = MatchResult(winner_team=winner, reason=reason, board_id=board_id)

    def _require_playing(self) -> None:
        if self.state.phase is MatchPhase.ENDED:
            raise PermissionError("match has ended")
        if self.state.phase is not MatchPhase.PLAYING:
            raise PermissionError("match has not started")


def _action_piece_type(action: object, state: GameState) -> str | None:
    if isinstance(action, DropAction):
        return action.piece_type.name
    if isinstance(action, MoveAction):
        piece = state.board_state.piece_at(
            action.from_square.index(state.board_state.board.shape.files)
        )
        return None if piece is None else piece.piece_type.name
    return None


def seat_allows_undo_response(spec: SeatSpec | None, requester: SeatSpec) -> bool:
    if spec is None:
        return False
    if spec.seat_id == requester.seat_id:
        return False
    if spec.board_id != requester.board_id:
        return False
    if spec.side is requester.side:
        return False
    if requester.duty is SeatDuty.HAND and spec.duty is not SeatDuty.HAND:
        return False
    return True

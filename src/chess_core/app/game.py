"""Local game application service."""

from __future__ import annotations

from enum import Enum, auto

from chess_core.app.game_record import GameRecord
from chess_core.core.gamemode import GameMode
from chess_core.core.move import MoveAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import NotationStyle, format_turn
from chess_core.core.state import GameState


class GameStatus(Enum):
    ACTIVE = auto()
    CHECK = auto()
    CHECKMATE = auto()
    STALEMATE = auto()


class LocalGameService:
    def __init__(
        self,
        mode: GameMode,
        initial_state: GameState | None = None,
        *,
        notation_style: NotationStyle = NotationStyle.PIECE_SQUARE,
    ) -> None:
        self.mode = mode
        self._notation_style = notation_style
        self._record = GameRecord.from_mode(mode, initial_state)
        self._generator = MoveGenerator(mode)
        self._revision = 0
        self._selected_square: int | None = None
        self._selected_moves: tuple[MoveAction, ...] = ()
        self._status_cache: tuple[int, GameStatus] | None = None

    @property
    def state(self) -> GameState:
        return self._record.current_view_state()

    @property
    def record(self) -> GameRecord:
        return self._record

    @property
    def is_live(self) -> bool:
        return self._record.is_live

    def legal_moves(self) -> list[MoveAction]:
        if not self.is_live:
            return []
        return [
            action
            for action in self._generator.generate_legal(self.state)
            if isinstance(action, MoveAction)
        ]

    def legal_moves_for_square(self, square_index: int) -> tuple[MoveAction, ...]:
        if not self.is_live:
            self._selected_square = None
            self._selected_moves = ()
            return ()
        self._selected_square = square_index
        self._selected_moves = tuple(
            action
            for action in self._generator.generate_legal_for_square(
                self.state, square_index
            )
            if isinstance(action, MoveAction)
        )
        return self._selected_moves

    @property
    def selected_moves(self) -> tuple[MoveAction, ...]:
        return self._selected_moves

    def play(self, move: MoveAction) -> GameState:
        if move not in self.legal_moves():
            raise ValueError("move is not legal")
        return self._apply(move)

    def play_selected(self, move: MoveAction) -> GameState:
        shape = self.mode.board.shape
        if (
            self._selected_square != move.from_square.index(shape.files)
            or move not in self._selected_moves
        ):
            raise ValueError("move is not legal for the current selection")
        return self._apply(move)

    def play_turn(self, turn: Turn) -> GameState:
        if not self.is_live:
            raise RuntimeError("cannot play while viewing history")
        return self._apply_turn(turn)

    def _apply(self, move: MoveAction) -> GameState:
        return self._apply_turn(Turn(self.state.side_to_move, [move]))

    def _apply_turn(self, turn: Turn) -> GameState:
        before = self.state
        after = before.apply_turn(turn, record_history=False)
        notation = format_turn(turn, before=before, after=after, style=self._notation_style)
        next_state = self._record.append_turn(turn, notation=notation)
        self._revision += 1
        self._invalidate_caches()
        return next_state

    def undo(self) -> GameState:
        if not self.is_live:
            self._record.go_live()
        self._record.undo_last_turn()
        self._revision += 1
        self._invalidate_caches()
        return self.state

    def can_undo(self) -> bool:
        return self._record.live_revision > 0

    def go_to_revision(self, revision: int) -> GameState:
        return self._record.go_to(revision)

    def go_live(self) -> GameState:
        return self._record.go_live()

    @property
    def move_log(self) -> list[str]:
        return self._record.move_log()

    def load_position(self, state: GameState) -> GameState:
        self._record.reset(state)
        self._revision += 1
        self._invalidate_caches()
        return self.state

    def status(self) -> GameStatus:
        if self._status_cache is not None and self._status_cache[0] == self._revision:
            return self._status_cache[1]
        view = self.state
        in_check = self._generator.is_in_check(view)
        has_legal = self._generator.has_any_legal(view) if self.is_live else True
        result = (
            GameStatus.CHECKMATE
            if in_check and not has_legal
            else GameStatus.STALEMATE
            if not in_check and not has_legal
            else GameStatus.CHECK
            if in_check
            else GameStatus.ACTIVE
        )
        self._status_cache = (self._revision, result)
        return result

    def reset(self) -> GameState:
        self._record.reset()
        self._revision += 1
        self._invalidate_caches()
        return self.state

    def clear_selection(self) -> None:
        self._selected_square = None
        self._selected_moves = ()

    def _invalidate_caches(self) -> None:
        self.clear_selection()
        self._status_cache = None

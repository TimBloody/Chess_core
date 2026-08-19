"""Local game application service."""

from __future__ import annotations

from enum import Enum, auto

from chess_core.app.game_record import GameRecord
from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Action, DropAction, MoveAction, PlaceBlockerAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import NotationStyle, format_turn, parse_fen
from chess_core.core.pgn import export_pgn, parse_pgn, resolve_turn
from chess_core.core.outcome import OutcomeStatus
from chess_core.core.rules import VictoryKind
from chess_core.core.state import GameState
from chess_core.core.turn import StepKind


class GameStatus(Enum):
    ACTIVE = auto()
    CHECK = auto()
    CHECKMATE = auto()
    STALEMATE = auto()
    VARIANT_WIN = auto()
    VARIANT_DRAW = auto()


class LocalGameService:
    def __init__(
        self,
        mode: GameMode,
        initial_state: GameState | None = None,
        *,
        notation_style: NotationStyle = NotationStyle.PIECE_SQUARE,
        allow_temporary_variations: bool = False,
    ) -> None:
        self.mode = mode
        self._notation_style = notation_style
        self._record = GameRecord.from_mode(mode, initial_state)
        self._generator = MoveGenerator(mode)
        self._revision = 0
        self._selected_square: int | None = None
        self._selected_moves: tuple[MoveAction, ...] = ()
        self._selected_drops: tuple[DropAction, ...] = ()
        self._pending_actions: list[Action] = []
        self._selected_hand_type: str | None = None
        self._status_cache: tuple[int, GameStatus] | None = None
        self._allow_temporary_variations = allow_temporary_variations
        self._mainline_record: GameRecord | None = None

    @property
    def state(self) -> GameState:
        return self._record.current_view_state()

    @property
    def record(self) -> GameRecord:
        return self._record

    @property
    def is_live(self) -> bool:
        return self._record.is_live

    @property
    def can_play(self) -> bool:
        return self.is_live or self._allow_temporary_variations

    @property
    def in_variation(self) -> bool:
        return self._mainline_record is not None

    @property
    def pending_move(self) -> MoveAction | None:
        for action in self._pending_actions:
            if isinstance(action, MoveAction):
                return action
        return None

    @property
    def pending_actions(self) -> tuple[Action, ...]:
        return tuple(self._pending_actions)

    def visible_state(self) -> GameState:
        """Board as currently playable, including unfinished turn actions."""
        if self._pending_actions and self.is_live:
            return self._action_state()
        return self.state

    @property
    def waiting_for_blocker(self) -> bool:
        return self._waiting_for_blocker()

    @property
    def selected_hand_type(self) -> str | None:
        return self._selected_hand_type

    def select_hand_piece(self, piece_type_name: str) -> tuple[DropAction, ...]:
        """Select a held piece type or Kyoto drop face; destinations become selected_drops."""
        if not self.can_play or self._waiting_for_blocker():
            self._selected_hand_type = None
            self._selected_drops = ()
            return ()
        if self.state.hands is None:
            raise ValueError("piece is not available in hand")
        if self._selected_hand_type == piece_type_name:
            self.clear_selection()
            return ()
        drops = tuple(
            action
            for action in self._generator.generate_legal_drops(self._action_state())
            if (action.face is not None and action.face == piece_type_name)
            or (action.face is None and action.piece_type.name == piece_type_name)
        )
        if not drops:
            raise ValueError("piece is not available in hand")
        self._selected_square = None
        self._selected_moves = ()
        self._selected_hand_type = piece_type_name
        self._selected_drops = drops
        return self._selected_drops

    def legal_moves(self) -> list[MoveAction]:
        if not self.can_play or self._waiting_for_blocker():
            return []
        return [
            action
            for action in self._generator.generate_legal(self._action_state())
            if isinstance(action, MoveAction)
        ]

    def legal_moves_for_square(self, square_index: int) -> tuple[MoveAction, ...]:
        if not self.can_play or self._waiting_for_blocker():
            self._selected_square = None
            self._selected_moves = ()
            self._selected_drops = ()
            return ()
        self._selected_hand_type = None
        self._selected_square = square_index
        actions = self._generator.generate_legal_for_square(
            self._action_state(), square_index
        )
        self._selected_moves = tuple(
            action for action in actions if isinstance(action, MoveAction)
        )
        self._selected_drops = tuple(
            action for action in actions if isinstance(action, DropAction)
        )
        return self._selected_moves

    def legal_turns(self) -> list[Turn]:
        if not self.can_play:
            return []
        return self.mode.legal_turns(self.state)

    def legal_turn_options(self):
        from chess_core.app.legal_turns import LegalTurnOptions, build_legal_turn_options

        if not self.can_play:
            return LegalTurnOptions(())
        return build_legal_turn_options(
            self.mode,
            self.state,
            self.legal_turns(),
            notation_style=self._notation_style,
        )

    def legal_drops_for_square(self, square_index: int) -> tuple[DropAction, ...]:
        self.legal_moves_for_square(square_index)
        return self._selected_drops

    @property
    def selected_moves(self) -> tuple[MoveAction, ...]:
        return self._selected_moves

    @property
    def selected_drops(self) -> tuple[DropAction, ...]:
        return self._selected_drops

    def legal_blocker_actions(self) -> tuple[PlaceBlockerAction, ...]:
        if not self._waiting_for_blocker() or not self.can_play:
            return ()
        from chess_core.core.blockers import legal_blocker_actions

        probe = self.state.apply_turn(
            Turn(self.state.side_to_move, list(self._pending_actions)),
            record_history=False,
            validate_scenario=False,
            switch_side=False,
        )
        return tuple(legal_blocker_actions(probe))

    def play(self, move: MoveAction) -> GameState:
        legal = self._generator.generate_legal_for_square(
            self._action_state(), move.from_square
        )
        if move not in legal:
            raise ValueError("move is not legal")
        return self._apply_action(move)

    def play_selected(self, move: MoveAction) -> GameState:
        shape = self.mode.board.shape
        if (
            self._selected_square != move.from_square.index(shape.files)
            or move not in self._selected_moves
        ):
            raise ValueError("move is not legal for the current selection")
        return self._apply_action(move)

    def play_drop(self, action: DropAction) -> GameState:
        legal = self._generator.generate_legal_drops(self._action_state())
        if action not in legal:
            raise ValueError("drop is not legal")
        self._selected_hand_type = None
        return self._apply_action(action)

    def play_selected_drop(self, square: Square) -> GameState:
        action = next(
            (drop for drop in self._selected_drops if drop.to_square == square),
            None,
        )
        if action is None:
            raise ValueError("drop is not legal for the current hand selection")
        return self.play_drop(action)

    def play_blocker(self, square: Square) -> GameState:
        if not self._waiting_for_blocker():
            raise ValueError("no pending move for blocker placement")
        action = PlaceBlockerAction(square)
        if action not in self.legal_blocker_actions():
            raise ValueError("blocker placement is not legal")
        return self._apply_action(action)

    def play_turn(self, turn: Turn) -> GameState:
        if not self.can_play:
            raise RuntimeError("cannot play while viewing history")
        signature = (turn.side, tuple(turn.actions))
        legal = any(
            (candidate.side, tuple(candidate.actions)) == signature
            for candidate in self.mode.legal_turns(self.state)
        )
        if not legal:
            raise ValueError("turn is not legal")
        self._pending_actions = []
        return self._apply_turn(turn)

    def _apply_action(self, action: Action) -> GameState:
        actions = [*self._pending_actions, action]
        if self._should_keep_pending(actions):
            self._pending_actions = actions
            self._selected_square = None
            self._selected_moves = ()
            self._selected_drops = ()
            self._status_cache = None
            return self.state
        self._pending_actions = []
        return self._apply_turn(Turn(self.state.side_to_move, actions))

    def _apply_turn(self, turn: Turn) -> GameState:
        self._start_variation_if_needed()
        before = self.state
        after = self.mode.apply_turn(before, turn, record_history=False)
        notation = self.mode.format_turn(
            turn, before=before, after=after, style=self._notation_style
        )
        next_state = self._record.append_turn(turn, notation=notation)
        self._revision += 1
        self._invalidate_caches()
        return next_state

    def undo(self) -> GameState:
        if self._pending_actions:
            self._pending_actions = []
            self._invalidate_caches()
            return self.state
        if not self.is_live:
            self._record.go_live()
        self._record.undo_last_turn()
        self._revision += 1
        self._invalidate_caches()
        return self.state

    def can_undo(self) -> bool:
        return self._pending_actions or self._record.live_revision > 0

    def go_to_revision(self, revision: int) -> GameState:
        self._pending_actions = []
        return self._record.go_to(revision)

    def go_live(self) -> GameState:
        self._pending_actions = []
        return self._record.go_live()

    def return_to_mainline(self) -> GameState:
        if self._mainline_record is None:
            return self.state
        self._record = self._mainline_record
        self._mainline_record = None
        self._record.go_live()
        self._pending_actions = []
        self._revision += 1
        self._invalidate_caches()
        return self.state

    @property
    def move_log(self) -> list[str]:
        return self._record.move_log()

    def load_position(self, state: GameState) -> GameState:
        self._pending_actions = []
        self._mainline_record = None
        self._record.reset(state)
        self._revision += 1
        self._invalidate_caches()
        return self.state

    def export_pgn(self, *, headers: dict[str, str] | None = None, result: str = "*") -> str:
        return export_pgn(
            mode=self.mode,
            initial=self._record.initial,
            notations=[entry.notation for entry in self._record.turns],
            headers=headers,
            result=result,
        )

    def import_pgn(self, text: str) -> GameState:
        pgn = parse_pgn(text)
        initial = self.mode.initial_state()
        fen = pgn.headers.get("FEN")
        if fen:
            initial = parse_fen(fen, self.mode)
        sfen = pgn.headers.get("SFEN")
        if sfen:
            from chess_core.core.sfen import parse_sfen

            initial = parse_sfen(sfen, self.mode)
        self._record = GameRecord.from_mode(self.mode, initial)
        self._mainline_record = None
        state = self._record.live_state()
        for token in pgn.moves:
            turn = resolve_turn(state, token, self._generator)
            after = self.mode.apply_turn(state, turn, record_history=False)
            notation = self.mode.format_turn(
                turn, before=state, after=after, style=self._notation_style
            )
            state = self._record.append_turn(turn, notation=notation)
        self._revision += 1
        self._pending_actions = []
        self._invalidate_caches()
        return self.state

    def status(self) -> GameStatus:
        if self._status_cache is not None and self._status_cache[0] == self._revision:
            return self._status_cache[1]
        if self._pending_actions:
            self._status_cache = (self._revision, GameStatus.ACTIVE)
            return GameStatus.ACTIVE
        view = self.state
        kinds = self.mode.victory_kinds()
        uses_check = self.mode.protects_royal()
        if (
            VictoryKind.KING_CAPTURE in kinds
            and not self._side_has_royal(view, view.side_to_move)
        ):
            result = GameStatus.CHECKMATE
            self._status_cache = (self._revision, result)
            return result
        previous = view.side_to_move.opponent()
        if self._three_check_succeeded(view, previous):
            result = GameStatus.VARIANT_WIN
            self._status_cache = (self._revision, result)
            return result
        if VictoryKind.KING_REACHES_ZONE in kinds and self._royal_try_succeeded(
            view, previous
        ):
            result = GameStatus.VARIANT_WIN
            self._status_cache = (self._revision, result)
            return result
        in_check = self._generator.is_in_check(view) if uses_check else False
        has_legal = self._generator.has_any_legal(view) if self.can_play else True
        if VictoryKind.MATERIAL in kinds or VictoryKind.CUSTOM in kinds:
            outcome = self.mode.outcome(view)
            if outcome.status is OutcomeStatus.WIN:
                result = GameStatus.VARIANT_WIN
            elif outcome.status is OutcomeStatus.DRAW and outcome.reason == "stalemate":
                result = GameStatus.STALEMATE
            elif outcome.status is OutcomeStatus.DRAW:
                result = GameStatus.VARIANT_DRAW
            elif in_check:
                result = GameStatus.CHECK
            else:
                result = GameStatus.ACTIVE
        elif not has_legal and not self.mode.lose_on_no_legal_moves():
            result = GameStatus.VARIANT_WIN
        elif in_check and not has_legal:
            result = GameStatus.CHECKMATE
        elif not in_check and not has_legal:
            result = GameStatus.STALEMATE
        elif in_check:
            result = GameStatus.CHECK
        else:
            result = GameStatus.ACTIVE
        self._status_cache = (self._revision, result)
        return result

    def reset(self) -> GameState:
        self._pending_actions = []
        self._mainline_record = None
        self._record.reset()
        self._revision += 1
        self._invalidate_caches()
        return self.state

    def clear_selection(self) -> None:
        self._selected_square = None
        self._selected_moves = ()
        self._selected_drops = ()
        self._selected_hand_type = None

    def _invalidate_caches(self) -> None:
        self.clear_selection()
        self._status_cache = None

    def _action_state(self) -> GameState:
        if not self._pending_actions:
            return self.state
        return self.state.apply_turn(
            Turn(self.state.side_to_move, list(self._pending_actions)),
            record_history=False,
            validate_scenario=False,
            switch_side=False,
        )

    def _current_scenario(self):
        policy = self.mode.turn_policy
        if policy is not None:
            return policy.scenario_for(self.state)
        return self.mode.turn_scenario

    def _waiting_for_blocker(self) -> bool:
        remaining = self._current_scenario().remaining_steps(self._pending_actions)
        return bool(remaining) and remaining[0].kind is StepKind.PLACE_BLOCKER

    def _should_keep_pending(self, actions: list[Action]) -> bool:
        policy = self.mode.turn_policy
        if policy is None:
            return self._needs_blocker() and len(actions) == 1
        try:
            probe = self.state.apply_turn(
                Turn(self.state.side_to_move, actions),
                record_history=False,
                validate_scenario=False,
                switch_side=False,
            )
        except ValueError:
            return False
        end = policy.should_end_turn(probe, actions)
        required = self._current_scenario().required_action_count()
        if len(actions) >= required:
            end = True
        return not end

    def _needs_blocker(self) -> bool:
        return any(
            step.kind is StepKind.PLACE_BLOCKER
            for step in self._current_scenario().steps
        )

    def _start_variation_if_needed(self) -> None:
        if self.is_live:
            return
        if not self._allow_temporary_variations:
            raise RuntimeError("cannot play while viewing history")
        if self._mainline_record is None:
            self._mainline_record = self._record
        self._record = self._record.branch_from_view()

    def _side_has_royal(self, state: GameState, side: PieceSide) -> bool:
        return any(
            piece.side is side and self.mode.piece_is_royal(piece)
            for _index, piece in state.board_state.iter_occupied()
        )

    def _royal_try_succeeded(self, state: GameState, side: PieceSide) -> bool:
        for condition in self.mode.victory_conditions():
            if condition.kind is not VictoryKind.KING_REACHES_ZONE:
                continue
            if self._royal_in_zone(state, side, condition.target_zone_mask):
                return True
        return False

    def _three_check_succeeded(self, state: GameState, side: PieceSide) -> bool:
        for condition in self.mode.victory_conditions():
            if condition.kind is not VictoryKind.THREE_CHECK:
                continue
            given = state.extras.get("checks_given") or {}
            count = given.get(side.name.lower(), given.get(side, 0))
            threshold = condition.threshold or 3
            if int(count) >= threshold:
                return True
        return False

    def _royal_in_zone(
        self, state: GameState, side: PieceSide, mask: int | None
    ) -> bool:
        shape = self.mode.board.shape
        enemy = side.opponent()
        royals = [
            (index, Square.from_index(index, shape.files, shape.ranks))
            for index, piece in state.board_state.iter_occupied()
            if piece.side is side and self.mode.piece_is_royal(piece)
        ]
        if not royals:
            return False
        if mask is not None:
            return any(
                ((1 << index) & mask)
                and not self._generator.is_square_attacked(state, square, enemy)
                for index, square in royals
            )
        target_rank = side.last_rank(shape.ranks)
        return all(
            square.rank == target_rank
            and not self._generator.is_square_attacked(state, square, enemy)
            for _index, square in royals
        )

"""Local game application service."""

from __future__ import annotations

from datetime import datetime
from enum import Enum, auto

from chess_core.app.game_record import GameRecord, MoveLogLine, transcript_filename
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Action, DropAction, MoveAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import NotationStyle, format_turn
from chess_core.core.piece import PieceSide
from chess_core.core.repetition import is_threefold
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.state import GameState


class GameStatus(Enum):
    ACTIVE = auto()
    CHECK = auto()
    CHECKMATE = auto()
    STALEMATE = auto()
    REPETITION_DRAW = auto()
    MATERIAL_WIN = auto()
    TRY_WIN = auto()
    KING_CAPTURE_WIN = auto()


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

    def legal_moves(self) -> list[MoveAction]:
        if not self.can_play:
            return []
        return [
            action
            for action in self._generator.generate_legal(self.state)
            if isinstance(action, MoveAction)
        ]

    def legal_drops(self) -> list[DropAction]:
        if not self.can_play:
            return []
        return [
            action
            for action in self._generator.generate_legal(self.state)
            if isinstance(action, DropAction)
        ]

    def play_action(self, action: Action) -> GameState:
        if not self.can_play:
            raise RuntimeError("cannot play while viewing history")
        if action not in self._generator.generate_legal(self.state):
            raise ValueError("action is not legal")
        return self._apply_turn(Turn(self.state.side_to_move, [action]))

    def legal_moves_for_square(self, square_index: int) -> tuple[MoveAction, ...]:
        if not self.can_play:
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
        if not self.can_play:
            raise RuntimeError("cannot play while viewing history")
        return self._apply_turn(turn)

    def _apply(self, move: MoveAction) -> GameState:
        return self._apply_turn(Turn(self.state.side_to_move, [move]))

    def _apply_turn(self, turn: Turn) -> GameState:
        self._start_variation_if_needed()
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
        state = self._record.go_to(revision)
        self._revision += 1
        self._invalidate_caches()
        return state

    def go_live(self) -> GameState:
        state = self._record.go_live()
        self._revision += 1
        self._invalidate_caches()
        return state

    def return_to_mainline(self) -> GameState:
        if self._mainline_record is None:
            return self.state
        self._record = self._mainline_record
        self._mainline_record = None
        self._record.go_live()
        self._revision += 1
        self._invalidate_caches()
        return self.state

    @property
    def move_log(self) -> list[str]:
        return self._record.move_log()

    @property
    def move_log_lines(self) -> list[MoveLogLine]:
        return self._record.move_log_lines()

    def live_status(self) -> GameStatus:
        """Terminal result of the playable position, even while browsing history."""
        return evaluate_status(
            self.mode,
            self._generator,
            self._record.live_state(),
            is_live=True,
        )

    def export_transcript(self, *, exported_at: datetime | None = None) -> str:
        live_state = self._record.live_state()
        status = evaluate_status(self.mode, self._generator, live_state, is_live=True)
        result, comment = transcript_result(self.mode, live_state, status)
        return self._record.format_transcript(
            result=result,
            comment=comment,
            exported_at=exported_at,
        )

    def transcript_filename(self, *, exported_at: datetime | None = None) -> str:
        return transcript_filename(self.mode.id, exported_at)

    def load_position(self, state: GameState) -> GameState:
        self._mainline_record = None
        self._record.reset(state)
        self._revision += 1
        self._invalidate_caches()
        return self.state

    def import_pgn(self, text: str, *, game_index: int = 0) -> GameState:
        from chess_core.core.pgn import parse_pgn

        games = parse_pgn(text)
        if not games:
            raise ValueError("PGN is empty")
        if not 0 <= game_index < len(games):
            raise ValueError(f"game index out of range: {game_index}")
        return self.import_pgn_game(games[game_index])

    def import_pgn_game(self, game: "PgnGame") -> GameState:
        from chess_core.app.pgn_replay import move_tokens_from_game, resolve_turn
        from chess_core.core.notation import parse_fen
        from chess_core.core.pgn import PgnGame

        if not isinstance(game, PgnGame):
            raise TypeError("expected PgnGame")
        initial = self.mode.initial_state()
        fen = game.tag("FEN")
        if fen:
            initial = parse_fen(fen, self.mode)
        self._record = GameRecord.from_mode(self.mode, initial)
        self._mainline_record = None
        state = self._record.live_state()
        for token in move_tokens_from_game(game):
            turn = resolve_turn(state, token, self._generator)
            before = state
            after = before.apply_turn(turn, record_history=False)
            notation = format_turn(turn, before=before, after=after, style=self._notation_style)
            state = self._record.append_turn(turn, notation=notation)
        self._revision += 1
        self._invalidate_caches()
        return self.state

    def status(self) -> GameStatus:
        if self._status_cache is not None and self._status_cache[0] == self._revision:
            return self._status_cache[1]
        result = evaluate_status(self.mode, self._generator, self.state, is_live=self.is_live)
        self._status_cache = (self._revision, result)
        return result

    def reset(self) -> GameState:
        self._mainline_record = None
        self._record.reset()
        self._revision += 1
        self._invalidate_caches()
        return self.state

    def _start_variation_if_needed(self) -> None:
        if self.is_live:
            return
        if not self._allow_temporary_variations:
            raise RuntimeError("cannot play while viewing history")
        if self._mainline_record is None:
            self._mainline_record = self._record
        self._record = self._record.branch_from_view()

    def clear_selection(self) -> None:
        self._selected_square = None
        self._selected_moves = ()

    def _invalidate_caches(self) -> None:
        self.clear_selection()
        self._status_cache = None


def evaluate_status(
    mode: GameMode,
    generator: MoveGenerator,
    state: GameState,
    *,
    is_live: bool,
) -> GameStatus:
    conditions = (
        mode.victory if isinstance(mode.victory, tuple) else (mode.victory,)
    )
    kinds = {condition.kind for condition in conditions if isinstance(condition, VictoryCondition)}
    previous = (
        PieceSide.BLACK if state.side_to_move is PieceSide.WHITE else PieceSide.WHITE
    )

    if VictoryKind.KING_CAPTURE in kinds and not _has_royal(mode, state, state.side_to_move):
        return GameStatus.KING_CAPTURE_WIN
    if VictoryKind.KING_REACHES_ZONE in kinds and _royal_reached_zone(
        mode, generator, state, previous, conditions
    ):
        return GameStatus.TRY_WIN
    if VictoryKind.OCCUPY_ZONE in kinds and _occupied_target_zone(mode, state, previous):
        return GameStatus.TRY_WIN
    if VictoryKind.ALIGN in kinds and _has_alignment(mode, state):
        return GameStatus.TRY_WIN
    if VictoryKind.MATERIAL in kinds and VictoryKind.MAJORITY not in kinds:
        white_count = _side_piece_count(state, PieceSide.WHITE)
        black_count = _side_piece_count(state, PieceSide.BLACK)
        threshold = int(mode.initial_extras.get("material_win_threshold", 0) or 0)
        if white_count <= threshold or black_count <= threshold:
            return GameStatus.MATERIAL_WIN

    if is_threefold(state):
        return GameStatus.REPETITION_DRAW

    in_check = mode.checks_enabled and generator.is_in_check(state)
    has_legal = generator.has_any_legal(state) if is_live else True
    if has_legal:
        return GameStatus.CHECK if in_check else GameStatus.ACTIVE
    if VictoryKind.MAJORITY in kinds:
        white_count = _side_piece_count(state, PieceSide.WHITE)
        black_count = _side_piece_count(state, PieceSide.BLACK)
        if white_count == black_count:
            return GameStatus.STALEMATE
        return GameStatus.MATERIAL_WIN
    lose_on_no_moves = any(
        isinstance(condition, VictoryCondition) and condition.lose_on_no_legal_moves
        for condition in conditions
    )
    if in_check:
        return GameStatus.CHECKMATE
    if lose_on_no_moves:
        return GameStatus.STALEMATE
    return GameStatus.MATERIAL_WIN


def transcript_result(mode: GameMode, state: GameState, status: GameStatus) -> tuple[str, str]:
    """PGN-like score and a short termination comment for any mode."""
    previous = PieceSide.BLACK if state.side_to_move is PieceSide.WHITE else PieceSide.WHITE
    if status in (GameStatus.ACTIVE, GameStatus.CHECK):
        return "*", "партия не окончена"
    if status is GameStatus.STALEMATE:
        return "1/2-1/2", "пат / ничья"
    if status is GameStatus.REPETITION_DRAW:
        return "1/2-1/2", "троекратное повторение"
    if status is GameStatus.CHECKMATE:
        return _score_tag(previous), "мат"
    if status is GameStatus.KING_CAPTURE_WIN:
        return _score_tag(previous), "взятие королевской фигуры"
    if status is GameStatus.TRY_WIN:
        aligned = line_winner(mode, state)
        if aligned is not None:
            return _score_tag(aligned), "три в ряд"
        conditions = mode.victory if isinstance(mode.victory, tuple) else (mode.victory,)
        if any(
            isinstance(item, VictoryCondition) and item.kind is VictoryKind.OCCUPY_ZONE
            for item in conditions
        ):
            return _score_tag(previous), "занят угол соперника"
        return _score_tag(previous), "цель достигнута"
    if status is GameStatus.MATERIAL_WIN:
        winner = material_winner(mode, state)
        if winner is None:
            return "1/2-1/2", "ничья по материалу"
        return _score_tag(winner), "материал"
    return "*", "партия не окончена"


def _score_tag(side: PieceSide) -> str:
    return "1-0" if side is PieceSide.WHITE else "0-1"


def _has_royal(mode: GameMode, state: GameState, side: PieceSide) -> bool:
    return any(
        piece is not None
        and piece.side is side
        and piece.piece_type.name == mode.royal_type
        for piece in state.board_state.cells.values()
    )


def _side_piece_count(state: GameState, side: PieceSide) -> int:
    return sum(
        1
        for piece in state.board_state.cells.values()
        if piece is not None and piece.side is side
    )


def material_winner(mode: GameMode, state: GameState) -> PieceSide | None:
    """Who wins a MATERIAL/MAJORITY terminal: giveaway, draughts, or reversi."""
    white = _side_piece_count(state, PieceSide.WHITE)
    black = _side_piece_count(state, PieceSide.BLACK)
    conditions = mode.victory if isinstance(mode.victory, tuple) else (mode.victory,)
    kinds = {condition.kind for condition in conditions if isinstance(condition, VictoryCondition)}
    extras = mode.initial_extras
    if VictoryKind.MAJORITY in kinds:
        if white > black:
            return PieceSide.WHITE
        if black > white:
            return PieceSide.BLACK
        return None
    empty_wins = bool(extras.get("empty_side_wins", True))
    threshold = int(extras.get("material_win_threshold", 0) or 0)
    if white <= threshold and black <= threshold:
        return None
    if white <= threshold:
        return PieceSide.WHITE if empty_wins else PieceSide.BLACK
    if black <= threshold:
        return PieceSide.BLACK if empty_wins else PieceSide.WHITE
    if extras.get("blocked_side_wins", True):
        return state.side_to_move
    return state.side_to_move.opponent()


def line_winner(mode: GameMode, state: GameState) -> PieceSide | None:
    """Who owns a completed alignment; the mover wins if both lined up."""
    white = _side_has_alignment(mode, state, PieceSide.WHITE)
    black = _side_has_alignment(mode, state, PieceSide.BLACK)
    if white and black:
        return PieceSide.BLACK if state.side_to_move is PieceSide.WHITE else PieceSide.WHITE
    if white:
        return PieceSide.WHITE
    if black:
        return PieceSide.BLACK
    return None


def _has_alignment(mode: GameMode, state: GameState) -> bool:
    return line_winner(mode, state) is not None


def _side_has_alignment(mode: GameMode, state: GameState, side: PieceSide) -> bool:
    lines = mode.initial_extras.get("align_lines")
    if not isinstance(lines, (tuple, list)):
        return False
    for line in lines:
        if not isinstance(line, (tuple, list)) or not line:
            continue
        if all(
            (piece := state.board_state.piece_at(int(index))) is not None and piece.side is side
            for index in line
        ):
            return True
    return False


def _occupied_target_zone(mode: GameMode, state: GameState, side: PieceSide) -> bool:
    zones = mode.initial_extras.get("occupy_zones")
    if not isinstance(zones, dict):
        return False
    mask = zones.get(side.name)
    if not isinstance(mask, int):
        return False
    indices = [
        index
        for index, piece in state.board_state.cells.items()
        if piece is not None and piece.side is side
    ]
    if not indices:
        return False
    return all((mask >> index) & 1 for index in indices)


def _royal_reached_zone(
    mode: GameMode,
    generator: MoveGenerator,
    state: GameState,
    side: PieceSide,
    conditions: tuple[VictoryCondition, ...],
) -> bool:
    shape = mode.board.shape
    zone = next(
        (
            condition.target_zone_mask
            for condition in conditions
            if condition.kind is VictoryKind.KING_REACHES_ZONE
        ),
        None,
    )
    last_rank = shape.ranks - 1 if side is PieceSide.WHITE else 0
    for index, piece in state.board_state.cells.items():
        if piece is None or piece.side is not side or piece.piece_type.name != mode.royal_type:
            continue
        if zone is not None:
            if (zone >> index) & 1 == 0:
                continue
        elif index // shape.files != last_rank:
            continue
        from chess_core.core.board import Square

        square = Square.from_index(index, shape.files, shape.ranks)
        enemy = PieceSide.BLACK if side is PieceSide.WHITE else PieceSide.WHITE
        if not generator.is_square_attacked(state, square, enemy):
            return True
    return False

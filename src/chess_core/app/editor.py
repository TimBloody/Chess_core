"""Board editor application service (no PyQt)."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.notation import parse_fen, to_fen
from chess_core.core.pgn import looks_like_pgn
from chess_core.core.sfen import looks_like_sfen, parse_sfen, to_sfen
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import BoardState, GameState, HandsState


class BoardEditorService:
    def __init__(
        self,
        mode: GameMode,
        validator: Callable[[GameState], list[str]] | None = None,
        require_one_king_per_side: bool = False,
    ) -> None:
        self._mode = mode
        self._validator = validator
        self._require_one_king_per_side = require_one_king_per_side
        self._state: GameState | None = None

    @property
    def state(self) -> GameState:
        return self._require_state()

    @property
    def mode(self) -> GameMode:
        return self._mode

    def piece_types_for_palette(self) -> list[str]:
        return [piece_type.id.name for piece_type in self._mode.pieces.all_types()]

    def new_empty_position(self) -> GameState:
        cells = {index: None for index in range(self._mode.board.shape.cell_count)}
        self._state = GameState(
            board_state=BoardState(board=self._mode.board, cells=cells),
            side_to_move=self._mode.starting_side,
            hands=HandsState() if self._mode.drop_rule is not None else None,
            extras={"mode": self._mode},
        )
        return self._state

    def load_start_position(self) -> GameState:
        self._state = self._mode.initial_state()
        return self._state

    def load_state(self, state: GameState) -> GameState:
        if state.board_state.board.shape != self._mode.board.shape:
            raise ValueError("state board shape does not match editor mode")
        loaded = state.clone()
        loaded.extras["mode"] = self._mode
        self._state = loaded
        return self._state

    def clear_board(self) -> None:
        state = self._require_state()
        for index in state.board_state.cells:
            state.board_state.cells[index] = None

    def set_side_to_move(self, side: PieceSide) -> None:
        self._require_state().side_to_move = side

    def set_piece(self, square_index: int, piece_id: str | None, side: str | None) -> None:
        state = self._require_state()
        self._validate_square_index(square_index)

        if piece_id is None or side is None:
            self.remove_piece(square_index)
            return

        state.board_state.cells[square_index] = Piece(
            piece_type=PieceTypeId(piece_id),
            side=self._parse_side(side),
        )

    def remove_piece(self, square_index: int) -> None:
        state = self._require_state()
        self._validate_square_index(square_index)
        state.board_state.cells[square_index] = None

    def export_notation(self) -> str:
        state = self._require_state()
        if self._mode.drop_rule is not None:
            try:
                return to_sfen(state)
            except ValueError:
                pass
        return to_fen(state)

    def import_notation(self, data: str) -> GameState:
        text = data.strip()
        if looks_like_pgn(text) and text.startswith("["):
            raise ValueError("PGN records a full game; import it from the game page")
        errors: list[str] = []
        parsers = []
        if looks_like_sfen(text):
            parsers.append(parse_sfen)
        parsers.append(parse_fen)
        if parse_sfen not in parsers:
            parsers.append(parse_sfen)
        for parser in parsers:
            try:
                self._state = parser(text, self._mode)
                return self._state
            except ValueError as exc:
                errors.append(str(exc))
        raise ValueError("; ".join(errors))

    def to_playable_state(self) -> GameState:
        state = deepcopy(self._require_state())
        state.extras["mode"] = self._mode
        return state

    def validate_for_mode(
        self,
        validator: Callable[[GameState], list[str]] | None = None,
        require_one_king_per_side: bool | None = None,
    ) -> list[str]:
        state = self._require_state()
        errors: list[str] = []

        if require_one_king_per_side is None:
            require_one_king_per_side = self._require_one_king_per_side

        if require_one_king_per_side:
            errors.extend(self._validate_one_king_per_side(state))

        active_validator = validator or self._validator
        if active_validator is not None:
            errors.extend(active_validator(state))

        return errors

    def _require_state(self) -> GameState:
        if self._state is None:
            raise RuntimeError("create or import a position before editing")
        return self._state

    def _validate_square_index(self, square_index: int) -> None:
        shape = self._mode.board.shape
        Square.from_index(square_index, shape.files, shape.ranks)

    def _parse_side(self, side: str) -> PieceSide:
        try:
            return PieceSide[side.upper()]
        except KeyError as exc:
            valid = ", ".join(member.name.lower() for member in PieceSide)
            raise ValueError(f"unknown piece side {side!r}; expected one of: {valid}") from exc

    def _validate_one_king_per_side(self, state: GameState) -> list[str]:
        counts = {PieceSide.WHITE: 0, PieceSide.BLACK: 0}
        for piece in state.board_state.cells.values():
            if piece is None:
                continue
            if piece is None:
                continue
            if piece.side in counts and self._mode.piece_is_royal(piece):
                counts[piece.side] += 1

        errors: list[str] = []
        for side, count in counts.items():
            if count != 1:
                errors.append(
                    f"expected exactly one {side.name.lower()} royal piece, found {count}"
                )
        return errors

"""Reversi, corners, and draughts as configured GameMode factories."""

from __future__ import annotations

from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.move import DropAction
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import CaptureSink, VictoryCondition, VictoryKind
from chess_core.core.state import GameState
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.catalog import corners_piece_catalog, draughts_piece_catalog, reversi_piece_catalog
from chess_core.modes.giveaway_rules import MustCaptureLegality

_LINES = (
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
)


def reversi() -> GameMode:
    """Othello/reversi: drop a disc that sandwiches and flips the opponent."""
    return (
        GameModeBuilder("reversi", "Reversi")
        .with_shape(8, 8)
        .with_pieces(reversi_piece_catalog())
        .with_turn_scenario(TurnScenario((TurnStep(StepKind.DROP),)))
        .with_victory(VictoryCondition(VictoryKind.MAJORITY, lose_on_no_legal_moves=False))
        .with_drop_rule(ReversiDropRule())
        .with_transitions((ReversiFlipTransition(),))
        .with_start_cells(_reversi_start_cells())
        .with_checks_enabled(False)
        .with_royal_type("")
        .with_initial_extras(
            {
                "hand_stock": 32,
                "hide_hands": True,
                "click_drops": True,
                "auto_pass": True,
                "eval_corners": (0, 7, 56, 63),
                "eval_corner_value": 10,
                "eval_adjacent_value": -5,
                "eval_disc": 1,
                "eval_search_depth": 4,
            }
        )
        .build()
    )


def corners() -> GameMode:
    """Russian уголки: 9 men in opposite 3×3 corners, steps and jumps, no captures."""
    white_home = _corner_mask(0, 2, 0, 2)
    black_home = _corner_mask(5, 7, 5, 7)
    return (
        GameModeBuilder("corners", "Corners")
        .with_shape(8, 8)
        .with_pieces(corners_piece_catalog())
        .with_turn_scenario(TurnScenario((TurnStep(StepKind.MOVE_OR_CAPTURE),)))
        .with_victory(VictoryCondition(VictoryKind.OCCUPY_ZONE))
        .with_start_cells(_corners_start_cells())
        .with_checks_enabled(False)
        .with_royal_type("")
        .with_initial_extras(
            {
                "occupy_zones": {
                    PieceSide.WHITE.name: black_home,
                    PieceSide.BLACK.name: white_home,
                }
            }
        )
        .build()
    )


def draughts() -> GameMode:
    """Russian draughts on 8×8 dark squares: mandatory jumps, flying kings."""
    return (
        GameModeBuilder("draughts", "Draughts")
        .with_shape(8, 8)
        .with_pieces(draughts_piece_catalog())
        .with_turn_scenario(TurnScenario((TurnStep(StepKind.MOVE_OR_CAPTURE),)))
        .with_victory(VictoryCondition(VictoryKind.MATERIAL, lose_on_no_legal_moves=False))
        .with_capture_sink(CaptureSink.DESTROY)
        .with_promotion_rule(LastRankPromotionRule({"man": "kingman"}))
        .with_legality(MustCaptureLegality())
        .with_start_cells(_draughts_start_cells())
        .with_checks_enabled(False)
        .with_royal_type("")
        .with_initial_extras(
            {
                "empty_side_wins": False,
                "blocked_side_wins": False,
            }
        )
        .build()
    )


class ReversiDropRule:
    allows_pass = True

    def can_drop(self, piece_type: PieceTypeId, square_index: int, state: object) -> bool:
        del piece_type
        if not isinstance(state, GameState):
            return False
        if state.board_state.piece_at(square_index) is not None:
            return False
        return bool(_reversi_flips(state, square_index, state.side_to_move))

    def allowed_faces(self, piece_type: PieceTypeId) -> tuple[str, ...] | None:
        del piece_type
        return None

    def captured_as(self, piece: Piece) -> Piece:
        return piece


class ReversiFlipTransition:
    def apply_after_action(self, action, state: object) -> object:
        if not isinstance(action, DropAction) or not isinstance(state, GameState):
            return state
        target = action.to_square.index(state.board_state.board.shape.files)
        for index in _reversi_flips(state, target, state.side_to_move):
            occupant = state.board_state.piece_at(index)
            if occupant is None:
                continue
            occupant = Piece(occupant.piece_type, action_side(state, action), occupant.state)
            state.board_state.cells[index] = occupant
        return state


def action_side(state: GameState, action: DropAction) -> PieceSide:
    del action
    return state.side_to_move


class LastRankPromotionRule:
    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    def promotion_zone_mask(self, side: str) -> int:
        del side
        return 0

    def choices(self, piece_type: PieceTypeId) -> tuple[PieceTypeId, ...]:
        promoted = self._mapping.get(piece_type.name)
        return (PieceTypeId(promoted),) if promoted else ()

    def can_promote(self, piece: Piece, origin: Square, target: Square, state: object) -> bool:
        del origin
        if piece.piece_type.name not in self._mapping or not isinstance(state, GameState):
            return False
        last = state.board_state.board.shape.ranks - 1 if piece.side is PieceSide.WHITE else 0
        return target.rank == last

    def must_promote(self, piece: Piece, origin: Square, target: Square, state: object) -> bool:
        return self.can_promote(piece, origin, target, state)


def _reversi_flips(state: GameState, square_index: int, side: PieceSide) -> list[int]:
    mode = state.extras.get("mode")
    if mode is None:
        return []
    shape = state.board_state.board.shape
    origin = Square.from_index(square_index, shape.files, shape.ranks)
    flipped: list[int] = []
    for direction in _LINES:
        line: list[int] = []
        current = origin
        while True:
            nxt = mode.topology.step(current, direction)
            if nxt is None:
                line = []
                break
            piece = state.board_state.piece_at(nxt.index(shape.files))
            if piece is None:
                line = []
                break
            if piece.side is side:
                break
            line.append(nxt.index(shape.files))
            current = nxt
        flipped.extend(line)
    return flipped


def _reversi_start_cells() -> dict[int, Piece]:
    disc = PieceTypeId("disc")
    return {
        27: Piece(disc, PieceSide.BLACK),
        28: Piece(disc, PieceSide.WHITE),
        35: Piece(disc, PieceSide.WHITE),
        36: Piece(disc, PieceSide.BLACK),
    }


def _corners_start_cells() -> dict[int, Piece]:
    cells: dict[int, Piece] = {}
    man = PieceTypeId("man")
    for rank in range(3):
        for file in range(3):
            cells[rank * 8 + file] = Piece(man, PieceSide.WHITE)
            cells[(7 - rank) * 8 + (7 - file)] = Piece(man, PieceSide.BLACK)
    return cells


def _draughts_start_cells() -> dict[int, Piece]:
    cells: dict[int, Piece] = {}
    man = PieceTypeId("man")
    for rank in range(3):
        for file in range(8):
            if (file + rank) % 2 == 0:
                cells[rank * 8 + file] = Piece(man, PieceSide.WHITE)
            if (file + (5 + rank)) % 2 == 0:
                cells[(5 + rank) * 8 + file] = Piece(man, PieceSide.BLACK)
    return cells


def _corner_mask(file_from: int, file_to: int, rank_from: int, rank_to: int) -> int:
    mask = 0
    for rank in range(rank_from, rank_to + 1):
        for file in range(file_from, file_to + 1):
            mask |= 1 << (rank * 8 + file)
    return mask

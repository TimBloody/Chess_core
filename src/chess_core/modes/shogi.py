"""Shogi and shogi-variant mode factories (stubs)."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.piece import Piece, PieceSide, PieceTransform, PieceTypeId
from chess_core.core.rules import DropRule, VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.catalog import (
    dobutsu_shogi_piece_catalog,
    kyoto_shogi_piece_catalog,
    shogi_piece_catalog,
)


def shogi() -> GameMode:
    """9x9, drops, promotion zones, checkmate king."""
    return (
        GameModeBuilder("shogi", "Shogi")
        .with_shape(9, 9)
        .with_pieces(shogi_piece_catalog())
        .with_turn_scenario(_standard_single_move_scenario())
        .with_victory(VictoryCondition(VictoryKind.CHECKMATE))
        .build()
    )


def kyoto_shogi() -> GameMode:
    """
    5x5 Kyoto shogi (Tamiya Katsuya).

    - No promotion zone: every non-king piece flips to its paired type after each move.
    - Pairs: Tokin<->Lance, Silver<->Bishop, Gold<->Knight, Pawn<->Rook; King does not flip.
    - Drops: captured piece may be placed with either face up (DropRule.allowed_faces).
    - Relaxed drop restrictions vs standard shogi (same file pawn, last rank, etc.).
    - Victory: checkmate (same goal as shogi).

    Configure via PieceType.transforms_on_move (PieceTransform) and drop_rule,
    not hardcoded movegen branches.
    """
    catalog = kyoto_shogi_piece_catalog()
    flip = KyotoFlipTransform()
    for piece_type in catalog.all_types():
        if piece_type.id.name != "king":
            piece_type.transforms_on_move = flip

    # Kyoto flip-after-move is represented as a PieceTransform on each
    # non-king piece type; movegen should consume that config, not branch by mode.
    return (
        GameModeBuilder("kyoto_shogi", "Kyoto Shogi")
        .with_shape(5, 5)
        .with_pieces(catalog)
        .with_turn_scenario(_standard_single_move_scenario())
        .with_victory(VictoryCondition(VictoryKind.CHECKMATE))
        .with_drop_rule(KyotoDropRule())
        .with_start_cells(_kyoto_start_cells())
        .build()
    )


def dobutsu_shogi() -> GameMode:
    """3x4 animal shogi for children; smaller catalog and board."""
    return (
        GameModeBuilder("dobutsu_shogi", "Dobutsu Shogi")
        .with_shape(3, 4)
        .with_pieces(dobutsu_shogi_piece_catalog())
        .with_turn_scenario(_standard_single_move_scenario())
        .with_victory(VictoryCondition(VictoryKind.KING_REACHES_ZONE))
        .build()
    )


class KyotoFlipTransform(PieceTransform):
    """Stub: flip piece to alternate face in catalog after each move."""

    _pairs = {
        "tokin": "lance",
        "lance": "tokin",
        "silver": "bishop",
        "bishop": "silver",
        "gold": "knight",
        "knight": "gold",
        "pawn": "rook",
        "rook": "pawn",
    }

    def apply(self, piece_type: PieceTypeId, context) -> PieceTypeId:
        return PieceTypeId(self._pairs.get(piece_type.name, piece_type.name))


class KyotoDropRule(DropRule):
    """Kyoto pieces may be dropped on any empty square with either face up."""

    def can_drop(self, piece_type: PieceTypeId, square_index: int, state: object) -> bool:
        return state.board_state.piece_at(square_index) is None

    def allowed_faces(self, piece_type: PieceTypeId) -> tuple[str, ...] | None:
        paired = KyotoFlipTransform._pairs.get(piece_type.name)
        return None if paired is None else (piece_type.name, paired)


def _kyoto_start_cells() -> dict[int, Piece]:
    white = ("tokin", "silver", "king", "gold", "pawn")
    black = tuple(reversed(white))
    cells: dict[int, Piece] = {}
    for file, name in enumerate(white):
        cells[file] = Piece(PieceTypeId(name), PieceSide.WHITE)
    for file, name in enumerate(black):
        cells[20 + file] = Piece(PieceTypeId(name), PieceSide.BLACK)
    return cells


def _standard_single_move_scenario() -> TurnScenario:
    return TurnScenario((TurnStep(StepKind.MOVE_OR_DROP),))

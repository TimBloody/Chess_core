"""Shogi and shogi-variant mode factories."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.piece import Piece, PieceSide, PieceTransform, PieceTypeId
from chess_core.core.rules import CaptureSink, DropRule, VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.catalog import (
    dobutsu_shogi_piece_catalog,
    kyoto_shogi_piece_catalog,
    shogi_piece_catalog,
)
from chess_core.modes.shogi_rules import (
    DobutsuDropRule,
    DobutsuPromotionRule,
    ShogiDropRule,
    ShogiPromotionRule,
)


def shogi() -> GameMode:
    """9x9 standard shogi: drops, promotion zone, checkmate the king."""
    return (
        GameModeBuilder("shogi", "Shogi")
        .with_shape(9, 9)
        .with_pieces(shogi_piece_catalog())
        .with_turn_scenario(_standard_single_move_scenario())
        .with_victory(VictoryCondition(VictoryKind.CHECKMATE))
        .with_drop_rule(ShogiDropRule())
        .with_capture_sink(CaptureSink.MOVER_HAND)
        .with_promotion_rule(ShogiPromotionRule())
        .with_start_cells(_shogi_start_cells())
        .with_asset_family("shogi")
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
        .with_capture_sink(CaptureSink.MOVER_HAND)
        .with_start_cells(_kyoto_start_cells())
        .with_asset_family("shogi")
        .build()
    )


def dobutsu_shogi() -> GameMode:
    """3x4 animal shogi: capture the lion or reach the opposite rank safely."""
    return (
        GameModeBuilder("dobutsu_shogi", "Dobutsu Shogi")
        .with_shape(3, 4)
        .with_pieces(dobutsu_shogi_piece_catalog())
        .with_turn_scenario(_standard_single_move_scenario())
        .with_victory(
            (
                VictoryCondition(VictoryKind.KING_CAPTURE),
                VictoryCondition(VictoryKind.KING_REACHES_ZONE),
            )
        )
        .with_drop_rule(DobutsuDropRule())
        .with_capture_sink(CaptureSink.MOVER_HAND)
        .with_promotion_rule(DobutsuPromotionRule())
        .with_start_cells(_dobutsu_start_cells())
        .with_royal_type("lion")
        .with_asset_family("dobutsu")
        .build()
    )


class KyotoFlipTransform(PieceTransform):
    """Flip piece to alternate face in catalog after each move."""

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

    def captured_as(self, piece: Piece) -> Piece:
        return piece


def _kyoto_start_cells() -> dict[int, Piece]:
    white = ("tokin", "silver", "king", "gold", "pawn")
    black = tuple(reversed(white))
    cells: dict[int, Piece] = {}
    for file, name in enumerate(white):
        cells[file] = Piece(PieceTypeId(name), PieceSide.WHITE)
    for file, name in enumerate(black):
        cells[20 + file] = Piece(PieceTypeId(name), PieceSide.BLACK)
    return cells


def _shogi_start_cells() -> dict[int, Piece]:
    back = ("lance", "knight", "silver", "gold", "king", "gold", "silver", "knight", "lance")
    cells: dict[int, Piece] = {}
    for file, name in enumerate(back):
        cells[file] = Piece(PieceTypeId(name), PieceSide.WHITE)
        cells[72 + file] = Piece(PieceTypeId(name), PieceSide.BLACK)
        cells[18 + file] = Piece(PieceTypeId("pawn"), PieceSide.WHITE)
        cells[54 + file] = Piece(PieceTypeId("pawn"), PieceSide.BLACK)
    cells[10] = Piece(PieceTypeId("bishop"), PieceSide.WHITE)
    cells[16] = Piece(PieceTypeId("rook"), PieceSide.WHITE)
    cells[64] = Piece(PieceTypeId("rook"), PieceSide.BLACK)
    cells[70] = Piece(PieceTypeId("bishop"), PieceSide.BLACK)
    return cells


def _dobutsu_start_cells() -> dict[int, Piece]:
    """Sente (white) at the bottom: giraffe, lion, elephant; chick on b2."""
    cells = {
        0: Piece(PieceTypeId("giraffe"), PieceSide.WHITE),
        1: Piece(PieceTypeId("lion"), PieceSide.WHITE),
        2: Piece(PieceTypeId("elephant"), PieceSide.WHITE),
        4: Piece(PieceTypeId("chick"), PieceSide.WHITE),
        7: Piece(PieceTypeId("chick"), PieceSide.BLACK),
        9: Piece(PieceTypeId("elephant"), PieceSide.BLACK),
        10: Piece(PieceTypeId("lion"), PieceSide.BLACK),
        11: Piece(PieceTypeId("giraffe"), PieceSide.BLACK),
    }
    return cells


def _standard_single_move_scenario() -> TurnScenario:
    return TurnScenario((TurnStep(StepKind.MOVE_OR_DROP),))

"""Chess and chess-variant mode factories."""

from __future__ import annotations

import random

from chess_core.core.board import BoardShape
from chess_core.core.castling import StandardCastlingRule
from chess_core.core.chess960 import (
    Chess960CastlingRule,
    chess960_rook_files,
    chess960_start_cells,
    scharnagl_back_rank,
)
from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.masks import MaskTableLoader
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import CastlingRule, DropRule, VictoryCondition, VictoryKind
from chess_core.core.topology import CylindricalFilesTopology
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.infra.paths import masks_dir
from chess_core.modes.catalog import chess_piece_catalog
from chess_core.modes.chess_rules import ChessPromotionRule
from chess_core.modes.crazyhouse_rules import CrazyhouseDropRule
from chess_core.modes.fairytale_rules import FairytaleFileResolver
from chess_core.modes.koth_rules import center_zone_mask
from chess_core.modes.three_check_rules import ThreeCheckCounter
from chess_core.modes.two_move_rules import DoubleMoveTurnPolicy


def classic_chess() -> GameMode:
    """8x8, flat topology, standard turn (one move), checkmate victory."""
    return _chess_mode("classic_chess", "Classic Chess")


def chess960(position_id: int | None = None) -> GameMode:
    """Fischer random: Scharnagl id 0..959, FIDE castling to c/g files."""
    chosen = random.randrange(960) if position_id is None else position_id
    back_rank = scharnagl_back_rank(chosen)
    rook_files = chess960_rook_files(back_rank)
    return _chess_mode(
        "chess960",
        f"Chess960 #{chosen}",
        start_cells=chess960_start_cells(chosen),
        extras={
            "castling_rights": {"K", "Q", "k", "q"},
            "chess960_position": chosen,
        },
        castling_rule=Chess960CastlingRule(rook_files),
    )


def crazyhouse() -> GameMode:
    """Captures to hand; drops instead of a board move; pawns not on 1st/8th."""
    return _chess_mode(
        "crazyhouse",
        "Crazyhouse",
        scenario=TurnScenario((TurnStep(StepKind.MOVE_OR_DROP),)),
        drop_rule=CrazyhouseDropRule(),
    )


def giveaway() -> GameMode:
    """Antichess / losing chess: must capture if possible; lose all pieces or stalemate."""
    return _chess_mode(
        "giveaway",
        "Giveaway Chess",
        victory=VictoryCondition(VictoryKind.MATERIAL),
    )


def minichess() -> GameMode:
    """Configurable small board (e.g. 5x5, 6x6) via same builder as classic."""
    return (
        GameModeBuilder("minichess", "Mini Chess")
        .with_shape(5, 5)
        .with_pieces(chess_piece_catalog())
        .with_turn_scenario(_standard_single_move_scenario())
        .with_victory(VictoryCondition(VictoryKind.CHECKMATE))
        .with_promotion_rule(ChessPromotionRule())
        .build()
    )


def cylindrical_chess() -> GameMode:
    """Classic rules on 8x8 with files a and h glued (CylindricalFilesTopology)."""
    shape = BoardShape(files=8, ranks=8)
    return _chess_mode(
        "cylindrical_chess",
        "Cylindrical Chess",
        topology=CylindricalFilesTopology(shape),
    )


def duck_chess() -> GameMode:
    """Move then place the duck; king capture; stalemate is a win for the blocked side."""
    scenario = TurnScenario(
        (
            TurnStep(StepKind.MOVE_OR_CAPTURE, label="move"),
            TurnStep(StepKind.PLACE_BLOCKER, label="duck"),
        )
    )
    return _chess_mode(
        "duck_chess",
        "Duck Chess",
        scenario=scenario,
        victory=VictoryCondition(VictoryKind.KING_CAPTURE, lose_on_no_legal_moves=False),
    )


def two_move_chess() -> GameMode:
    """Two moves per turn unless in check or White's first turn of the game."""
    scenario = TurnScenario(
        (
            TurnStep(StepKind.MOVE_OR_CAPTURE, label="move 1"),
            TurnStep(StepKind.MOVE_OR_CAPTURE, label="move 2"),
        )
    )
    return (
        _chess_builder("two_move", "Two-move Chess")
        .with_turn_policy(DoubleMoveTurnPolicy())
        .with_turn_scenario(scenario)
        .with_is_dummy(False)
        .with_modifier_ids(("two_move",))
        .build()
    )


def fairytale_chess() -> GameMode:
    """File-dependent movement for rook/bishop/knight by current file."""
    return (
        _chess_builder("fairytale", "Fairytale Chess")
        .with_move_resolver(FairytaleFileResolver())
        .with_is_dummy(False)
        .with_modifier_ids(("fairytale",))
        .build()
    )


def three_check_chess() -> GameMode:
    """Win by delivering three checks or checkmate."""
    return (
        _chess_builder("three_check", "Three-check Chess")
        .with_victory(
            (
                VictoryCondition(VictoryKind.CHECKMATE),
                VictoryCondition(VictoryKind.THREE_CHECK, threshold=3),
            )
        )
        .with_transitions((ThreeCheckCounter(),))
        .with_initial_extras(
            {
                "castling_rights": {"K", "Q", "k", "q"},
                "checks_given": {"white": 0, "black": 0},
            }
        )
        .with_is_dummy(False)
        .with_modifier_ids(("three_check",))
        .build()
    )


def king_of_the_hill() -> GameMode:
    """Win by safely reaching the centre with the king or checkmate."""
    mask = center_zone_mask(files=8, ranks=8)
    return (
        _chess_builder("king_of_the_hill", "King of the Hill")
        .with_victory(
            (
                VictoryCondition(VictoryKind.CHECKMATE),
                VictoryCondition(
                    VictoryKind.KING_REACHES_ZONE, target_zone_mask=mask
                ),
            )
        )
        .with_is_dummy(False)
        .with_modifier_ids(("king_of_the_hill",))
        .build()
    )


def three_check_king_of_the_hill() -> GameMode:
    """Three-check and king-of-the-hill victory modifiers combined."""
    mask = center_zone_mask(files=8, ranks=8)
    return (
        _chess_builder(
            "three_check_king_of_the_hill",
            "Three-check King of the Hill",
        )
        .with_victory(
            (
                VictoryCondition(VictoryKind.CHECKMATE),
                VictoryCondition(VictoryKind.THREE_CHECK, threshold=3),
                VictoryCondition(
                    VictoryKind.KING_REACHES_ZONE, target_zone_mask=mask
                ),
            )
        )
        .with_transitions((ThreeCheckCounter(),))
        .with_initial_extras(
            {
                "castling_rights": {"K", "Q", "k", "q"},
                "checks_given": {"white": 0, "black": 0},
            }
        )
        .with_is_dummy(False)
        .with_modifier_ids(("three_check", "king_of_the_hill"))
        .build()
    )


def _standard_single_move_scenario() -> TurnScenario:
    return TurnScenario((TurnStep(StepKind.MOVE_OR_CAPTURE),))


def _chess_builder(
    mode_id: str,
    name: str,
    *,
    topology: CylindricalFilesTopology | None = None,
    scenario: TurnScenario | None = None,
    victory: VictoryCondition | None = None,
    start_cells: dict[int, Piece] | None = None,
    extras: dict[str, object] | None = None,
    drop_rule: DropRule | None = None,
    castling_rule: CastlingRule | None = None,
) -> GameModeBuilder:
    builder = (
        GameModeBuilder(mode_id, name)
        .with_shape(8, 8)
        .with_pieces(chess_piece_catalog())
        .with_turn_scenario(scenario or _standard_single_move_scenario())
        .with_victory(victory or VictoryCondition(VictoryKind.CHECKMATE))
        .with_start_cells(start_cells or _classic_start_cells())
        .with_initial_extras(extras or {"castling_rights": {"K", "Q", "k", "q"}})
        .with_castling_rule(castling_rule or StandardCastlingRule())
        .with_promotion_rule(ChessPromotionRule())
    )
    if drop_rule is not None:
        builder.with_drop_rule(drop_rule)
    if topology is not None:
        builder.with_topology(topology)
    mask_name = "cylinder_8x8" if topology is not None else "flat_8x8"
    mask_path = masks_dir() / f"{mask_name}.json"
    if mask_path.is_file():
        builder.with_ray_table(MaskTableLoader().load(mask_path))
    return builder


def _chess_mode(
    mode_id: str,
    name: str,
    *,
    topology: CylindricalFilesTopology | None = None,
    scenario: TurnScenario | None = None,
    victory: VictoryCondition | None = None,
    start_cells: dict[int, Piece] | None = None,
    extras: dict[str, object] | None = None,
    drop_rule: DropRule | None = None,
    castling_rule: CastlingRule | None = None,
) -> GameMode:
    return _chess_builder(
        mode_id,
        name,
        topology=topology,
        scenario=scenario,
        victory=victory,
        start_cells=start_cells,
        extras=extras,
        drop_rule=drop_rule,
        castling_rule=castling_rule,
    ).build()


def _classic_start_cells() -> dict[int, Piece]:
    back_rank = ("rook", "knight", "bishop", "queen", "king", "bishop", "knight", "rook")
    cells: dict[int, Piece] = {}
    for file, name in enumerate(back_rank):
        cells[file] = Piece(PieceTypeId(name), PieceSide.WHITE)
        cells[56 + file] = Piece(PieceTypeId(name), PieceSide.BLACK)
        cells[8 + file] = Piece(PieceTypeId("pawn"), PieceSide.WHITE)
        cells[48 + file] = Piece(PieceTypeId("pawn"), PieceSide.BLACK)
    return cells

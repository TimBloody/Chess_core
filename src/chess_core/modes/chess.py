"""Chess and chess-variant mode factories."""

from __future__ import annotations

import random

from chess_core.core.board import BoardShape
from chess_core.core.chess960 import (
    chess960_rook_files,
    chess960_start_cells,
    decode_chess960_back_rank,
)
from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.masks import MaskTableLoader
from chess_core.infra.paths import masks_dir
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import CaptureSink, VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.core.topology import CylindricalFilesTopology
from chess_core.modes.catalog import chess_piece_catalog
from chess_core.modes.crazyhouse_rules import CrazyhouseDropRule
from chess_core.modes.giveaway_rules import MustCaptureLegality


def classic_chess() -> GameMode:
    """8x8, flat topology, standard turn (one move), checkmate victory."""
    return _chess_mode("classic_chess", "Classic Chess")


def chess960(position_id: int | None = None) -> GameMode:
    """Fischer random: classic rules with a Scharnagl back rank 0..959."""
    chosen = random.randrange(960) if position_id is None else position_id
    back_rank = decode_chess960_back_rank(chosen)
    extras: dict[str, object] = {
        "castling_rights": {"K", "Q", "k", "q"},
        "castling_rooks": chess960_rook_files(back_rank),
        "chess960_position": chosen,
    }
    return _chess_mode(
        "chess960",
        "Chess960",
        start_cells=chess960_start_cells(chosen),
        extras=extras,
    )


def crazyhouse() -> GameMode:
    """Captures to hand; drops like shogi but chess pieces on 8x8."""
    return _chess_mode(
        "crazyhouse",
        "Crazyhouse",
        scenario=TurnScenario((TurnStep(StepKind.MOVE_OR_DROP),)),
        drop_rule=CrazyhouseDropRule(),
        capture_sink=CaptureSink.MOVER_HAND,
    )


def giveaway() -> GameMode:
    """Antichess / losing chess: must capture if possible; lose all pieces or stalemate."""
    return _chess_mode(
        "giveaway",
        "Giveaway Chess",
        victory=VictoryCondition(VictoryKind.MATERIAL, lose_on_no_legal_moves=False),
        extras={"castling_rights": set(), "promote_includes_king": True},
        legality=MustCaptureLegality(),
        checks_enabled=False,
    )


def minichess() -> GameMode:
    """Gardner 5x5: RNBQK and pawns, no castling."""
    return (
        GameModeBuilder("minichess", "Mini Chess")
        .with_shape(5, 5)
        .with_pieces(chess_piece_catalog())
        .with_turn_scenario(_standard_single_move_scenario())
        .with_victory(VictoryCondition(VictoryKind.CHECKMATE))
        .with_start_cells(_minichess_start_cells())
        .with_initial_extras({"castling_rights": set()})
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
    """TurnScenario: MoveAction then PlaceBlockerAction (duck)."""
    scenario = TurnScenario(
        (
            TurnStep(StepKind.MOVE_OR_CAPTURE, label="move"),
            TurnStep(StepKind.PLACE_BLOCKER, label="duck"),
        )
    )
    return _chess_mode("duck_chess", "Duck Chess", scenario=scenario)


def _standard_single_move_scenario() -> TurnScenario:
    return TurnScenario((TurnStep(StepKind.MOVE_OR_CAPTURE),))


def _chess_mode(
    mode_id: str,
    name: str,
    *,
    topology: CylindricalFilesTopology | None = None,
    scenario: TurnScenario | None = None,
    victory: VictoryCondition | None = None,
    drop_rule=None,
    capture_sink: CaptureSink | None = None,
    extras: dict[str, object] | None = None,
    start_cells: dict[int, Piece] | None = None,
    legality=None,
    checks_enabled: bool = True,
) -> GameMode:
    merged_extras: dict[str, object] = {"castling_rights": {"K", "Q", "k", "q"}}
    if extras:
        merged_extras.update(extras)
    builder = (
        GameModeBuilder(mode_id, name)
        .with_shape(8, 8)
        .with_pieces(chess_piece_catalog())
        .with_turn_scenario(scenario or _standard_single_move_scenario())
        .with_victory(victory or VictoryCondition(VictoryKind.CHECKMATE))
        .with_start_cells(start_cells if start_cells is not None else _classic_start_cells())
        .with_initial_extras(merged_extras)
        .with_checks_enabled(checks_enabled)
    )
    if topology is not None:
        builder.with_topology(topology)
    if drop_rule is not None:
        builder.with_drop_rule(drop_rule)
    if capture_sink is not None:
        builder.with_capture_sink(capture_sink)
    if legality is not None:
        builder.with_legality(legality)
    mask_name = "cylinder_8x8" if topology is not None else "flat_8x8"
    mask_path = masks_dir() / f"{mask_name}.json"
    if mask_path.is_file():
        builder.with_ray_table(MaskTableLoader().load(mask_path))

    return builder.build()


def _classic_start_cells() -> dict[int, Piece]:
    back_rank = ("rook", "knight", "bishop", "queen", "king", "bishop", "knight", "rook")
    cells: dict[int, Piece] = {}
    for file, name in enumerate(back_rank):
        cells[file] = Piece(PieceTypeId(name), PieceSide.WHITE)
        cells[56 + file] = Piece(PieceTypeId(name), PieceSide.BLACK)
        cells[8 + file] = Piece(PieceTypeId("pawn"), PieceSide.WHITE)
        cells[48 + file] = Piece(PieceTypeId("pawn"), PieceSide.BLACK)
    return cells


def _minichess_start_cells() -> dict[int, Piece]:
    back_rank = ("rook", "knight", "bishop", "queen", "king")
    cells: dict[int, Piece] = {}
    for file, name in enumerate(back_rank):
        cells[file] = Piece(PieceTypeId(name), PieceSide.WHITE)
        cells[20 + file] = Piece(PieceTypeId(name), PieceSide.BLACK)
        cells[5 + file] = Piece(PieceTypeId("pawn"), PieceSide.WHITE)
        cells[15 + file] = Piece(PieceTypeId("pawn"), PieceSide.BLACK)
    return cells

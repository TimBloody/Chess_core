"""Chess and chess-variant mode factories (stubs)."""

from __future__ import annotations

from chess_core.core.board import BoardShape
from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.masks import MaskTableLoader
from chess_core.infra.paths import masks_dir
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.core.topology import CylindricalFilesTopology
from chess_core.modes.catalog import chess_piece_catalog


def classic_chess() -> GameMode:
    """8x8, flat topology, standard turn (one move), checkmate victory."""
    return _chess_mode("classic_chess", "Classic Chess")


def chess960() -> GameMode:
    """Fischer random: classic rules with randomized back rank."""
    return _chess_mode("chess960", "Chess960")


def crazyhouse() -> GameMode:
    """Captures to hand; drops like shogi but chess pieces on 8x8."""
    return _chess_mode("crazyhouse", "Crazyhouse")


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
) -> GameMode:
    builder = (
        GameModeBuilder(mode_id, name)
        .with_shape(8, 8)
        .with_pieces(chess_piece_catalog())
        .with_turn_scenario(scenario or _standard_single_move_scenario())
        .with_victory(victory or VictoryCondition(VictoryKind.CHECKMATE))
        .with_start_cells(_classic_start_cells())
        .with_initial_extras({"castling_rights": {"K", "Q", "k", "q"}})
    )
    if topology is not None:
        builder.with_topology(topology)
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

"""Tests for PlaceAction and turn scenario integration."""

from chess_core.core.board import Square
from chess_core.core.move import ActionKind, PlaceAction, Turn
from chess_core.core.piece import PieceSide, PieceTypeId
from chess_core.core.rules_strategy import apply_place_action
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.chess import classic_chess


def test_place_action_kind_and_turn_scenario() -> None:
    action = PlaceAction(PieceTypeId("checker_man"), Square(2, 2))
    assert action.kind is ActionKind.PLACE_PIECE

    scenario = TurnScenario((TurnStep(StepKind.PLACE),))
    turn = Turn(PieceSide.WHITE, [action])
    assert scenario.validate_turn(turn) is True


def test_apply_place_action_on_empty_square() -> None:
    mode = classic_chess()
    empty = mode.initial_state()
    for index in range(mode.board.shape.cell_count):
        empty.board_state.cells[index] = None

    turn = Turn(
        PieceSide.WHITE,
        [PlaceAction(PieceTypeId("queen"), Square(4, 4))],
    )
    apply_place_action(empty, turn, turn.actions[0])
    assert empty.board_state.piece_at(36) is not None
    assert empty.board_state.piece_at(36).piece_type.name == "queen"


def test_apply_turn_accepts_place_when_scenario_allows() -> None:
    from chess_core.core.gamemode import GameModeBuilder
    from chess_core.core.rules import VictoryCondition, VictoryKind
    from chess_core.modes.catalog import chess_piece_catalog

    mode = (
        GameModeBuilder("place_test", "Place Test")
        .with_shape(8, 8)
        .with_pieces(chess_piece_catalog())
        .with_turn_scenario(TurnScenario((TurnStep(StepKind.PLACE),)))
        .with_victory(VictoryCondition(VictoryKind.CUSTOM))
        .build()
    )
    state = mode.initial_state()
    turn = Turn(
        PieceSide.WHITE,
        [PlaceAction(PieceTypeId("queen"), Square(4, 4))],
    )
    next_state = state.apply_turn(turn, record_history=False)
    assert next_state.board_state.piece_at(36) is not None

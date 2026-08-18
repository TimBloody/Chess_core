"""Tests for game record timeline."""

from chess_core.app.game_record import GameRecord
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, Turn
from chess_core.core.piece import PieceSide
from chess_core.modes.chess import classic_chess


def test_append_undo_and_go_to_revision() -> None:
    mode = classic_chess()
    record = GameRecord.from_mode(mode)
    e4 = Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))])
    record.append_turn(e4, notation="e4")
    assert record.live_revision == 1
    record.go_to(0)
    assert record.view_revision == 0
    assert record.current_view_state().board_state.piece_at(12) is not None
    record.go_live()
    assert record.is_live
    record.undo_last_turn()
    assert record.live_revision == 0


def test_viewing_history_blocks_live_append() -> None:
    mode = classic_chess()
    record = GameRecord.from_mode(mode)
    record.append_turn(
        Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]),
        notation="e4",
    )
    record.go_to(0)
    try:
        record.append_turn(
            Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]),
            notation="e4",
        )
        raised = False
    except RuntimeError:
        raised = True
    assert raised

"""Bughouse capture routing and partner gifts."""

from chess_core.core.board import Square
from chess_core.core.move import DropAction, MoveAction, Turn
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import CaptureSink
from chess_core.core.state import HandsState
from chess_core.modes.bughouse import bughouse
from chess_core.modes.crazyhouse_rules import demote_captured_piece


def test_bughouse_mode_uses_partner_outbound_sink() -> None:
    mode = bughouse()
    assert mode.capture_sink is CaptureSink.PARTNER_OUTBOUND
    assert mode.drop_rule is not None
    assert mode.initial_extras["match_kind"] == "bughouse"
    assert mode.initial_state().hands is not None


def test_capture_goes_to_outbound_gifts_not_own_hand() -> None:
    mode = bughouse()
    state = mode.initial_state()
    state.board_state.cells = {
        index: None for index in range(mode.board.shape.cell_count)
    }
    state.board_state.cells[12] = Piece(PieceTypeId("knight"), PieceSide.WHITE)
    state.board_state.cells[28] = Piece(PieceTypeId("pawn"), PieceSide.BLACK)
    state.side_to_move = PieceSide.WHITE
    state.hands = HandsState()
    result = state.apply_turn(
        Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))])
    )
    gifts = result.extras.get("outbound_gifts") or []
    assert len(gifts) == 1
    assert gifts[0].piece_type.name == "pawn"
    assert result.hands is not None
    assert result.hands.count(PieceSide.WHITE, "pawn") == 0


def test_promoted_capture_demotes_to_pawn() -> None:
    queen = Piece(
        PieceTypeId("queen"),
        PieceSide.BLACK,
        {"promoted_from": "pawn"},
    )
    demoted = demote_captured_piece(queen)
    assert demoted.piece_type.name == "pawn"


def test_drop_after_transfer_is_legal() -> None:
    mode = bughouse()
    state = mode.initial_state()
    state.board_state.cells[27] = None
    assert state.hands is not None
    state.hands.add(PieceSide.WHITE, Piece(PieceTypeId("knight"), PieceSide.WHITE))
    result = state.apply_turn(
        Turn(PieceSide.WHITE, [DropAction(PieceTypeId("knight"), Square(3, 3))])
    )
    assert result.board_state.piece_at(27) is not None
    assert result.board_state.piece_at(27).piece_type.name == "knight"

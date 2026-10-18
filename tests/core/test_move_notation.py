"""Tests for move notation formatting."""

from chess_core.core.board import Square
from chess_core.core.move import DropAction, MoveAction, PlaceBlockerAction, Turn
from chess_core.core.notation import NotationStyle, format_action, format_turn, square_name
from chess_core.core.piece import PieceSide, PieceTypeId
from chess_core.modes.chess import classic_chess


def test_square_name_on_rectangular_board() -> None:
    assert square_name(Square(0, 0)) == "a1"
    assert square_name(Square(9, 2)) == "j3"


def test_from_to_notation_for_quiet_move() -> None:
    mode = classic_chess()
    state = mode.initial_state()
    turn = Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))])
    after = state.apply_turn(turn, record_history=False)
    text = format_turn(turn, before=state, after=after, style=NotationStyle.FROM_TO)
    assert text == "e2-e4"


def test_uci_round_trip() -> None:
    from chess_core.core.notation import format_uci, parse_uci

    move = parse_uci("e2e4")
    assert (move.from_square.file, move.from_square.rank) == (4, 1)
    assert (move.to_square.file, move.to_square.rank) == (4, 3)
    assert format_uci(move) == "e2e4"
    promo = parse_uci("e7e8q")
    assert promo.promotion_choice is not None
    assert promo.promotion_choice.name == "queen"
    assert format_uci(promo) == "e7e8q"
    king = parse_uci("a7a8k")
    assert king.promotion_choice is not None
    assert king.promotion_choice.name == "king"
    assert format_uci(king) == "a7a8k"


def test_piece_square_notation() -> None:
    mode = classic_chess()
    state = mode.initial_state()
    turn = Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))])
    after = state.apply_turn(turn, record_history=False)
    text = format_turn(turn, before=state, after=after, style=NotationStyle.PIECE_SQUARE)
    assert text == "e4"


def test_duck_and_drop_notation() -> None:
    mode = classic_chess()
    state = mode.initial_state()
    move = MoveAction(Square(4, 1), Square(4, 3))
    duck = PlaceBlockerAction(Square(0, 0))
    turn = Turn(PieceSide.WHITE, [move, duck])
    text = format_turn(turn, before=state, after=state, style=NotationStyle.FROM_TO)
    assert "·" in text
    assert "@a1" in text

    drop = DropAction(PieceTypeId("knight"), Square(2, 2))
    assert format_action(drop, before=state, after=state) == "N@c3"

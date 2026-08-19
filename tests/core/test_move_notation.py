"""Tests for move notation formatting."""

from chess_core.core.board import Square
from chess_core.core.move import DropAction, MoveAction, PlaceBlockerAction, Turn
from chess_core.core.notation import (
    NotationStyle,
    format_action,
    format_turn,
    parse_fen,
    square_name,
)
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


def _san(
    fen: str,
    source: Square,
    target: Square,
    promotion: str | None = None,
) -> str:
    mode = classic_chess()
    state = parse_fen(fen, mode)
    action = MoveAction(
        source,
        target,
        PieceTypeId(promotion) if promotion else None,
    )
    turn = Turn(state.side_to_move, [action])
    after = state.apply_turn(turn, record_history=False)
    return format_turn(
        turn,
        before=state,
        after=after,
        style=NotationStyle.PIECE_SQUARE,
    )


def test_san_disambiguates_by_file_rank_and_full_square() -> None:
    assert (
        _san(
            "1n2k3/8/5n2/8/8/8/8/4K3 b - - 0 1",
            Square(1, 7),
            Square(3, 6),
        )
        == "Nbd7"
    )
    assert (
        _san(
            "4k3/8/8/8/8/R7/8/R3K3 w - - 0 1",
            Square(0, 0),
            Square(0, 1),
        )
        == "R1a2"
    )
    assert (
        _san(
            "4k3/8/8/1N6/8/1N3N2/8/4K3 w - - 0 1",
            Square(1, 2),
            Square(3, 3),
        )
        == "Nb3d4"
    )


def test_san_formats_capture_en_passant_promotion_check_and_mate() -> None:
    assert (
        _san(
            "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1",
            Square(4, 4),
            Square(3, 5),
        )
        == "exd6"
    )
    assert (
        _san(
            "7k/4P3/8/8/8/8/8/4K3 w - - 0 1",
            Square(4, 6),
            Square(4, 7),
            "queen",
        )
        == "e8=Q+"
    )

    mode = classic_chess()
    state = mode.initial_state()
    for source, target in (
        (Square(5, 1), Square(5, 2)),
        (Square(4, 6), Square(4, 4)),
        (Square(6, 1), Square(6, 3)),
        (Square(3, 7), Square(7, 3)),
    ):
        action = MoveAction(source, target)
        turn = Turn(state.side_to_move, [action])
        after = state.apply_turn(turn, record_history=False)
        text = format_turn(
            turn,
            before=state,
            after=after,
            style=NotationStyle.PIECE_SQUARE,
        )
        state = after
    assert text == "Qh4#"


def test_san_formats_castling_with_letter_o() -> None:
    assert (
        _san(
            "4k3/8/8/8/8/8/8/4K2R w K - 0 1",
            Square(4, 0),
            Square(6, 0),
        )
        == "O-O"
    )


def test_san_ignores_pinned_piece_when_disambiguating() -> None:
    assert (
        _san(
            "k7/8/8/8/1b6/2N5/8/4K1N1 w - - 0 1",
            Square(6, 0),
            Square(4, 1),
        )
        == "Ne2"
    )


def test_san_piece_capture_uses_x_and_check_suffix() -> None:
    assert (
        _san(
            "4k3/5p2/8/8/2B5/8/8/4K3 w - - 0 1",
            Square(2, 3),
            Square(5, 6),
        )
        == "Bxf7+"
    )

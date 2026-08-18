import pytest

from chess_core.app.game import GameStatus
from chess_core.core.board import Square
from chess_core.core.move import MoveAction
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import parse_fen
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.modes.chess import classic_chess
from chess_core.tools.classical_demo import parse_move, run_moves


def move(name: str, promotion: str | None = None) -> MoveAction:
    def square(token: str) -> Square:
        return Square(ord(token[0]) - ord("a"), int(token[1]) - 1)

    return MoveAction(
        square(name[:2]),
        square(name[2:]),
        PieceTypeId(promotion) if promotion else None,
    )


def legal_from_fen(fen: str) -> tuple[MoveGenerator, object, set[MoveAction]]:
    mode = classic_chess()
    state = parse_fen(fen, mode)
    generator = MoveGenerator(mode)
    return generator, state, set(generator.generate_legal(state))


@pytest.mark.parametrize(
    ("fen", "allowed_capture", "forbidden_beyond"),
    (
            ("4k3/8/8/8/3R1p2/8/8/4K3 w - - 0 1", "d4f4", "d4g4"),
            ("4k3/6p1/8/8/3B4/8/8/4K3 w - - 0 1", "d4g7", "d4h8"),
        ("4k3/8/8/3p4/3Q4/8/8/4K3 w - - 0 1", "d4d5", "d4d6"),
    ),
)
def test_sliders_stop_at_first_occupied_square(
    fen: str, allowed_capture: str, forbidden_beyond: str
) -> None:
    _, _, legal = legal_from_fen(fen)
    assert move(allowed_capture) in legal
    assert move(forbidden_beyond) not in legal


def test_friendly_piece_blocks_slider_but_knight_jumps() -> None:
    _, _, legal = legal_from_fen(
        "4k3/8/8/8/3R4/3P4/1N6/1B2K3 w - - 0 1"
    )
    assert move("d4d3") not in legal
    assert move("b1e4") not in legal
    assert move("b2c4") in legal


def test_check_detection_and_all_three_single_check_evasions() -> None:
    generator, state, legal = legal_from_fen(
        "k3r3/8/8/8/8/8/R6B/4K3 w - - 0 1"
    )
    assert generator.is_in_check(state)
    assert move("e1d1") in legal
    assert move("a2e2") in legal
    assert move("h2e5") in legal
    assert move("a2a3") not in legal


def test_pin_and_discovered_check_are_filtered() -> None:
    generator, state, legal = legal_from_fen(
        "k3r3/8/8/8/8/8/4R3/4K3 w - - 0 1"
    )
    assert not generator.is_in_check(state)
    assert move("e2d2") not in legal
    assert move("e2e8") in legal


def test_selected_square_generation_preserves_pin_and_check_evasions() -> None:
    mode = classic_chess()
    generator = MoveGenerator(mode)
    pinned = parse_fen("k3r3/8/8/8/8/8/4R3/4K3 w - - 0 1", mode)
    pinned_rook = set(generator.generate_legal_for_square(pinned, Square(4, 1)))
    assert move("e2d2") not in pinned_rook
    assert move("e2e8") in pinned_rook

    checked = parse_fen("k3r3/8/8/8/8/8/R6B/4K3 w - - 0 1", mode)
    rook_evasions = set(generator.generate_legal_for_square(checked, 8))
    assert move("a2e2") in rook_evasions
    assert move("a2a3") not in rook_evasions


def test_double_check_allows_only_king_moves() -> None:
    generator, state, legal = legal_from_fen(
        "k3r3/8/8/8/1b6/8/R7/4K3 w - - 0 1"
    )
    assert generator.is_in_check(state)
    assert legal
    assert all(action.from_square == Square(4, 0) for action in legal)


def test_king_cannot_move_to_attacked_square() -> None:
    _, _, legal = legal_from_fen("k7/8/8/8/8/8/3r4/4K3 w - - 0 1")
    assert move("e1e2") not in legal
    assert move("e1d1") not in legal


def test_castling_through_check_is_illegal() -> None:
    _, _, legal = legal_from_fen("k4r2/8/8/8/8/8/8/4K2R w K - 0 1")
    assert move("e1g1") not in legal


def test_en_passant_that_exposes_own_king_is_illegal() -> None:
    _, _, legal = legal_from_fen("k7/8/8/4KPpr/8/8/8/8 w - g6 0 1")
    assert move("f5g6") not in legal


@pytest.mark.parametrize(
    ("fen", "check", "checkmate", "stalemate"),
    (
        ("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1", True, True, False),
        ("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", False, False, True),
    ),
)
def test_checkmate_and_stalemate_basics(
    fen: str, check: bool, checkmate: bool, stalemate: bool
) -> None:
    generator, state, _ = legal_from_fen(fen)
    assert generator.is_in_check(state) is check
    assert generator.is_checkmate(state) is checkmate
    assert generator.is_stalemate(state) is stalemate


def test_local_game_service_plays_a_complete_scholars_mate() -> None:
    game = run_moves(
        ["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"]
    )

    assert game.status() is GameStatus.CHECKMATE
    assert game.state.side_to_move is PieceSide.BLACK
    assert parse_move("a7a8n").promotion_choice == PieceTypeId("knight")


def test_pawn_captures_double_step_and_all_promotions() -> None:
    _, _, initial = legal_from_fen(
        "4k3/8/8/8/8/3p4/2P5/4K3 w - - 0 1"
    )
    assert move("c2c4") in initial
    assert move("c2d3") in initial
    assert move("c2b3") not in initial

    _, _, promotions = legal_from_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert {
        action.promotion_choice.name
        for action in promotions
        if action.from_square == Square(0, 6)
    } == {"queen", "rook", "bishop", "knight"}

import pytest

from chess_core.core.board import Board, BoardShape, Square
from chess_core.core.castling import encode_castling
from chess_core.core.chess960 import (
    Chess960CastlingRule,
    chess960_rook_files,
    chess960_start_cells,
    is_valid_chess960_back_rank,
    scharnagl_back_rank,
)
from chess_core.core.move import MoveAction
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import BoardState, GameState

STANDARD_BACK_RANK = (
    "rook",
    "knight",
    "bishop",
    "queen",
    "king",
    "bishop",
    "knight",
    "rook",
)


def _state_from_cells(cells: dict[int, Piece]) -> GameState:
    board = Board(BoardShape(8, 8))
    full: dict[int, Piece | None] = {index: None for index in range(64)}
    full.update(cells)
    return GameState(
        board_state=BoardState(board, full),
        side_to_move=PieceSide.WHITE,
    )


def _position_with_king_on_file(file: int) -> int:
    for position_id in range(960):
        if scharnagl_back_rank(position_id)[file] == "king":
            return position_id
    raise AssertionError(f"no Chess960 position has king on file {file}")


def test_position_518_is_standard_chess() -> None:
    assert scharnagl_back_rank(518) == STANDARD_BACK_RANK


def test_all_960_ids_produce_unique_valid_back_ranks() -> None:
    ranks = [scharnagl_back_rank(position_id) for position_id in range(960)]
    assert len(set(ranks)) == 960
    assert all(is_valid_chess960_back_rank(rank) for rank in ranks)


def test_black_mirrors_white_in_start_cells() -> None:
    cells = chess960_start_cells(0)
    for file in range(8):
        white = cells[file]
        black = cells[56 + file]
        assert white.piece_type == black.piece_type
        assert white.side is PieceSide.WHITE
        assert black.side is PieceSide.BLACK


def test_start_cells_have_32_pieces_and_pawns_on_ranks_1_and_6() -> None:
    cells = chess960_start_cells(518)
    assert len(cells) == 32
    for file in range(8):
        white_pawn = cells[8 + file]
        black_pawn = cells[48 + file]
        assert white_pawn == Piece(PieceTypeId("pawn"), PieceSide.WHITE)
        assert black_pawn == Piece(PieceTypeId("pawn"), PieceSide.BLACK)
        assert (8 + file) // 8 == 1
        assert (48 + file) // 8 == 6


@pytest.mark.parametrize("position_id", [-1, 960, 1000])
def test_invalid_position_id_raises(position_id: int) -> None:
    with pytest.raises(ValueError):
        scharnagl_back_rank(position_id)
    with pytest.raises(ValueError):
        chess960_start_cells(position_id)


def test_standard_518_white_castling_paths() -> None:
    rule = Chess960CastlingRule(chess960_rook_files(scharnagl_back_rank(518)))
    state = _state_from_cells(chess960_start_cells(518))
    kingside, queenside = rule.paths(state, PieceSide.WHITE)

    assert kingside.right == "K"
    assert kingside.king_from == Square(4, 0)
    assert kingside.king_to == Square(6, 0)
    assert kingside.rook_from == Square(7, 0)
    assert kingside.rook_to == Square(5, 0)

    assert queenside.right == "Q"
    assert queenside.king_from == Square(4, 0)
    assert queenside.king_to == Square(2, 0)
    assert queenside.rook_from == Square(0, 0)
    assert queenside.rook_to == Square(3, 0)


def test_king_on_c1_queenside_stays_and_encodes_to_rook() -> None:
    position_id = _position_with_king_on_file(2)
    back_rank = scharnagl_back_rank(position_id)
    assert back_rank[2] == "king"
    rule = Chess960CastlingRule(chess960_rook_files(back_rank))
    state = _state_from_cells(chess960_start_cells(position_id))
    paths = {path.right: path for path in rule.paths(state, PieceSide.WHITE)}
    queenside = paths["Q"]

    assert queenside.king_from == Square(2, 0)
    assert queenside.king_to == Square(2, 0)
    assert encode_castling(queenside) == MoveAction(
        queenside.king_from, queenside.rook_from
    )


def test_decode_round_trip_both_sides() -> None:
    rule = Chess960CastlingRule(chess960_rook_files(scharnagl_back_rank(518)))
    state = _state_from_cells(chess960_start_cells(518))
    for side in (PieceSide.WHITE, PieceSide.BLACK):
        for path in rule.paths(state, side):
            assert rule.decode(encode_castling(path), state) == path

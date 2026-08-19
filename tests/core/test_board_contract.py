import pytest

from chess_core.core.bitboard import BitMask, BitboardSet
from chess_core.core.board import Board, BoardShape, Square
from chess_core.core.piece import PieceSide


@pytest.mark.parametrize("files,ranks", [(8, 8), (5, 5)])
def test_square_index_round_trip(files: int, ranks: int) -> None:
    for rank in range(ranks):
        for file in range(files):
            square = Square(file=file, rank=rank)
            index = square.index(files)

            assert index == rank * files + file
            assert Square.from_index(index, files, ranks) == square


@pytest.mark.parametrize("shape", [BoardShape(8, 8), BoardShape(5, 5)])
def test_board_shape_and_all_squares_mask(shape: BoardShape) -> None:
    board = Board(shape)

    assert board.shape == shape
    assert shape.cell_count == shape.files * shape.ranks
    assert board.all_squares_mask() == (1 << shape.cell_count) - 1


@pytest.mark.parametrize("shape", [BoardShape(8, 8), BoardShape(5, 5)])
def test_board_boundaries(shape: BoardShape) -> None:
    board = Board(shape)

    assert board.is_on_board(Square(0, 0))
    assert board.is_on_board(Square(shape.files - 1, shape.ranks - 1))
    assert not board.is_on_board(Square(-1, 0))
    assert not board.is_on_board(Square(0, -1))
    assert not board.is_on_board(Square(shape.files, 0))
    assert not board.is_on_board(Square(0, shape.ranks))


@pytest.mark.parametrize("files,ranks", [(8, 8), (5, 5)])
def test_index_contract_rejects_out_of_bounds(files: int, ranks: int) -> None:
    with pytest.raises(ValueError):
        Square(-1, 0).index(files)
    with pytest.raises(ValueError):
        Square(files, 0).index(files)
    with pytest.raises(ValueError):
        Square(0, -1).index(files)
    with pytest.raises(ValueError):
        Square.from_index(-1, files, ranks)
    with pytest.raises(ValueError):
        Square.from_index(files * ranks, files, ranks)


def test_bitmask_operations_and_bitboard_set_contract() -> None:
    first = BitMask(0b1011)
    second = BitMask(0b0110)

    assert (first & second).value == 0b0010
    assert first.intersect(second).value == 0b0010
    assert (first | second).value == 0b1111
    assert first.union(second).value == 0b1111
    assert first.without(second).value == 0b1001
    assert (~BitMask(0)).value == -1

    masks = BitboardSet()
    masks.set_mask("all", 0b1111)

    assert masks.get_mask("all") == 0b1111
    assert masks.mask_for_square(0) == 0b0001
    assert masks.mask_for_square(4) == 0b10000
    with pytest.raises(ValueError):
        masks.mask_for_square(-1)


def test_piece_side_geometry() -> None:
    assert PieceSide.WHITE.opponent() is PieceSide.BLACK
    assert PieceSide.BLACK.opponent() is PieceSide.WHITE
    assert PieceSide.WHITE.forward_delta() == 1
    assert PieceSide.BLACK.forward_delta() == -1
    assert PieceSide.WHITE.last_rank(8) == 7
    assert PieceSide.BLACK.last_rank(8) == 0
    assert PieceSide.WHITE.ranks_ahead(6, 8) == 1
    assert PieceSide.BLACK.ranks_ahead(1, 8) == 1
    with pytest.raises(ValueError):
        PieceSide.NEUTRAL.opponent()

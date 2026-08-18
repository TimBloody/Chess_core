from chess_core.core.board import BoardShape, Square
from chess_core.core.topology import (
    AdjacencyMap,
    CylindricalFilesTopology,
    FlatTopology,
    PortalLink,
    PortalTopology,
)


def _mask_for(shape: BoardShape, squares: set[Square]) -> int:
    return sum(1 << square.index(shape.files) for square in squares)


def test_flat_neighbors_for_e4_are_eight_adjacent_squares() -> None:
    shape = BoardShape(files=8, ranks=8)
    topology = FlatTopology(shape)
    square = Square(file=4, rank=3)

    expected = {
        Square(file=3, rank=2),
        Square(file=4, rank=2),
        Square(file=5, rank=2),
        Square(file=3, rank=3),
        Square(file=5, rank=3),
        Square(file=3, rank=4),
        Square(file=4, rank=4),
        Square(file=5, rank=4),
    }

    assert topology.neighbors(square).value == _mask_for(shape, expected)


def test_adjacency_map_precomputes_neighbors_by_square_index() -> None:
    shape = BoardShape(files=8, ranks=8)
    topology = FlatTopology(shape)
    square = Square(file=4, rank=3)
    adjacency = AdjacencyMap(shape, topology)

    assert adjacency.neighbors_of(square.index(shape.files)) == topology.neighbors(square).value


def test_cylinder_wraps_file_zero_left_to_last_file() -> None:
    shape = BoardShape(files=8, ranks=8)
    topology = CylindricalFilesTopology(shape)

    assert topology.step(Square(file=0, rank=3), (-1, 0)) == Square(file=7, rank=3)


def test_cylinder_rook_rank_ray_from_a_file_includes_h_file() -> None:
    shape = BoardShape(files=8, ranks=8)
    topology = CylindricalFilesTopology(shape)
    current = Square(file=0, rank=3)
    ray: list[Square] = []

    for _ in range(shape.files - 1):
        next_square = topology.step(current, (-1, 0))
        assert next_square is not None

        ray.append(next_square)
        current = next_square

    assert Square(file=7, rank=3) in ray


def test_portal_step_can_replace_off_board_step() -> None:
    shape = BoardShape(files=8, ranks=8)
    source = Square(file=7, rank=7)
    target = Square(file=0, rank=0)
    topology = PortalTopology(shape, (PortalLink(source, target),))

    assert topology.step(source, (1, 0)) == target

from chess_core.core.board import BoardShape, Square
from chess_core.core.rays import RayBuilder
from chess_core.core.topology import CylindricalFilesTopology, FlatTopology


def _mask_for(shape: BoardShape, squares: set[Square]) -> int:
    return sum(1 << square.index(shape.files) for square in squares)


def test_flat_and_cylinder_rank_rays_from_e4_differ_at_wrapped_files() -> None:
    shape = BoardShape(files=8, ranks=8)
    origin = Square(file=4, rank=3)

    flat = RayBuilder(shape, FlatTopology(shape))
    cylinder = RayBuilder(shape, CylindricalFilesTopology(shape))

    flat_east = flat.build_line(origin, (1, 0)).mask
    cylinder_east = cylinder.build_line(origin, (1, 0)).mask
    flat_west = flat.build_line(origin, (-1, 0)).mask
    cylinder_west = cylinder.build_line(origin, (-1, 0)).mask

    assert origin.index(shape.files) == 28
    assert flat_east == _mask_for(
        shape,
        {Square(5, 3), Square(6, 3), Square(7, 3)},
    )
    assert cylinder_east == _mask_for(
        shape,
        {
            Square(5, 3),
            Square(6, 3),
            Square(7, 3),
            Square(0, 3),
            Square(1, 3),
            Square(2, 3),
            Square(3, 3),
        },
    )
    assert flat_west == _mask_for(
        shape,
        {Square(3, 3), Square(2, 3), Square(1, 3), Square(0, 3)},
    )
    assert cylinder_west == _mask_for(
        shape,
        {
            Square(3, 3),
            Square(2, 3),
            Square(1, 3),
            Square(0, 3),
            Square(7, 3),
            Square(6, 3),
            Square(5, 3),
        },
    )
    assert flat_east != cylinder_east
    assert flat_west != cylinder_west


def test_flat_and_cylinder_file_rays_from_e4_are_equal() -> None:
    shape = BoardShape(files=8, ranks=8)
    origin = Square(file=4, rank=3)

    flat_table = RayBuilder(shape, FlatTopology(shape)).build_all_directions(((0, 1), (0, -1)))
    cylinder_table = RayBuilder(
        shape,
        CylindricalFilesTopology(shape),
    ).build_all_directions(((0, 1), (0, -1)))

    assert flat_table.ray_mask(28, (0, 1)) == cylinder_table.ray_mask(28, (0, 1))
    assert flat_table.ray_mask(28, (0, -1)) == cylinder_table.ray_mask(28, (0, -1))

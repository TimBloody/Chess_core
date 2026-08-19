from random import Random

import pytest

from chess_core.app.training.maze import (
    MazeMoveResult,
    MazePuzzle,
    MazeSession,
    MazeStatus,
    generate_maze,
    solve_maze,
)


def _rook_file_puzzle(*, blocked: bool) -> MazePuzzle:
    obstacles = frozenset({8}) if blocked else frozenset()  # a2
    return MazePuzzle(
        piece_type="rook",
        start=0,  # a1
        obstacles=obstacles,
        targets={56: "pawn"},  # a8
    )


def test_rook_captures_along_an_open_file() -> None:
    session = MazeSession.start(_rook_file_puzzle(blocked=False))
    dests = session.legal_destinations()

    assert 56 in dests
    assert 8 in dests
    assert session.try_move(56) is MazeMoveResult.WON
    assert session.status is MazeStatus.WON
    assert session.hero_square == 56
    assert session.remaining == {}


def test_obstacle_blocks_sliding_and_landing() -> None:
    session = MazeSession.start(_rook_file_puzzle(blocked=True))
    dests = session.legal_destinations()

    assert 8 not in dests
    assert 16 not in dests
    assert 56 not in dests
    assert 7 in dests  # h1
    assert session.try_move(56) is MazeMoveResult.ILLEGAL


def test_avoid_checks_rejects_squares_attacked_by_remaining_pieces() -> None:
    puzzle = MazePuzzle(
        piece_type="knight",
        start=1,  # b1
        obstacles=frozenset(),
        targets={10: "queen", 16: "pawn"},  # c2 queen, a3 pawn
        avoid_checks=True,
    )
    session = MazeSession.start(puzzle)
    dests = session.legal_destinations()

    assert 18 not in dests  # c3, attacked by the queen
    assert 11 not in dests  # d2, attacked by the queen
    assert 16 in dests  # capture the pawn, a3 is not attacked after the queen stays on c2
    assert session.try_move(18) is MazeMoveResult.UNDER_FIRE
    assert session.try_move(16) is MazeMoveResult.CAPTURED
    assert 16 not in session.remaining
    assert session.status is MazeStatus.PLAYING


def test_generated_maze_is_solvable_with_seed() -> None:
    puzzle = generate_maze(
        piece_type="knight",
        target_count=3,
        obstacle_count=6,
        avoid_checks=False,
        rng=Random(42),
    )
    path = solve_maze(puzzle)
    assert path is not None
    session = MazeSession.start(puzzle)
    for dest in path:
        result = session.try_move(dest)
        assert result in {
            MazeMoveResult.MOVED,
            MazeMoveResult.CAPTURED,
            MazeMoveResult.WON,
        }
    assert session.status is MazeStatus.WON


def test_generated_hard_maze_never_steps_into_check() -> None:
    puzzle = generate_maze(
        piece_type="bishop",
        target_count=2,
        obstacle_count=4,
        avoid_checks=True,
        rng=Random(9),
    )
    path = solve_maze(puzzle)
    assert path is not None
    session = MazeSession.start(puzzle)
    for dest in path:
        assert dest in session.legal_destinations()
        session.try_move(dest)
    assert session.status is MazeStatus.WON


def _hard_maze_constraints(puzzle: MazePuzzle) -> None:
    assert puzzle.piece_type not in puzzle.targets.values()
    if puzzle.piece_type != "knight":
        assert "queen" not in puzzle.targets.values()
    if puzzle.piece_type == "bishop":
        start_color = ((puzzle.start % 8) + (puzzle.start // 8)) % 2
        for square in puzzle.targets:
            assert ((square % 8) + (square // 8)) % 2 == start_color
    path = solve_maze(puzzle)
    assert path is not None
    session = MazeSession.start(puzzle)
    assert session.legal_destinations()
    for dest in path:
        result = session.try_move(dest)
        assert result is not MazeMoveResult.UNDER_FIRE
        assert result is not MazeMoveResult.ILLEGAL
    assert session.status is MazeStatus.WON


def test_avoid_checks_mazes_are_constructed_solvable_for_every_hero() -> None:
    for piece_index, piece_type in enumerate(
        ("knight", "bishop", "rook", "queen", "king")
    ):
        for seed in range(5):
            puzzle = generate_maze(
                piece_type=piece_type,
                target_count=3,
                obstacle_count=6,
                avoid_checks=True,
                rng=Random(1000 * piece_index + seed),
            )
            _hard_maze_constraints(puzzle)


def test_easy_mazes_stay_solvable_without_check_filter() -> None:
    puzzle = generate_maze(
        piece_type="rook",
        target_count=4,
        obstacle_count=8,
        avoid_checks=False,
        rng=Random(3),
    )
    assert solve_maze(puzzle) is not None
    assert puzzle.piece_type not in puzzle.targets.values()
    assert "queen" not in puzzle.targets.values()

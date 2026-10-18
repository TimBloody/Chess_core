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
    assert 8 not in dests
    assert session.try_move(8) is MazeMoveResult.ILLEGAL
    assert session.try_move(56) is MazeMoveResult.WON
    assert session.status is MazeStatus.WON
    assert session.hero_square == 56
    assert session.remaining == {}


def test_forced_capture_order_on_a_blocked_file() -> None:
    puzzle = MazePuzzle(
        piece_type="rook",
        start=0,
        obstacles=frozenset(),
        targets={24: "pawn", 56: "pawn"},
    )
    session = MazeSession.start(puzzle)

    assert session.legal_destinations() == {24}
    assert session.try_move(56) is MazeMoveResult.ILLEGAL
    assert session.try_move(24) is MazeMoveResult.CAPTURED
    assert session.legal_destinations() == {56}
    assert session.try_move(56) is MazeMoveResult.WON


def test_obstacle_blocks_sliding_and_landing() -> None:
    blocked = _rook_file_puzzle(blocked=True)
    puzzle = MazePuzzle(
        piece_type=blocked.piece_type,
        start=blocked.start,
        obstacles=blocked.obstacles,
        targets=blocked.targets,
        captures_only=False,
    )
    session = MazeSession.start(puzzle)
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
        targets={10: "queen", 18: "pawn", 16: "pawn"},  # c2 queen, c3 pawn, a3 pawn
        avoid_checks=True,
    )
    session = MazeSession.start(puzzle)
    dests = session.legal_destinations()

    assert 18 not in dests  # c3, attacked by the queen
    assert 11 not in dests  # d2 is empty; capture-only mazes ignore it
    assert 16 in dests  # capture the pawn; a3 is not attacked after the queen stays on c2
    assert session.capture_destinations() >= {16, 18}
    assert session.try_move(18) is MazeMoveResult.UNDER_FIRE
    assert session.try_move(16) is MazeMoveResult.CAPTURED
    assert 16 not in session.remaining
    assert session.status is MazeStatus.PLAYING


def test_undo_restores_hero_and_remaining_targets() -> None:
    session = MazeSession.start(_rook_file_puzzle(blocked=False))
    assert session.try_move(56) is MazeMoveResult.WON
    assert session.hero_square == 56
    assert session.can_undo
    assert session.undo()
    assert session.hero_square == 0
    assert session.remaining == {56: "pawn"}
    assert session.move_count == 0
    assert session.status is MazeStatus.PLAYING
    assert not session.can_undo
    assert session.try_move(56) is MazeMoveResult.WON


def test_reset_replays_the_same_puzzle() -> None:
    session = MazeSession.start(_rook_file_puzzle(blocked=False))
    session.try_move(56)
    session.reset()
    assert session.hero_square == 0
    assert session.remaining == {56: "pawn"}
    assert session.status is MazeStatus.PLAYING
    assert session.move_count == 0
    assert not session.can_undo


def test_puzzle_rejects_overlapping_squares() -> None:
    with pytest.raises(ValueError, match="overlap"):
        MazePuzzle(
            piece_type="knight",
            start=0,
            obstacles=frozenset({10}),
            targets={10: "pawn"},
        )
    with pytest.raises(ValueError, match="hero cannot start"):
        MazePuzzle(
            piece_type="knight",
            start=10,
            obstacles=frozenset(),
            targets={10: "pawn"},
        )


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
    assert len(path) == 3
    assert all(dest in puzzle.targets for dest in path)
    session = MazeSession.start(puzzle)
    for dest in path:
        result = session.try_move(dest)
        assert result in {MazeMoveResult.CAPTURED, MazeMoveResult.WON}
        assert result is not MazeMoveResult.MOVED
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
    path = solve_maze(puzzle)
    assert path is not None
    assert len(path) == 4
    assert all(dest in puzzle.targets for dest in path)
    assert puzzle.captures_only
    assert puzzle.piece_type not in puzzle.targets.values()
    assert "queen" not in puzzle.targets.values()


def _turn_count(start: int, path: list[int], files: int = 8) -> int:
    squares = [start, *path]
    turns = 0
    previous: tuple[int, int] | None = None
    for origin, dest in zip(squares, squares[1:]):
        delta_file = (dest % files) - (origin % files)
        delta_rank = (dest // files) - (origin // files)
        if delta_file == 0 and delta_rank == 0:
            continue
        if delta_file == 0 or delta_rank == 0 or abs(delta_file) == abs(delta_rank):
            steps = max(abs(delta_file), abs(delta_rank))
            current = (delta_file // steps, delta_rank // steps)
        else:
            current = (delta_file, delta_rank)
        if previous is not None and current != previous and current != (
            -previous[0],
            -previous[1],
        ):
            turns += 1
        previous = current
    return turns


def test_sliding_routes_change_direction_without_check_filter() -> None:
    for piece_type in ("rook", "bishop", "queen"):
        for seed in range(6):
            puzzle = generate_maze(
                piece_type=piece_type,
                target_count=6,
                obstacle_count=8,
                avoid_checks=False,
                rng=Random(seed),
            )
            path = solve_maze(puzzle)
            assert path is not None
            assert len(path) == 6
            assert _turn_count(puzzle.start, path, puzzle.files) >= 4


def test_rook_route_still_turns_when_checks_are_forbidden() -> None:
    for seed in range(8):
        puzzle = generate_maze(
            piece_type="rook",
            target_count=6,
            obstacle_count=4,
            avoid_checks=True,
            rng=Random(seed),
        )
        path = solve_maze(puzzle)
        assert path is not None
        assert len(path) == 6
        assert _turn_count(puzzle.start, path, puzzle.files) >= 3


def test_generated_maze_offers_decoy_captures() -> None:
    decoy_plies = 0
    for seed in range(12):
        puzzle = generate_maze(
            piece_type="knight",
            target_count=4,
            obstacle_count=4,
            avoid_checks=True,
            rng=Random(50 + seed),
        )
        path = solve_maze(puzzle)
        assert path is not None
        session = MazeSession.start(puzzle)
        for dest in path:
            if len(session.capture_destinations()) >= 2:
                decoy_plies += 1
            assert dest in session.legal_destinations()
            session.try_move(dest)
        assert session.status is MazeStatus.WON
        if decoy_plies:
            break
    assert decoy_plies >= 1

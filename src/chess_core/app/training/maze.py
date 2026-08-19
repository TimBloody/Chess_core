"""Piece maze: capture every black piece, obstacles block landing and sliding.

Hard mode (Train with Magnus style) forbids standing on a square attacked by
any remaining black piece. Black pieces are static; they only attack.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from random import Random

from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import MoveAction
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import BoardState, GameState
from chess_core.modes.chess import classic_chess

MAZE_HERO_TYPES = ("knight", "bishop", "rook", "queen", "king")
_BLOCKER_TYPE = PieceTypeId("blocker")


class MazeStatus(str, Enum):
    PLAYING = "playing"
    WON = "won"
    STUCK = "stuck"


class MazeMoveResult(str, Enum):
    MOVED = "moved"
    CAPTURED = "captured"
    WON = "won"
    ILLEGAL = "illegal"
    UNDER_FIRE = "under_fire"
    STUCK = "stuck"


@dataclass(frozen=True)
class MazePuzzle:
    piece_type: str
    start: int
    obstacles: frozenset[int]
    targets: dict[int, str]
    avoid_checks: bool = False
    files: int = 8
    ranks: int = 8

    def __post_init__(self) -> None:
        cell_count = self.files * self.ranks
        occupied = {self.start, *self.obstacles, *self.targets}
        if self.start in self.obstacles or self.start in self.targets:
            raise ValueError("hero cannot start on an obstacle or target")
        if self.obstacles & self.targets.keys():
            raise ValueError("obstacle and target squares overlap")
        if any(not 0 <= index < cell_count for index in occupied):
            raise ValueError("maze square is outside the board")
        if self.piece_type not in MAZE_HERO_TYPES:
            raise ValueError(f"unsupported maze piece {self.piece_type!r}")
        if not self.targets:
            raise ValueError("maze needs at least one black piece to capture")


@dataclass
class MazeSession:
    puzzle: MazePuzzle
    hero_square: int
    remaining: dict[int, str]
    status: MazeStatus = MazeStatus.PLAYING
    move_count: int = 0
    _mode: GameMode = field(default_factory=classic_chess, repr=False)
    _generator: MoveGenerator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._generator = MoveGenerator(self._mode)
        if self.status is MazeStatus.PLAYING and not self.legal_destinations():
            self.status = MazeStatus.STUCK if self.remaining else MazeStatus.WON

    @classmethod
    def start(cls, puzzle: MazePuzzle, mode: GameMode | None = None) -> "MazeSession":
        return cls(
            puzzle=puzzle,
            hero_square=puzzle.start,
            remaining=dict(puzzle.targets),
            _mode=mode or classic_chess(),
        )

    def legal_destinations(self) -> set[int]:
        if self.status is not MazeStatus.PLAYING:
            return set()
        state = self._state()
        dests = _destinations(self._generator, state, self.hero_square)
        if not self.puzzle.avoid_checks:
            return dests
        return {
            dest
            for dest in dests
            if not _landing_is_attacked(
                self._generator, state, dest, self.puzzle.files, self.puzzle.ranks
            )
        }

    def try_move(self, dest: int) -> MazeMoveResult:
        if self.status is not MazeStatus.PLAYING:
            return MazeMoveResult.ILLEGAL
        if dest not in self.legal_destinations():
            if dest in _destinations(self._generator, self._state(), self.hero_square):
                return MazeMoveResult.UNDER_FIRE
            return MazeMoveResult.ILLEGAL
        captured = dest in self.remaining
        if captured:
            del self.remaining[dest]
        self.hero_square = dest
        self.move_count += 1
        if not self.remaining:
            self.status = MazeStatus.WON
            return MazeMoveResult.WON
        if not self.legal_destinations():
            self.status = MazeStatus.STUCK
            return MazeMoveResult.STUCK
        return MazeMoveResult.CAPTURED if captured else MazeMoveResult.MOVED

    def _state(self) -> GameState:
        return _maze_state(
            self._mode,
            self.hero_square,
            self.puzzle.piece_type,
            self.remaining,
            self.puzzle.obstacles,
        )


def generate_maze(
    *,
    piece_type: str = "knight",
    target_count: int = 4,
    obstacle_count: int = 8,
    avoid_checks: bool = False,
    rng: Random | None = None,
    max_attempts: int = 24,
) -> MazePuzzle:
    """Build a maze from a known solution, walking the hero backwards.

    Black pieces are dropped on the square the hero is leaving, then the hero
    steps to a previous square. Later captures are placed first, so each new
    victim is unprotected by pieces that will still be on the board. That
    makes avoid-check mazes solvable without rejection sampling of random
    boards, and it prevents mutual-defence pairs (two rooks covering each
    other, and the like).
    """

    if piece_type not in MAZE_HERO_TYPES:
        raise ValueError(f"unsupported maze piece {piece_type!r}")
    if target_count < 1:
        raise ValueError("target_count must be positive")
    if obstacle_count < 0:
        raise ValueError("obstacle_count must be non-negative")
    rng = rng or Random()
    mode = classic_chess()
    generator = MoveGenerator(mode)
    for _ in range(max_attempts):
        puzzle = _build_maze_from_solution(
            generator,
            mode,
            piece_type=piece_type,
            target_count=target_count,
            obstacle_count=obstacle_count,
            avoid_checks=avoid_checks,
            rng=rng,
        )
        if puzzle is not None:
            return puzzle
    raise RuntimeError("could not construct a solvable maze")


def solve_maze(puzzle: MazePuzzle, mode: GameMode | None = None) -> list[int] | None:
    """Return destination squares of a solution, or None if unsolvable."""

    mode = mode or classic_chess()
    generator = MoveGenerator(mode)
    start = (puzzle.start, frozenset(puzzle.targets))
    queue: deque[tuple[int, frozenset[int], list[int]]] = deque()
    queue.append((puzzle.start, frozenset(puzzle.targets), []))
    seen = {start}
    while queue:
        hero, remaining_keys, path = queue.popleft()
        remaining = {index: puzzle.targets[index] for index in remaining_keys}
        state = _maze_state(mode, hero, puzzle.piece_type, remaining, puzzle.obstacles)
        dests = _destinations(generator, state, hero)
        if puzzle.avoid_checks:
            dests = {
                dest
                for dest in dests
                if not _landing_is_attacked(
                    generator, state, dest, puzzle.files, puzzle.ranks
                )
            }
        for dest in dests:
            next_remaining = set(remaining_keys)
            next_remaining.discard(dest)
            key = (dest, frozenset(next_remaining))
            if key in seen:
                continue
            next_path = path + [dest]
            if not next_remaining:
                return next_path
            seen.add(key)
            queue.append((dest, frozenset(next_remaining), next_path))
    return None


def _build_maze_from_solution(
    generator: MoveGenerator,
    mode: GameMode,
    *,
    piece_type: str,
    target_count: int,
    obstacle_count: int,
    avoid_checks: bool,
    rng: Random,
) -> MazePuzzle | None:
    files = mode.board.shape.files
    ranks = mode.board.shape.ranks
    cell_count = mode.board.shape.cell_count
    endpoint = rng.randrange(cell_count)
    obstacles = _place_obstacles(
        cell_count,
        files,
        endpoint,
        piece_type,
        obstacle_count,
        rng,
    )
    hero = endpoint
    targets: dict[int, str] = {}
    remaining_captures = target_count
    remaining_quiets = max(3, target_count)
    for _ in range(target_count * 10 + 20):
        if remaining_captures <= 0 and remaining_quiets <= 0:
            break
        captured = False
        prefer_capture = remaining_captures > 0 and (
            remaining_quiets <= 0 or rng.random() < 0.55
        )
        if prefer_capture:
            nxt = _reverse_capture(
                generator,
                mode,
                piece_type,
                hero,
                targets,
                obstacles,
                avoid_checks,
                rng,
            )
            if nxt is not None:
                hero, targets = nxt
                remaining_captures -= 1
                captured = True
        if captured:
            continue
        nxt = _reverse_quiet(
            generator,
            mode,
            piece_type,
            hero,
            targets,
            obstacles,
            avoid_checks,
            rng,
        )
        if nxt is not None:
            hero = nxt
            if remaining_quiets > 0:
                remaining_quiets -= 1
            continue
        if remaining_captures > 0:
            nxt = _reverse_capture(
                generator,
                mode,
                piece_type,
                hero,
                targets,
                obstacles,
                avoid_checks,
                rng,
            )
            if nxt is not None:
                hero, targets = nxt
                remaining_captures -= 1
                continue
        break
    if remaining_captures > 0 or not targets or hero in targets:
        return None
    if avoid_checks and _attacked_by_black(
        generator, mode, piece_type, targets, obstacles, hero, files, ranks
    ):
        return None
    return MazePuzzle(
        piece_type=piece_type,
        start=hero,
        obstacles=frozenset(obstacles),
        targets=targets,
        avoid_checks=avoid_checks,
        files=files,
        ranks=ranks,
    )


def _target_types_for(hero_type: str) -> tuple[str, ...]:
    pool = ["pawn", "knight", "bishop", "rook"]
    if hero_type == "knight":
        pool.append("queen")
    return tuple(name for name in pool if name != hero_type)


def _square_color(index: int, files: int) -> int:
    return ((index % files) + (index // files)) % 2


def _place_obstacles(
    cell_count: int,
    files: int,
    endpoint: int,
    piece_type: str,
    obstacle_count: int,
    rng: Random,
) -> set[int]:
    candidates = [index for index in range(cell_count) if index != endpoint]
    cap = min(obstacle_count, max(0, len(candidates) - 16))
    if cap <= 0:
        return set()
    if piece_type == "bishop":
        color = _square_color(endpoint, files)
        same = [
            index for index in candidates if _square_color(index, files) == color
        ]
        other = [index for index in candidates if _square_color(index, files) != color]
        rng.shuffle(same)
        rng.shuffle(other)
        max_same = max(0, len(same) - 10)
        n_same = min(cap, max_same)
        blocked = set(same[:n_same])
        blocked.update(other[: cap - len(blocked)])
        return blocked
    rng.shuffle(candidates)
    return set(candidates[:cap])


def _reverse_origins(
    generator: MoveGenerator,
    mode: GameMode,
    piece_type: str,
    hero: int,
    targets: dict[int, str],
    obstacles: set[int],
) -> list[int]:
    state = _maze_state(mode, hero, piece_type, targets, obstacles)
    return sorted(
        dest
        for dest in _destinations(generator, state, hero)
        if dest not in targets and dest not in obstacles
    )


def _reverse_quiet(
    generator: MoveGenerator,
    mode: GameMode,
    piece_type: str,
    hero: int,
    targets: dict[int, str],
    obstacles: set[int],
    avoid_checks: bool,
    rng: Random,
) -> int | None:
    files = mode.board.shape.files
    ranks = mode.board.shape.ranks
    if avoid_checks and _attacked_by_black(
        generator, mode, piece_type, targets, obstacles, hero, files, ranks
    ):
        return None
    origins = _reverse_origins(generator, mode, piece_type, hero, targets, obstacles)
    if avoid_checks:
        origins = [
            origin
            for origin in origins
            if not _attacked_by_black(
                generator, mode, piece_type, targets, obstacles, origin, files, ranks
            )
        ]
    if not origins:
        return None
    return rng.choice(origins)


def _reverse_capture(
    generator: MoveGenerator,
    mode: GameMode,
    piece_type: str,
    hero: int,
    targets: dict[int, str],
    obstacles: set[int],
    avoid_checks: bool,
    rng: Random,
) -> tuple[int, dict[int, str]] | None:
    if hero in targets:
        return None
    files = mode.board.shape.files
    ranks = mode.board.shape.ranks
    if avoid_checks and _attacked_by_black(
        generator, mode, piece_type, targets, obstacles, hero, files, ranks
    ):
        return None
    origins = _reverse_origins(generator, mode, piece_type, hero, targets, obstacles)
    if not origins:
        return None
    types = list(_target_types_for(piece_type))
    rng.shuffle(types)
    rng.shuffle(origins)
    for type_name in types:
        trial = dict(targets)
        trial[hero] = type_name
        safe_origins = origins
        if avoid_checks:
            safe_origins = [
                origin
                for origin in origins
                if not _attacked_by_black(
                    generator, mode, piece_type, trial, obstacles, origin, files, ranks
                )
            ]
        if not safe_origins:
            continue
        return rng.choice(safe_origins), trial
    return None


def _attacked_by_black(
    generator: MoveGenerator,
    mode: GameMode,
    piece_type: str,
    targets: dict[int, str],
    obstacles: set[int] | frozenset[int],
    square: int,
    files: int,
    ranks: int,
) -> bool:
    if square in targets:
        remaining = dict(targets)
        del remaining[square]
    else:
        remaining = targets
    state = _maze_state(mode, square, piece_type, remaining, obstacles)
    return generator.is_square_attacked(
        state, Square.from_index(square, files, ranks), PieceSide.BLACK
    )


def _maze_state(
    mode: GameMode,
    hero_square: int,
    piece_type: str,
    targets: dict[int, str],
    obstacles: frozenset[int] | set[int],
) -> GameState:
    cells: dict[int, Piece | None] = {
        index: None for index in range(mode.board.shape.cell_count)
    }
    cells[hero_square] = Piece(PieceTypeId(piece_type), PieceSide.WHITE)
    for index, type_name in targets.items():
        cells[index] = Piece(PieceTypeId(type_name), PieceSide.BLACK)
    for index in obstacles:
        cells[index] = Piece(_BLOCKER_TYPE, PieceSide.NEUTRAL)
    return GameState(
        board_state=BoardState(board=mode.board, cells=cells),
        side_to_move=PieceSide.WHITE,
        extras={"mode": mode},
    )


def _destinations(generator: MoveGenerator, state: GameState, hero: int) -> set[int]:
    files = state.board_state.board.shape.files
    dests: set[int] = set()
    for action in generator.generate_pseudo_legal(state):
        if not isinstance(action, MoveAction):
            continue
        if action.from_square.index(files) != hero:
            continue
        dests.add(action.to_square.index(files))
    return dests


def _landing_is_attacked(
    generator: MoveGenerator,
    state: GameState,
    dest: int,
    files: int,
    ranks: int,
) -> bool:
    probe = state.clone(include_history=False)
    occupant = probe.board_state.cells.get(dest)
    if occupant is not None and occupant.side is PieceSide.BLACK:
        probe.board_state.cells[dest] = None
    hero = None
    origin = None
    for index, piece in probe.board_state.iter_occupied():
        if piece.side is PieceSide.WHITE:
            hero = piece
            origin = index
            break
    if hero is None or origin is None:
        return True
    probe.board_state.cells[origin] = None
    probe.board_state.cells[dest] = hero
    return generator.is_square_attacked(
        probe, Square.from_index(dest, files, ranks), PieceSide.BLACK
    )

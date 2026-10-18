"""Piece maze: capture every black piece in order; obstacles block landing and sliding.

Default puzzles are capture chains (Magnus Trainer style): every ply takes a
piece, quiet moves onto empty squares are illegal, and the generator prefers
positions whose capture order is unique. Each step of that chain changes
direction when it can, so a rook, bishop, or queen traces a route instead of
one straight line. Hard mode also forbids standing on a square attacked by any
remaining black piece. Black pieces are static; they only attack.
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
    captures_only: bool = True
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


@dataclass(frozen=True)
class _MazeSnapshot:
    hero_square: int
    remaining: dict[int, str]
    status: MazeStatus
    move_count: int


@dataclass
class MazeSession:
    puzzle: MazePuzzle
    hero_square: int
    remaining: dict[int, str]
    status: MazeStatus = MazeStatus.PLAYING
    move_count: int = 0
    _mode: GameMode = field(default_factory=classic_chess, repr=False)
    _generator: MoveGenerator = field(init=False, repr=False)
    _history: list[_MazeSnapshot] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._generator = MoveGenerator(self._mode)
        self.remaining = dict(self.remaining)
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

    def reset(self) -> None:
        self.hero_square = self.puzzle.start
        self.remaining = dict(self.puzzle.targets)
        self.status = MazeStatus.PLAYING
        self.move_count = 0
        self._history.clear()
        if not self.legal_destinations():
            self.status = MazeStatus.STUCK if self.remaining else MazeStatus.WON

    def legal_destinations(self) -> set[int]:
        if self.status is not MazeStatus.PLAYING:
            return set()
        return _legal_destinations(
            self._generator,
            self._mode,
            self.puzzle,
            self.hero_square,
            self.remaining,
        )

    def capture_destinations(self) -> set[int]:
        """Captures the hero can make, including landings that are under fire."""
        if self.status is not MazeStatus.PLAYING:
            return set()
        raw = _destinations(self._generator, self._state(), self.hero_square)
        if self.puzzle.captures_only:
            return raw & set(self.remaining)
        return raw

    def try_move(self, dest: int) -> MazeMoveResult:
        if self.status is not MazeStatus.PLAYING:
            return MazeMoveResult.ILLEGAL
        raw = _destinations(self._generator, self._state(), self.hero_square)
        useful = raw & set(self.remaining) if self.puzzle.captures_only else raw
        if dest not in useful:
            return MazeMoveResult.ILLEGAL
        if dest not in self.legal_destinations():
            return MazeMoveResult.UNDER_FIRE
        snapshot = _MazeSnapshot(
            hero_square=self.hero_square,
            remaining=dict(self.remaining),
            status=self.status,
            move_count=self.move_count,
        )
        captured = dest in self.remaining
        if captured:
            del self.remaining[dest]
        self.hero_square = dest
        self.move_count += 1
        self._history.append(snapshot)
        if not self.remaining:
            self.status = MazeStatus.WON
            return MazeMoveResult.WON
        if not self.legal_destinations():
            self.status = MazeStatus.STUCK
            return MazeMoveResult.STUCK
        return MazeMoveResult.CAPTURED if captured else MazeMoveResult.MOVED

    @property
    def can_undo(self) -> bool:
        return bool(self._history)

    def undo(self) -> bool:
        if not self._history:
            return False
        snapshot = self._history.pop()
        self.hero_square = snapshot.hero_square
        self.remaining = dict(snapshot.remaining)
        self.status = snapshot.status
        self.move_count = snapshot.move_count
        return True

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
    captures_only: bool = True,
    rng: Random | None = None,
    max_attempts: int = 100,
) -> MazePuzzle:
    """Build a maze from a known solution, walking the hero backwards.

    Black pieces are dropped on the square the hero is leaving, then the hero
    steps to a previous square. Capture-only mazes never insert quiet steps.
    Consecutive steps change direction when a legal previous square exists, so
    the captures form a route. Among those squares, origins that also see other
    remaining pieces are preferred: those extra captures are decoys (often
    hanging under fire), so several takes look possible while only one order
    stays safe and solvable.
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
    best: tuple[int, int, int, MazePuzzle] | None = None
    want_decoys = max(1, target_count // 2) if captures_only and target_count >= 2 else 0
    want_turns = max(0, target_count - 2) if target_count >= 3 else 0
    for _ in range(max_attempts):
        puzzle = _build_maze_from_solution(
            generator,
            mode,
            piece_type=piece_type,
            target_count=target_count,
            obstacle_count=obstacle_count,
            avoid_checks=avoid_checks,
            captures_only=captures_only,
            rng=rng,
        )
        if puzzle is None:
            continue
        path = solve_maze(puzzle, mode)
        if path is None:
            continue
        if captures_only and (
            len(path) != target_count or any(dest not in puzzle.targets for dest in path)
        ):
            continue
        unique = 1 if (not captures_only or _count_solutions(puzzle, mode, limit=2) == 1) else 0
        decoys = _decoy_plies(puzzle, path, mode)
        turns = _path_turn_count(puzzle.start, path, puzzle.files)
        rank = (turns, unique, decoys)
        if best is None or rank > best[:3]:
            best = (turns, unique, decoys, puzzle)
        full_route = turns >= max(0, target_count - 1)
        if unique and turns >= want_turns and (full_route or decoys >= want_decoys):
            return puzzle
    if best is not None:
        return best[3]
    raise RuntimeError("could not construct a solvable maze")


def _decoy_plies(
    puzzle: MazePuzzle, path: list[int], mode: GameMode | None = None
) -> int:
    """How many solution plies offer more than one capture (safe or hanging)."""

    mode = mode or classic_chess()
    generator = MoveGenerator(mode)
    hero = puzzle.start
    remaining = dict(puzzle.targets)
    decoys = 0
    for dest in path:
        raw = _capture_targets_from(
            generator, mode, puzzle.piece_type, hero, remaining, puzzle.obstacles
        )
        if len(raw) >= 2:
            decoys += 1
        remaining.pop(dest, None)
        hero = dest
    return decoys


def solve_maze(puzzle: MazePuzzle, mode: GameMode | None = None) -> list[int] | None:
    """Return destination squares of a solution, or None if unsolvable."""

    found = _search_solutions(puzzle, mode, limit=1)
    return found[0] if found else None


def _count_solutions(
    puzzle: MazePuzzle, mode: GameMode | None = None, *, limit: int = 8
) -> int:
    if not puzzle.captures_only:
        return len(_search_solutions(puzzle, mode, limit=limit))
    mode = mode or classic_chess()
    generator = MoveGenerator(mode)
    found = 0

    def walk(hero: int, remaining: dict[int, str]) -> None:
        nonlocal found
        if found >= limit:
            return
        dests = _legal_destinations(generator, mode, puzzle, hero, remaining)
        for dest in dests:
            if found >= limit:
                return
            nxt = dict(remaining)
            nxt.pop(dest, None)
            if not nxt:
                found += 1
                continue
            walk(dest, nxt)

    walk(puzzle.start, dict(puzzle.targets))
    return found


def _search_solutions(
    puzzle: MazePuzzle, mode: GameMode | None, *, limit: int
) -> list[list[int]]:
    mode = mode or classic_chess()
    generator = MoveGenerator(mode)
    queue: deque[tuple[int, frozenset[int], list[int]]] = deque()
    queue.append((puzzle.start, frozenset(puzzle.targets), []))
    seen = {(puzzle.start, frozenset(puzzle.targets))}
    found: list[list[int]] = []
    while queue and len(found) < limit:
        hero, remaining_keys, path = queue.popleft()
        remaining = {index: puzzle.targets[index] for index in remaining_keys}
        dests = _legal_destinations(generator, mode, puzzle, hero, remaining)
        for dest in dests:
            next_remaining = set(remaining_keys)
            next_remaining.discard(dest)
            key = (dest, frozenset(next_remaining))
            if key in seen:
                continue
            next_path = path + [dest]
            if not next_remaining:
                found.append(next_path)
                if len(found) >= limit:
                    break
                continue
            seen.add(key)
            queue.append((dest, frozenset(next_remaining), next_path))
    return found


def _build_maze_from_solution(
    generator: MoveGenerator,
    mode: GameMode,
    *,
    piece_type: str,
    target_count: int,
    obstacle_count: int,
    avoid_checks: bool,
    captures_only: bool,
    rng: Random,
) -> MazePuzzle | None:
    if captures_only:
        return _build_capture_chain(
            generator,
            mode,
            piece_type=piece_type,
            target_count=target_count,
            obstacle_count=obstacle_count,
            avoid_checks=avoid_checks,
            rng=rng,
        )
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
    for _ in range(target_count * 12 + 24):
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
        captures_only=False,
        files=files,
        ranks=ranks,
    )


def _build_capture_chain(
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
    hero = rng.randrange(cell_count)
    targets: dict[int, str] = {}
    obstacles: set[int] = set()
    placed: list[int] = []
    prev_vector: tuple[int, int] | None = None
    for _ in range(target_count):
        nxt = _next_reverse_capture(
            generator,
            mode,
            piece_type,
            hero,
            targets,
            obstacles,
            avoid_checks,
            rng,
            prev_vector=prev_vector,
        )
        if nxt is None:
            return None
        origin, targets = nxt
        placed.append(hero)
        prev_vector = _step_vector(hero, origin, files)
        hero = origin
    if not targets or hero in targets:
        return None
    if avoid_checks and _attacked_by_black(
        generator, mode, piece_type, targets, obstacles, hero, files, ranks
    ):
        return None
    reserved = {hero, *targets}
    dests = list(reversed(placed))
    previous = hero
    for dest in dests:
        reserved.update(_squares_between(previous, dest, files))
        previous = dest
    obstacles = _place_obstacles_on(
        [index for index in range(cell_count) if index not in reserved],
        obstacle_count,
        rng,
    )
    return MazePuzzle(
        piece_type=piece_type,
        start=hero,
        obstacles=frozenset(obstacles),
        targets=targets,
        avoid_checks=avoid_checks,
        captures_only=True,
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


def _squares_between(origin: int, dest: int, files: int) -> set[int]:
    file_a, rank_a = origin % files, origin // files
    file_b, rank_b = dest % files, dest // files
    delta_file = file_b - file_a
    delta_rank = rank_b - rank_a
    if delta_file != 0 and delta_rank != 0 and abs(delta_file) != abs(delta_rank):
        return set()
    steps = max(abs(delta_file), abs(delta_rank))
    if steps <= 1:
        return set()
    step_file = 0 if delta_file == 0 else delta_file // abs(delta_file)
    step_rank = 0 if delta_rank == 0 else delta_rank // abs(delta_rank)
    if abs(delta_file) != steps * abs(step_file) or abs(delta_rank) != steps * abs(
        step_rank
    ):
        return set()
    between: set[int] = set()
    file_, rank = file_a + step_file, rank_a + step_rank
    for _ in range(steps - 1):
        between.add(file_ + rank * files)
        file_ += step_file
        rank += step_rank
    return between


def _place_obstacles_on(candidates: list[int], obstacle_count: int, rng: Random) -> set[int]:
    if obstacle_count <= 0 or not candidates:
        return set()
    pool = list(candidates)
    rng.shuffle(pool)
    return set(pool[: min(obstacle_count, len(pool))])


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
        same = [index for index in candidates if _square_color(index, files) == color]
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


def _step_vector(origin: int, dest: int, files: int) -> tuple[int, int] | None:
    delta_file = (dest % files) - (origin % files)
    delta_rank = (dest // files) - (origin // files)
    if delta_file == 0 and delta_rank == 0:
        return None
    if delta_file == 0 or delta_rank == 0 or abs(delta_file) == abs(delta_rank):
        steps = max(abs(delta_file), abs(delta_rank))
        return (delta_file // steps, delta_rank // steps)
    return (delta_file, delta_rank)


def _is_turn(previous: tuple[int, int], current: tuple[int, int]) -> bool:
    return current != previous and current != (-previous[0], -previous[1])


def _slide_length(origin: int, dest: int, files: int) -> int:
    return max(
        abs((dest % files) - (origin % files)),
        abs((dest // files) - (origin // files)),
    )


def _path_turn_count(start: int, path: list[int], files: int) -> int:
    squares = [start, *path]
    turns = 0
    previous: tuple[int, int] | None = None
    for origin, dest in zip(squares, squares[1:]):
        vector = _step_vector(origin, dest, files)
        if vector is None:
            continue
        if previous is not None and _is_turn(previous, vector):
            turns += 1
        previous = vector
    return turns


def _prefer_route(
    origins: list[int],
    hero: int,
    files: int,
    *,
    prev_vector: tuple[int, int] | None,
    require_turn: bool,
    prefer_long: bool,
) -> list[int]:
    chosen = origins
    if require_turn and prev_vector is not None:
        chosen = []
        for origin in origins:
            vector = _step_vector(hero, origin, files)
            if vector is not None and _is_turn(prev_vector, vector):
                chosen.append(origin)
        if not chosen:
            return []
    if prefer_long:
        long = [origin for origin in chosen if _slide_length(hero, origin, files) >= 2]
        if long:
            return long
    return chosen


def _next_reverse_capture(
    generator: MoveGenerator,
    mode: GameMode,
    piece_type: str,
    hero: int,
    targets: dict[int, str],
    obstacles: set[int],
    avoid_checks: bool,
    rng: Random,
    *,
    prev_vector: tuple[int, int] | None,
) -> tuple[int, dict[int, str]] | None:
    """Step backwards, preferring a new direction and then a longer leg."""

    turn_options = (True, False) if prev_vector is not None else (False,)
    length_options = (True, False)
    for require_turn in turn_options:
        for prefer_long in length_options:
            for prefer_decoys in (True, False):
                found = _reverse_capture(
                    generator,
                    mode,
                    piece_type,
                    hero,
                    targets,
                    obstacles,
                    avoid_checks,
                    rng,
                    prefer_decoys=prefer_decoys,
                    prev_vector=prev_vector,
                    require_turn=require_turn,
                    prefer_long=prefer_long,
                )
                if found is not None:
                    return found
    return None


def _reverse_capture(
    generator: MoveGenerator,
    mode: GameMode,
    piece_type: str,
    hero: int,
    targets: dict[int, str],
    obstacles: set[int],
    avoid_checks: bool,
    rng: Random,
    *,
    prefer_decoys: bool = False,
    prev_vector: tuple[int, int] | None = None,
    require_turn: bool = False,
    prefer_long: bool = False,
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
    origins = _prefer_route(
        origins,
        hero,
        files,
        prev_vector=prev_vector,
        require_turn=require_turn,
        prefer_long=prefer_long,
    )
    if not origins:
        return None
    types = list(_target_types_for(piece_type))
    rng.shuffle(types)
    rng.shuffle(origins)
    decoys: list[tuple[int, int, int, dict[int, str]]] = []
    plain: list[tuple[int, dict[int, str]]] = []
    for type_name in types:
        trial = dict(targets)
        trial[hero] = type_name
        for origin in origins:
            if avoid_checks and _attacked_by_black(
                generator, mode, piece_type, trial, obstacles, origin, files, ranks
            ):
                continue
            captures = _capture_targets_from(
                generator, mode, piece_type, origin, trial, obstacles
            )
            if hero not in captures:
                continue
            extra = captures - {hero}
            guarded = 0
            for decoy in extra:
                leftover = dict(trial)
                del leftover[decoy]
                if _attacked_by_black(
                    generator, mode, piece_type, leftover, obstacles, decoy, files, ranks
                ):
                    guarded += 1
            safe_extra = len(extra) - guarded
            if extra and (not avoid_checks or guarded):
                decoys.append(
                    (
                        guarded if avoid_checks else len(extra),
                        -safe_extra,
                        origin,
                        trial,
                    )
                )
            else:
                plain.append((origin, trial))
    if decoys:
        best = max((score, alt) for score, alt, _origin, _trial in decoys)
        pool = [
            (origin, trial)
            for score, alt, origin, trial in decoys
            if (score, alt) == best
        ]
        return rng.choice(pool)
    if prefer_decoys:
        return None
    if not plain:
        return None
    return rng.choice(plain)


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


def _legal_destinations(
    generator: MoveGenerator,
    mode: GameMode,
    puzzle: MazePuzzle,
    hero: int,
    remaining: dict[int, str],
) -> set[int]:
    state = _maze_state(mode, hero, puzzle.piece_type, remaining, puzzle.obstacles)
    dests = _destinations(generator, state, hero)
    if puzzle.captures_only:
        dests &= set(remaining)
    if not puzzle.avoid_checks:
        return dests
    return {
        dest
        for dest in dests
        if not _landing_is_attacked(
            generator, state, dest, puzzle.files, puzzle.ranks
        )
    }


def _capture_targets_from(
    generator: MoveGenerator,
    mode: GameMode,
    piece_type: str,
    hero: int,
    targets: dict[int, str],
    obstacles: set[int] | frozenset[int],
) -> set[int]:
    state = _maze_state(mode, hero, piece_type, targets, obstacles)
    return _destinations(generator, state, hero) & set(targets)


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
    for index, piece in probe.board_state.cells.items():
        if piece is not None and piece.side is PieceSide.WHITE:
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

"""Mode-agnostic alpha-beta search over GameState / MoveGenerator.

Used as the built-in dummy engine for every ruleset, including future
non-chess games (reversi, corners, draughts) once they expose a GameMode.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from chess_core.app.game import GameStatus, evaluate_status, line_winner, material_winner
from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Action, DropAction, MoveAction, PlaceBlockerAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import format_engine_turn
from chess_core.core.piece import Piece, PieceSide
from chess_core.core.rules import VictoryKind
from chess_core.core.state import GameState
from chess_core.core.turn import StepKind

MATE_SCORE = 100_000
_INF = 1_000_000

_PIECE_VALUES: dict[str, int] = {
    "pawn": 100,
    "knight": 320,
    "bishop": 330,
    "rook": 500,
    "queen": 900,
    "king": 0,
    "gold": 500,
    "silver": 400,
    "lance": 300,
    "tokin": 420,
    "promoted_lance": 420,
    "promoted_knight": 420,
    "promoted_silver": 420,
    "horse": 1100,
    "dragon": 1200,
    "chick": 100,
    "hen": 350,
    "giraffe": 300,
    "elephant": 300,
    "lion": 0,
    "blocker": 0,
    "disc": 100,
    "man": 100,
    "kingman": 300,
    "gobblet_small": 100,
    "gobblet_medium": 250,
    "gobblet_large": 400,
}


@dataclass(frozen=True, slots=True)
class SearchResult:
    turn: Turn | None
    score_cp: int
    mate_in: int | None
    depth: int
    pv: tuple[str, ...]


class MinimaxEngine:
    """Negamax alpha-beta with iterative deepening and a time cutoff."""

    def search(self, state: GameState, *, depth: int | None = None, movetime_ms: int = 400) -> SearchResult:
        mode = state.extras.get("mode")
        if not isinstance(mode, GameMode):
            raise ValueError("GameState extras must include the GameMode")
        generator = MoveGenerator(mode)
        max_depth = depth if depth is not None else _default_depth(state, mode)
        deadline = time.monotonic() + max(movetime_ms, 1) / 1000.0
        best = SearchResult(None, 0, None, 0, ())
        turns = _legal_turns(generator, state)
        if not turns:
            terminal = _terminal_score(mode, generator, state, ply=0)
            return SearchResult(None, terminal, _mate_in(terminal, 0), 0, ())
        ordered = _order_turns(state, turns)
        for current_depth in range(1, max_depth + 1):
            if time.monotonic() >= deadline:
                break
            try:
                score, chosen, pv = self._negamax(
                    generator,
                    mode,
                    state,
                    current_depth,
                    -_INF,
                    _INF,
                    0,
                    deadline,
                    ordered,
                )
            except _TimeUp:
                break
            if chosen is None:
                chosen = ordered[0]
            best = SearchResult(
                turn=chosen,
                score_cp=score,
                mate_in=_mate_in(score, current_depth),
                depth=current_depth,
                pv=(format_engine_turn(chosen), *pv),
            )
            if abs(score) >= MATE_SCORE - 1000:
                break
            if chosen in ordered:
                ordered = [chosen, *[item for item in ordered if item is not chosen]]
        return best

    def _negamax(
        self,
        generator: MoveGenerator,
        mode: GameMode,
        state: GameState,
        depth: int,
        alpha: int,
        beta: int,
        ply: int,
        deadline: float,
        root_turns: list[Turn] | None,
    ) -> tuple[int, Turn | None, tuple[str, ...]]:
        if time.monotonic() >= deadline:
            raise _TimeUp
        terminal = _maybe_terminal(mode, generator, state, ply)
        if terminal is not None:
            return terminal, None, ()
        if depth <= 0:
            return _evaluate(state), None, ()
        turns = root_turns if root_turns is not None else _order_turns(
            state, _legal_turns(generator, state)
        )
        if not turns:
            score = _terminal_score(mode, generator, state, ply)
            return score, None, ()
        best_turn: Turn | None = None
        best_pv: tuple[str, ...] = ()
        best_score = -_INF
        for turn in turns:
            child = state.apply_turn(turn, record_history=False)
            score, _, pv = self._negamax(
                generator,
                mode,
                child,
                depth - 1,
                -beta,
                -alpha,
                ply + 1,
                deadline,
                None,
            )
            score = -score
            if score > best_score:
                best_score = score
                best_turn = turn
                best_pv = (format_engine_turn(turn), *pv)
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break
        return best_score, best_turn, best_pv[1:] if best_pv else ()


class _TimeUp(Exception):
    pass


def _default_depth(state: GameState, mode: GameMode) -> int:
    configured = mode.initial_extras.get("eval_search_depth")
    if isinstance(configured, int) and configured > 0:
        return configured
    if any(step.kind is StepKind.PLACE_BLOCKER for step in mode.turn_scenario.steps):
        return 1
    cells = state.board_state.board.shape.cell_count
    if cells <= 16:
        return 5
    if cells <= 25:
        return 3
    return 2


def legal_turns(state: GameState, *, duck_limit: int | None = 8) -> list[Turn]:
    """Complete legal turns for the side to move (including duck placements)."""
    mode = state.extras.get("mode")
    if not isinstance(mode, GameMode):
        raise ValueError("GameState extras must include the GameMode")
    return _legal_turns(MoveGenerator(mode), state, duck_limit=duck_limit)


def _legal_turns(
    generator: MoveGenerator, state: GameState, *, duck_limit: int | None = 8
) -> list[Turn]:
    mode: GameMode = state.extras["mode"]
    actions = generator.generate_legal(state)
    if any(step.kind is StepKind.PLACE_BLOCKER for step in mode.turn_scenario.steps):
        return _duck_turns(state, actions, limit=duck_limit)
    return [Turn(state.side_to_move, [action]) for action in actions]


def _duck_turns(state: GameState, actions: list[Action], *, limit: int | None) -> list[Turn]:
    shape = state.board_state.board.shape
    moves = [action for action in actions if isinstance(action, MoveAction)]
    empty = [
        index
        for index, piece in state.board_state.cells.items()
        if piece is None or (piece is not None and piece.side is PieceSide.NEUTRAL)
    ]
    turns: list[Turn] = []
    for move in moves:
        source = move.from_square.index(shape.files)
        dest = move.to_square.index(shape.files)
        candidates = {source}
        for index in empty:
            if index != dest:
                candidates.add(index)
        # Dummy: origin plus a spread of empty squares, not the full 60-ply duck tree.
        ordered = [source, *[index for index in sorted(candidates) if index != source]]
        chosen = ordered if limit is None else ordered[: max(1, limit)]
        for index in chosen:
            square = Square.from_index(index, shape.files, shape.ranks)
            turns.append(Turn(state.side_to_move, [move, PlaceBlockerAction(square)]))
    return turns


def _order_turns(state: GameState, turns: list[Turn]) -> list[Turn]:
    corners = _eval_corner_set(state)

    def key(turn: Turn) -> tuple[int, int]:
        action = turn.actions[0]
        capture = 0
        drop = 0
        if isinstance(action, MoveAction):
            if action.jumped:
                capture = -100 * len(action.jumped)
            else:
                target = action.to_square.index(state.board_state.board.shape.files)
                occupant = state.board_state.piece_at(target)
                if occupant is not None:
                    capture = -_piece_value(occupant)
        elif isinstance(action, DropAction):
            drop = 1
            index = action.to_square.index(state.board_state.board.shape.files)
            if index in corners:
                drop = -2
            elif _is_corner_adjacent(index, corners, state.board_state.board.shape.files):
                drop = 2
        return (capture, drop)

    return sorted(turns, key=key)


def _maybe_terminal(
    mode: GameMode,
    generator: MoveGenerator,
    state: GameState,
    ply: int,
) -> int | None:
    status = evaluate_status(mode, generator, state, is_live=True)
    if status is GameStatus.ACTIVE or status is GameStatus.CHECK:
        return None
    return _status_score(mode, state, status, ply)


def _terminal_score(
    mode: GameMode,
    generator: MoveGenerator,
    state: GameState,
    ply: int,
) -> int:
    status = evaluate_status(mode, generator, state, is_live=True)
    return _status_score(mode, state, status, ply)


def _status_score(
    mode: GameMode,
    state: GameState,
    status: GameStatus,
    ply: int,
) -> int:
    """Scores from the side-to-move point of view (negamax)."""
    if status is GameStatus.STALEMATE:
        return 0
    if status is GameStatus.REPETITION_DRAW:
        return 0
    if status is GameStatus.TRY_WIN:
        conditions = mode.victory if isinstance(mode.victory, tuple) else (mode.victory,)
        if any(getattr(item, "kind", None) is VictoryKind.ALIGN for item in conditions):
            winner = line_winner(mode, state)
            if winner is None:
                return 0
            return MATE_SCORE - ply if winner is state.side_to_move else -MATE_SCORE + ply
        return -MATE_SCORE + ply
    if status in {GameStatus.CHECKMATE, GameStatus.KING_CAPTURE_WIN}:
        return -MATE_SCORE + ply
    if status is GameStatus.MATERIAL_WIN:
        winner = material_winner(mode, state)
        if winner is None:
            return 0
        return MATE_SCORE - ply if winner is state.side_to_move else -MATE_SCORE + ply
    return _evaluate(state)


def _evaluate(state: GameState) -> int:
    """Material from the side to move; invert for giveaway-like MATERIAL modes."""
    mode = state.extras.get("mode")
    if isinstance(mode, GameMode) and mode.initial_extras.get("eval_corners") is not None:
        white_cp = _corner_board_eval(state, mode)
    else:
        white_cp = _white_material(state)
        if isinstance(mode, GameMode):
            conditions = mode.victory if isinstance(mode.victory, tuple) else (mode.victory,)
            if any(getattr(item, "kind", None) is VictoryKind.MATERIAL for item in conditions):
                if mode.initial_extras.get("empty_side_wins"):
                    white_cp = -white_cp
    stm = white_cp if state.side_to_move is PieceSide.WHITE else -white_cp
    return stm


def _eval_corner_set(state: GameState) -> frozenset[int]:
    mode = state.extras.get("mode")
    if not isinstance(mode, GameMode):
        return frozenset()
    raw = mode.initial_extras.get("eval_corners")
    if not isinstance(raw, (tuple, list)):
        return frozenset()
    return frozenset(int(index) for index in raw)


def _is_corner_adjacent(index: int, corners: frozenset[int], files: int) -> bool:
    file = index % files
    rank = index // files
    for corner in corners:
        cf = corner % files
        cr = corner // files
        if max(abs(file - cf), abs(rank - cr)) == 1:
            return True
    return False


def _corner_board_eval(state: GameState, mode: GameMode) -> int:
    """White-positive: corners 10, neighbors -5 if that corner is empty, discs 1."""
    extras = mode.initial_extras
    corner_value = int(extras.get("eval_corner_value", 10))
    adjacent_value = int(extras.get("eval_adjacent_value", -5))
    disc_value = int(extras.get("eval_disc", 1))
    files = state.board_state.board.shape.files
    ranks = state.board_state.board.shape.ranks
    cells = state.board_state.cells
    corners = _eval_corner_set(state)
    discs = 0
    corners_score = 0
    occupied = 0
    for index, piece in cells.items():
        if piece is None or piece.side is PieceSide.NEUTRAL:
            continue
        occupied += 1
        sign = 1 if piece.side is PieceSide.WHITE else -1
        discs += disc_value * sign
        if index in corners:
            corners_score += corner_value * sign
    empty = files * ranks - occupied
    if empty <= 10:
        discs *= 3
    adjacent_score = 0
    if adjacent_value:
        seen: set[int] = set()
        for corner in corners:
            if cells.get(corner) is not None:
                continue
            cf = corner % files
            cr = corner // files
            for df in (-1, 0, 1):
                for dr in (-1, 0, 1):
                    if df == 0 and dr == 0:
                        continue
                    nf = cf + df
                    nr = cr + dr
                    if not (0 <= nf < files and 0 <= nr < ranks):
                        continue
                    neighbor = nr * files + nf
                    if neighbor in seen:
                        continue
                    seen.add(neighbor)
                    piece = cells.get(neighbor)
                    if piece is None or piece.side is PieceSide.NEUTRAL:
                        continue
                    sign = 1 if piece.side is PieceSide.WHITE else -1
                    adjacent_score += adjacent_value * sign
    return discs + corners_score + adjacent_score


def _white_material(state: GameState) -> int:
    total = 0
    for piece in state.board_state.cells.values():
        if piece is None or piece.side is PieceSide.NEUTRAL:
            continue
        value = _piece_value(piece)
        total += value if piece.side is PieceSide.WHITE else -value
    if state.hands is not None:
        for side, pieces in state.hands.by_side.items():
            for piece in pieces:
                value = int(_piece_value(piece) * 0.9)
                total += value if side is PieceSide.WHITE else -value
    return total


def _piece_value(piece: Piece) -> int:
    return _PIECE_VALUES.get(piece.piece_type.name, 150)


def _side_count(state: GameState, side: PieceSide) -> int:
    return sum(
        1
        for piece in state.board_state.cells.values()
        if piece is not None and piece.side is side
    )


def _mate_in(score: int, depth: int) -> int | None:
    if abs(score) < MATE_SCORE - 1000:
        return None
    plies = MATE_SCORE - abs(score)
    moves = max(1, (plies + 1) // 2)
    return moves if score > 0 else -moves

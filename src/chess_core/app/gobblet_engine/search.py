"""Alpha-beta over Gobblet bitboards with line-threat heuristics."""

from __future__ import annotations

import time
from dataclasses import dataclass

from chess_core.app.gobblet_engine.bits import (
    NativeMove,
    LINES,
    OPP,
    SQUARE_WEIGHT,
    STM,
    apply_move,
    played_counts,
    square_cell,
    swap,
    terminal_value,
    top_owner_size,
)
from chess_core.app.gobblet_engine.canon import canonical, canonical_key, invert_perm, map_move
from chess_core.app.gobblet_engine.moves import can_place, legal_moves, move_size

MATE = 10_000
_INF = 1_000_000
_THREAT = 90
_DOUBLE_THREAT = 450
_RESERVE = (2, 6, 14)
EXACT = 0
LOWER = 1
UPPER = 2


@dataclass(frozen=True, slots=True)
class TTEntry:
    depth: int
    score: int
    bound: int
    best_move: NativeMove | None


class _TimeUp(Exception):
    pass


def evaluate(state: int, *, probe_win: bool = True) -> int:
    term = terminal_value(state)
    if term:
        return term * MATE
    tops = _tops(state)
    if probe_win and _has_immediate_win(state, tops):
        return MATE - 1
    stm_threats = _open_threats(tops, STM)
    opp_threats = _open_threats(tops, OPP)
    score = 0
    for square, (owner, _size) in enumerate(tops):
        if owner == STM:
            score += SQUARE_WEIGHT[square]
        elif owner == OPP:
            score -= SQUARE_WEIGHT[square]
    score += _threat_score(stm_threats) - _threat_score(opp_threats)
    stm_played = played_counts(state, STM)
    opp_played = played_counts(state, OPP)
    for size in range(3):
        score += _RESERVE[size] * (2 - stm_played[size])
        score -= _RESERVE[size] * (2 - opp_played[size])
    return score


def _threat_score(count: int) -> int:
    if count >= 2:
        return _DOUBLE_THREAT
    if count == 1:
        return _THREAT
    return 0


def _tops(state: int) -> list[tuple[int, int]]:
    return [top_owner_size(square_cell(state, square)) for square in range(9)]


def _open_threats(tops: list[tuple[int, int]], who: int) -> int:
    """Lines where `who` has two tops and the third is empty or a smaller enemy."""
    count = 0
    for line in LINES:
        ours = empty = theirs = 0
        for square in line:
            owner, _size = tops[square]
            if owner == who:
                ours += 1
            elif owner == 0:
                empty += 1
            else:
                theirs += 1
        if ours == 2 and empty + theirs == 1:
            count += 1
    return count


def _has_immediate_win(state: int, tops: list[tuple[int, int]] | None = None) -> bool:
    tops = tops if tops is not None else _tops(state)
    for line in LINES:
        ours: list[int] = []
        empty: list[int] = []
        theirs: list[tuple[int, int]] = []
        for square in line:
            owner, size = tops[square]
            if owner == STM:
                ours.append(square)
            elif owner == 0:
                empty.append(square)
            else:
                theirs.append((square, size))
        if len(ours) == 2 and len(empty) == 1 and can_place(state, empty[0], 1):
            return True
        if len(ours) == 2 and len(theirs) == 1:
            dest, opp_size = theirs[0]
            if can_place(state, dest, opp_size + 1):
                return True
    return False


def order_moves(state: int, moves: list[NativeMove]) -> list[NativeMove]:
    def key(move: NativeMove) -> tuple:
        size = move_size(state, move)
        child = swap(apply_move(state, move, size))
        term = terminal_value(child)
        if term == -1:
            return (0, 0, 0, size)
        child_tops = _tops(child)
        hang = _open_threats(child_tops, STM) > 0
        our_threats = _open_threats(child_tops, OPP)
        return (1, int(hang), -our_threats, -SQUARE_WEIGHT[move.end], size)

    return sorted(moves, key=key)


def search_best(
    state: int,
    *,
    depth: int = 5,
    deadline: float | None = None,
    tt: dict[int, TTEntry] | None = None,
    iterative: bool = True,
    ordered: bool = True,
    probe_win: bool = True,
) -> tuple[NativeMove | None, int]:
    table = tt if tt is not None else {}
    oriented, perm = canonical(state)
    move, score = _search_oriented(
        oriented,
        depth=depth,
        deadline=deadline,
        tt=table,
        iterative=iterative,
        ordered=ordered,
        probe_win=probe_win,
    )
    if move is None:
        return None, score
    return map_move(move, invert_perm(perm)), score


def _search_oriented(
    state: int,
    *,
    depth: int,
    deadline: float | None,
    tt: dict[int, TTEntry],
    iterative: bool,
    ordered: bool,
    probe_win: bool,
) -> tuple[NativeMove | None, int]:
    raw_moves = legal_moves(state)
    moves = order_moves(state, raw_moves) if ordered else raw_moves
    if not moves:
        return None, evaluate(state, probe_win=probe_win)
    committed_move = moves[0]
    committed_score = 0
    iteration_best = committed_move
    iteration_score = -_INF
    finished_root = 0
    depths = range(1, depth + 1) if iterative else (depth,)
    try:
        for current in depths:
            if deadline is not None and time.monotonic() >= deadline:
                break
            iteration_best = committed_move
            iteration_score = -_INF
            finished_root = 0
            alpha = -_INF
            beta = _INF
            tt_move = table_move(tt, state)
            first_move = tt_move if tt_move in moves else committed_move
            ordered_moves = [first_move, *[item for item in moves if item != first_move]]
            for move in ordered_moves:
                if deadline is not None and time.monotonic() >= deadline:
                    raise _TimeUp
                child = canonical_key(swap(apply_move(state, move, move_size(state, move))))
                score = -_negamax(
                    child, current - 1, -beta, -alpha, 1, deadline, tt, ordered, probe_win
                )
                finished_root += 1
                if score > iteration_score:
                    iteration_score = score
                    iteration_best = move
                if score > alpha:
                    alpha = score
            committed_move = iteration_best
            committed_score = iteration_score
            moves = [committed_move, *[item for item in moves if item != committed_move]]
    except _TimeUp:
        if finished_root >= 1:
            committed_move = iteration_best
            committed_score = iteration_score
    return committed_move, committed_score


def _negamax(
    state: int,
    depth: int,
    alpha: int,
    beta: int,
    ply: int,
    deadline: float | None,
    tt: dict[int, TTEntry],
    ordered: bool,
    probe_win: bool,
) -> int:
    if deadline is not None and time.monotonic() >= deadline:
        raise _TimeUp
    term = terminal_value(state)
    if term:
        return term * (MATE - ply)
    if depth <= 0:
        return evaluate(state, probe_win=probe_win)
    alpha_original = alpha
    beta_original = beta
    hit = tt.get(state)
    if hit is not None and hit.depth >= depth:
        if hit.bound == EXACT:
            return hit.score
        if hit.bound == LOWER:
            alpha = max(alpha, hit.score)
        elif hit.bound == UPPER:
            beta = min(beta, hit.score)
        if alpha >= beta:
            return hit.score
    raw_moves = legal_moves(state)
    moves = order_moves(state, raw_moves) if ordered else raw_moves
    if hit is not None and hit.best_move in moves:
        moves = [hit.best_move, *[move for move in moves if move != hit.best_move]]
    if not moves:
        return 0
    best = -_INF
    best_move: NativeMove | None = None
    for index, move in enumerate(moves):
        child = canonical_key(swap(apply_move(state, move, move_size(state, move))))
        if index == 0:
            score = -_negamax(
                child, depth - 1, -beta, -alpha, ply + 1, deadline, tt, ordered, probe_win
            )
        else:
            score = -_negamax(
                child, depth - 1, -alpha - 1, -alpha, ply + 1, deadline, tt, ordered, probe_win
            )
            if alpha < score < beta:
                score = -_negamax(
                    child, depth - 1, -beta, -alpha, ply + 1, deadline, tt, ordered, probe_win
                )
        if score > best:
            best = score
            best_move = move
        if score > alpha:
            alpha = score
        if alpha >= beta:
            break
    if abs(best) < MATE - 100:
        bound = EXACT
        if best <= alpha_original:
            bound = UPPER
        elif best >= beta_original:
            bound = LOWER
        previous = tt.get(state)
        if previous is None or depth >= previous.depth:
            tt[state] = TTEntry(depth, best, bound, best_move)
    return best


def table_move(tt: dict[int, TTEntry], state: int) -> NativeMove | None:
    entry = tt.get(state)
    return None if entry is None else entry.best_move

"""Gobblet engine: exact probes, trained AlphaZero model, then alpha-beta."""

from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path

from chess_core.app.gobblet_engine.bits import (
    NativeMove,
    apply_move,
    encode_state,
    swap,
    terminal_value,
)
from chess_core.app.gobblet_engine.moves import legal_moves, move_size
from chess_core.app.gobblet_engine.opening import GobbletOpeningBook
from chess_core.app.gobblet_engine.search import MATE, order_moves, search_best
from chess_core.app.gobblet_engine.tablebase import GobbletTablebase
from chess_core.app.search import SearchResult
from chess_core.core.board import Square
from chess_core.core.move import DropAction, MoveAction, Turn
from chess_core.core.notation import format_engine_turn
from chess_core.core.piece import PieceTypeId
from chess_core.core.state import GameState
from chess_core.infra.paths import project_root

_SIZE_NAME = {1: "gobblet_small", 2: "gobblet_medium", 3: "gobblet_large"}


class GobbletEngine:
    def __init__(
        self,
        tablebase: GobbletTablebase | None = None,
        opening: GobbletOpeningBook | None = None,
    ) -> None:
        self._tablebase = tablebase if tablebase is not None else _load_default_tablebase()
        self._opening = opening if opening is not None else _load_default_opening()
        self._opening_override = opening is not None

    def search(self, state: GameState, *, depth: int | None = None, movetime_ms: int = 10_000) -> SearchResult:
        key = encode_state(state)
        max_depth = 12 if depth is None else depth
        deadline = time.monotonic() + max(movetime_ms, 1) / 1000.0
        native, score = self._choose(key, max_depth, deadline)
        turn = None if native is None else native_to_turn(state, native)
        return SearchResult(
            turn=turn,
            score_cp=score,
            mate_in=_mate_in(score),
            depth=max_depth,
            pv=(format_engine_turn(turn),) if turn is not None else (),
        )

    def _choose(self, state: int, depth: int, deadline: float) -> tuple[NativeMove | None, int]:
        moves = legal_moves(state)
        if not moves:
            return None, 0
        immediate = [
            move
            for move in moves
            if terminal_value(swap(apply_move(state, move, move_size(state, move)))) == -1
        ]
        if immediate:
            return order_moves(state, immediate)[0], MATE
        table = self._tablebase
        if table is not None and len(table):
            wins = [
                move
                for move in moves
                if table.get(swap(apply_move(state, move, move_size(state, move)))) == -1
            ]
            if wins:
                return order_moves(state, wins)[0], MATE
        if self._opening_override:
            book_move, book_score = self._opening.probe(state)
            if book_move is not None and book_move in moves:
                return book_move, book_score
        neural = _load_default_alphazero()
        if neural is not None:
            mcts, torch = neural
            from chess_core.app.gobblet_engine.alphazero import (
                MCTSConfig,
                action_to_move,
                move_to_action,
            )

            mcts.config = MCTSConfig(
                simulations=max(32, min(192, depth * 24)),
                use_solved_opening=True,
            )
            safe = [move for move in moves if not _allows_immediate_reply(state, move)]
            allowed = (
                {move_to_action(move) for move in safe}
                if safe and len(safe) < len(moves)
                else None
            )
            policy = mcts.search_many(
                [state],
                add_noise=False,
                deadline=deadline,
                allowed_root_actions=[allowed],
            )[0]
            move = action_to_move(int(torch.argmax(policy)))
            if move in moves:
                _policy, values = mcts.evaluate([state])
                return move, int(values[0] * 1000)
        book_move, book_score = self._opening.probe(state)
        if book_move is not None and book_move in moves:
            return book_move, book_score
        return search_best(state, depth=depth, deadline=deadline)


def _allows_immediate_reply(state: int, move: NativeMove) -> bool:
    child = swap(apply_move(state, move, move_size(state, move)))
    for reply in legal_moves(child):
        grandchild = swap(apply_move(child, reply, move_size(child, reply)))
        if terminal_value(grandchild) == -1:
            return True
    return False


def native_to_turn(game: GameState, move: NativeMove) -> Turn:
    target = Square.from_index(move.end, 3, 3)
    if move.start < 0:
        action = DropAction(PieceTypeId(_SIZE_NAME[-move.start]), target)
    else:
        action = MoveAction(Square.from_index(move.start, 3, 3), target)
    return Turn(game.side_to_move, [action])


def tablebase_path() -> Path:
    return project_root() / "data" / "gobblet" / "tablebase.ggt"


def packaged_opening_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "gobblet" / "opening.ggb"


def alphazero_model_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "gobblet" / "alphazero.pt"


def opening_path(*, prefer_packaged: bool = False) -> Path:
    packaged = packaged_opening_path()
    if prefer_packaged:
        return packaged
    override = project_root() / "data" / "gobblet" / "opening.ggb"
    if override.is_file():
        return override
    return packaged


@lru_cache(maxsize=1)
def _load_default_tablebase() -> GobbletTablebase:
    path = tablebase_path()
    if path.is_file():
        return GobbletTablebase.load(path)
    return GobbletTablebase()


@lru_cache(maxsize=1)
def _load_default_opening() -> GobbletOpeningBook:
    path = opening_path()
    if path.is_file():
        return GobbletOpeningBook.load(path)
    return GobbletOpeningBook()


@lru_cache(maxsize=1)
def _load_default_alphazero():
    path = alphazero_model_path()
    if not path.is_file():
        return None
    try:
        import torch

        from chess_core.app.gobblet_engine.alphazero import GobbletMCTS, load_checkpoint

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model, _metadata = load_checkpoint(path, device=device)
        return GobbletMCTS(model, device=device), torch
    except (ImportError, OSError, RuntimeError, ValueError, KeyError):
        return None


def _mate_in(score: int) -> int | None:
    if abs(score) < MATE - 100:
        return None
    return 1 if score > 0 else -1

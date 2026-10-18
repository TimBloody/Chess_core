"""Gobblet bitboard engine, heuristics, and tablebase probe."""

from chess_core.app.engine import EngineAnalysisService, EngineRequest, SearchLimit
from chess_core.app.engine_catalog import preferred_engine_ids
from chess_core.app.gobblet_engine import (
    GobbletEngine,
    GobbletOpeningBook,
    GobbletTablebase,
    build_opening_book,
    build_proved_tablebase,
)
from chess_core.app.gobblet_engine.bits import NativeMove, apply_move, encode_state, square_cell, swap
from chess_core.app.gobblet_engine.canon import canonical, canonical_key, d4_perms, invert_perm, map_move, transform_state
from chess_core.app.gobblet_engine.moves import legal_moves
from chess_core.app.gobblet_engine.search import order_moves
from chess_core.core.board import Square
from chess_core.core.move import DropAction, MoveAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide
from chess_core.modes.gobblet import gobblet
from chess_core.modes.gobblet_rules import GOBBLET_LARGE, GOBBLET_MEDIUM, GOBBLET_SMALL, stack_at, sync_cell


def _index(file: int, rank: int) -> int:
    return rank * 3 + file


def test_native_opening_matches_core_drops() -> None:
    state = gobblet().initial_state()
    native = {(move.start, move.end) for move in legal_moves(encode_state(state))}
    core = set()
    for action in MoveGenerator(gobblet()).generate_legal(state):
        assert isinstance(action, DropAction)
        size = {"gobblet_small": -1, "gobblet_medium": -2, "gobblet_large": -3}[action.piece_type.name]
        core.add((size, action.to_square.index(3)))
    assert native == core


def test_opening_prefers_small_in_the_center() -> None:
    engine = GobbletEngine(tablebase=GobbletTablebase(), opening=GobbletOpeningBook())
    result = engine.search(gobblet().initial_state(), depth=1, movetime_ms=2000)
    assert result.turn is not None
    drop = result.turn.actions[0]
    assert isinstance(drop, DropAction)
    assert drop.piece_type == GOBBLET_SMALL
    assert (drop.to_square.file, drop.to_square.rank) == (1, 1)


def test_takes_three_in_a_row_when_available() -> None:
    mode = gobblet()
    state = mode.initial_state()
    stack_at(state, _index(0, 0)).append(Piece(GOBBLET_MEDIUM, PieceSide.WHITE))
    sync_cell(state, _index(0, 0))
    stack_at(state, _index(1, 0)).append(Piece(GOBBLET_MEDIUM, PieceSide.WHITE))
    sync_cell(state, _index(1, 0))
    result = GobbletEngine(tablebase=GobbletTablebase(), opening=GobbletOpeningBook()).search(
        state, depth=1, movetime_ms=2000
    )
    assert result.turn is not None
    drop = result.turn.actions[0]
    assert (drop.to_square.file, drop.to_square.rank) == (2, 0)


def test_blocks_an_immediate_triple() -> None:
    mode = gobblet()
    state = mode.initial_state()
    stack_at(state, _index(0, 2)).append(Piece(GOBBLET_SMALL, PieceSide.BLACK))
    sync_cell(state, _index(0, 2))
    stack_at(state, _index(1, 2)).append(Piece(GOBBLET_SMALL, PieceSide.BLACK))
    sync_cell(state, _index(1, 2))
    result = GobbletEngine(tablebase=GobbletTablebase(), opening=GobbletOpeningBook()).search(
        state, depth=2, movetime_ms=2000
    )
    assert result.turn is not None
    drop = result.turn.actions[0]
    assert (drop.to_square.file, drop.to_square.rank) in {(0, 2), (1, 2), (2, 2)}


def test_tablebase_win_is_preferred_over_heuristic() -> None:
    state = gobblet().initial_state()
    key = encode_state(state)
    moves = order_moves(key, legal_moves(key))
    corner = next(move for move in moves if move.end == 0)
    child = swap(apply_move(key, corner, 1))
    table = GobbletTablebase({canonical_key(child): -1})
    result = GobbletEngine(tablebase=table, opening=GobbletOpeningBook()).search(state, depth=5, movetime_ms=2000)
    assert result.turn is not None
    drop = result.turn.actions[0]
    assert (drop.to_square.file, drop.to_square.rank) == (0, 0)


def test_proved_tablebase_roundtrip(tmp_path) -> None:
    table = build_proved_tablebase(max_nodes=40)
    path = tmp_path / "tb.ggt"
    table.save(path)
    loaded = GobbletTablebase.load(path)
    assert len(loaded) == len(table)
    assert loaded.get(0) == table.get(0)


def test_catalog_prefers_gobblet_engine() -> None:
    assert preferred_engine_ids("gobblet")[0] == "gobblet"
    mode = gobblet()
    best = EngineAnalysisService.for_mode(mode, discovered=[]).analyze(
        EngineRequest(mode.initial_state(), SearchLimit(depth=1, movetime_ms=800))
    )
    assert best.engine_id == "gobblet"
    assert best.turn is not None
    assert isinstance(best.turn.actions[0], DropAction)


def test_native_move_matches_core_after_cover() -> None:
    mode = gobblet()
    state = mode.initial_state()
    state = state.apply_turn(Turn(PieceSide.WHITE, [DropAction(GOBBLET_SMALL, Square(1, 1))]))
    native = legal_moves(encode_state(state))
    core = MoveGenerator(mode).generate_legal(state)
    native_drops = {(m.start, m.end) for m in native if m.start < 0}
    core_drops = set()
    for action in core:
        if isinstance(action, DropAction):
            size = {"gobblet_small": -1, "gobblet_medium": -2, "gobblet_large": -3}[action.piece_type.name]
            core_drops.add((size, action.to_square.index(3)))
    assert native_drops == core_drops
    native_board = {(m.start, m.end) for m in native if m.start >= 0}
    core_board = {
        (action.from_square.index(3), action.to_square.index(3))
        for action in core
        if isinstance(action, MoveAction)
    }
    assert native_board == core_board


def test_rot90_four_times_is_identity() -> None:
    rot90 = d4_perms()[1]
    composed = rot90
    for _ in range(3):
        composed = tuple(rot90[index] for index in composed)
    assert composed == tuple(range(9))
    state = apply_move(0, NativeMove(-2, 8), 2)
    oriented = state
    for _ in range(4):
        oriented = transform_state(oriented, rot90)
    assert oriented == state


def test_corner_piece_canonicalizes_empty_top_right() -> None:
    keys = set()
    for corner in (0, 2, 6, 8):
        state = apply_move(0, NativeMove(-1, corner), 1)
        oriented, _perm = canonical(state)
        assert square_cell(oriented, 0) == square_cell(state, corner)
        assert square_cell(oriented, 8) == 0
        keys.add(canonical_key(state))
    assert keys == {canonical_key(apply_move(0, NativeMove(-1, 0), 1))}


def test_map_move_roundtrip_through_d4() -> None:
    move = NativeMove(0, 8)
    drop = NativeMove(-3, 4)
    for perm in d4_perms():
        inverse = invert_perm(perm)
        assert map_move(map_move(move, perm), inverse) == move
        assert map_move(map_move(drop, perm), inverse) == drop


def test_opening_book_plays_stored_move_on_empty_board() -> None:
    book = GobbletOpeningBook({0: (NativeMove(-3, 8), 12)})
    result = GobbletEngine(tablebase=GobbletTablebase(), opening=book).search(
        gobblet().initial_state(), depth=1, movetime_ms=200
    )
    assert result.turn is not None
    drop = result.turn.actions[0]
    assert isinstance(drop, DropAction)
    assert drop.piece_type == GOBBLET_LARGE
    assert (drop.to_square.file, drop.to_square.rank) == (2, 2)


def test_opening_book_roundtrip_and_corner_symmetry(tmp_path) -> None:
    book = build_opening_book(max_ply=1, leaf_depth=1)
    keys = {
        canonical_key(swap(apply_move(0, NativeMove(-1, square), 1)))
        for square in (0, 2, 6, 8)
    }
    assert len(keys) == 1
    path = tmp_path / "opening.ggb"
    book.save(path)
    loaded = GobbletOpeningBook.load(path)
    assert len(loaded) == len(book)
    move, _score = loaded.probe(0)
    assert move is not None
    assert move in legal_moves(0)


def _drop(state, piece, file: int, rank: int):
    stack_at(state, _index(file, rank)).append(piece)
    sync_cell(state, _index(file, rank))
    return state


def test_does_not_uncover_a_file_triple() -> None:
    """Lifting a1 onto c3 reveals Black on a1; with a3 they win on a2."""
    mode = gobblet()
    state = mode.initial_state()
    _drop(state, Piece(GOBBLET_LARGE, PieceSide.WHITE), 1, 1)
    _drop(state, Piece(GOBBLET_MEDIUM, PieceSide.BLACK), 0, 0)
    _drop(state, Piece(GOBBLET_LARGE, PieceSide.WHITE), 0, 0)
    _drop(state, Piece(GOBBLET_SMALL, PieceSide.BLACK), 2, 2)
    _drop(state, Piece(GOBBLET_SMALL, PieceSide.WHITE), 0, 2)
    _drop(state, Piece(GOBBLET_MEDIUM, PieceSide.BLACK), 0, 2)
    result = GobbletEngine(tablebase=GobbletTablebase(), opening=GobbletOpeningBook()).search(
        state, depth=2, movetime_ms=2000
    )
    assert result.turn is not None
    action = result.turn.actions[0]
    lifted_a1_to_c3 = (
        isinstance(action, MoveAction)
        and action.from_square.file == 0
        and action.from_square.rank == 0
        and action.to_square.file == 2
        and action.to_square.rank == 2
    )
    assert not lifted_a1_to_c3


def test_blocks_two_on_a_file() -> None:
    mode = gobblet()
    state = mode.initial_state()
    _drop(state, Piece(GOBBLET_SMALL, PieceSide.BLACK), 0, 0)
    _drop(state, Piece(GOBBLET_SMALL, PieceSide.BLACK), 0, 2)
    result = GobbletEngine(tablebase=GobbletTablebase(), opening=GobbletOpeningBook()).search(
        state, depth=2, movetime_ms=2000
    )
    assert result.turn is not None
    drop = result.turn.actions[0]
    assert isinstance(drop, DropAction)
    assert drop.to_square.file == 0


def test_timeout_returns_a_legal_ordered_move() -> None:
    engine = GobbletEngine(tablebase=GobbletTablebase(), opening=GobbletOpeningBook())
    result = engine.search(gobblet().initial_state(), depth=12, movetime_ms=1)
    assert result.turn is not None
    drop = result.turn.actions[0]
    assert isinstance(drop, DropAction)
    squares = {(action.to_square.file, action.to_square.rank) for action in [drop]}
    assert squares <= {(f, r) for f in range(3) for r in range(3)}

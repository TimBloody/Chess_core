"""Tests for Nanai checkers and Hasami shogi on 6x6."""

from chess_core.app.game import GameStatus, LocalGameService, evaluate_status
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.modes.hasami_shogi import hasami_shogi
from chess_core.modes.line_capture_common import hasami_captures_after_move
from chess_core.modes.nanai_checkers import MAN, nanai_checkers


def _sq(name: str) -> Square:
    return Square(ord(name[0]) - ord("a"), int(name[1]) - 1)


def _clear(mode) -> tuple[object, int]:
    state = mode.initial_state()
    files = mode.board.shape.files
    for index in range(mode.board.shape.cell_count):
        state.board_state.cells[index] = None
    return state, files


def test_nanai_and_hasami_are_registered() -> None:
    register_builtin_modes()
    modes = set(default_registry.list_modes())
    assert {"nanai_checkers", "hasami_shogi"} <= modes


def test_nanai_start_position() -> None:
    mode = nanai_checkers()
    state = mode.initial_state()
    files = mode.board.shape.files
    assert mode.board.shape.files == 6
    assert mode.board.shape.ranks == 6
    assert state.side_to_move is PieceSide.WHITE
    for file in range(6):
        assert state.board_state.piece_at(file).side is PieceSide.WHITE
        assert state.board_state.piece_at(5 * files + file).side is PieceSide.BLACK


def test_nanai_capture_blocked_by_third_own_piece() -> None:
    mode = nanai_checkers()
    state, files = _clear(mode)
    placements = {
        _sq("a1"): PieceSide.WHITE,
        _sq("a3"): PieceSide.WHITE,
        _sq("b2"): PieceSide.WHITE,
        _sq("a4"): PieceSide.BLACK,
        _sq("f6"): PieceSide.BLACK,
    }
    for square, side in placements.items():
        state.board_state.cells[square.index(files)] = Piece(MAN, side)
    state.side_to_move = PieceSide.WHITE
    after = state.apply_turn(
        Turn(PieceSide.WHITE, [MoveAction(_sq("b2"), _sq("a2"))]),
        record_history=False,
    )
    assert after.board_state.piece_at(_sq("a4").index(files)) is not None


def test_nanai_capture_without_third_own_piece() -> None:
    mode = nanai_checkers()
    state, files = _clear(mode)
    placements = {
        _sq("a3"): PieceSide.WHITE,
        _sq("b2"): PieceSide.WHITE,
        _sq("a4"): PieceSide.BLACK,
        _sq("f6"): PieceSide.BLACK,
    }
    for square, side in placements.items():
        state.board_state.cells[square.index(files)] = Piece(MAN, side)
    state.side_to_move = PieceSide.WHITE
    generator = MoveGenerator(mode)
    turn = next(
        Turn(PieceSide.WHITE, [action])
        for action in generator.generate_legal(state)
        if isinstance(action, MoveAction)
        and action.from_square == _sq("b2")
        and action.to_square == _sq("a2")
    )
    after = state.apply_turn(turn, record_history=False)
    assert after.board_state.piece_at(_sq("a4").index(files)) is None
    assert after.board_state.piece_at(_sq("a2").index(files)).side is PieceSide.WHITE


def test_hasami_start_position_and_black_to_move() -> None:
    mode = hasami_shogi()
    state = mode.initial_state()
    files = mode.board.shape.files
    assert mode.asset_family == "shogi"
    assert state.side_to_move is PieceSide.BLACK
    for file in range(6):
        assert state.board_state.piece_at(file).side is PieceSide.WHITE
        assert state.board_state.piece_at(5 * files + file).side is PieceSide.BLACK


def test_hasami_custodian_capture() -> None:
    mode = hasami_shogi()
    state, files = _clear(mode)
    pawn = PieceTypeId("pawn")
    placements = {
        _sq("a1"): PieceSide.WHITE,
        _sq("a2"): PieceSide.BLACK,
        _sq("a4"): PieceSide.WHITE,
        _sq("f6"): PieceSide.BLACK,
    }
    for square, side in placements.items():
        state.board_state.cells[square.index(files)] = Piece(pawn, side)
    state.side_to_move = PieceSide.WHITE
    generator = MoveGenerator(mode)
    turn = next(
        Turn(PieceSide.WHITE, [action])
        for action in generator.generate_legal(state)
        if isinstance(action, MoveAction)
        and action.from_square == _sq("a4")
        and action.to_square == _sq("a3")
    )
    after = state.apply_turn(turn, record_history=False)
    assert after.board_state.piece_at(_sq("a2").index(files)) is None
    assert after.board_state.piece_at(_sq("a3").index(files)).side is PieceSide.WHITE


def test_hasami_safe_move_between_two_own() -> None:
    mode = hasami_shogi()
    state, files = _clear(mode)
    pawn = PieceTypeId("pawn")
    placements = {
        _sq("a1"): PieceSide.WHITE,
        _sq("a3"): PieceSide.WHITE,
        _sq("a4"): PieceSide.BLACK,
    }
    for square, side in placements.items():
        state.board_state.cells[square.index(files)] = Piece(pawn, side)
    state.side_to_move = PieceSide.BLACK
    after = state.apply_turn(
        Turn(PieceSide.BLACK, [MoveAction(_sq("a4"), _sq("a2"))]),
        record_history=False,
    )
    assert after.board_state.piece_at(_sq("a2").index(files)).side is PieceSide.BLACK


def test_hasami_multi_capture_between_brackets() -> None:
    mode = hasami_shogi()
    state, files = _clear(mode)
    pawn = PieceTypeId("pawn")
    placements = {
        _sq("a1"): PieceSide.WHITE,
        _sq("a5"): PieceSide.WHITE,
        _sq("a2"): PieceSide.BLACK,
        _sq("a3"): PieceSide.BLACK,
        _sq("a4"): PieceSide.BLACK,
    }
    for square, side in placements.items():
        state.board_state.cells[square.index(files)] = Piece(pawn, side)
    state.side_to_move = PieceSide.WHITE
    probe = state.clone(include_history=False)
    probe.board_state.cells[_sq("a5").index(files)] = None
    probe.board_state.cells[_sq("a6").index(files)] = Piece(pawn, PieceSide.WHITE)
    captures = hasami_captures_after_move(
        probe,
        from_index=_sq("a5").index(files),
        to_index=_sq("a6").index(files),
        side=PieceSide.WHITE,
    )
    assert captures == (
        _sq("a2").index(files),
        _sq("a3").index(files),
        _sq("a4").index(files),
    )
    after = state.apply_turn(
        Turn(PieceSide.WHITE, [MoveAction(_sq("a5"), _sq("a6"))]),
        record_history=False,
    )
    assert after.board_state.piece_at(_sq("a2").index(files)) is None
    assert after.board_state.piece_at(_sq("a3").index(files)) is None
    assert after.board_state.piece_at(_sq("a4").index(files)) is None



def test_local_game_nanai_play() -> None:
    game = LocalGameService(nanai_checkers())
    assert game.state.side_to_move is PieceSide.WHITE
    action = next(
        candidate
        for candidate in MoveGenerator(game.mode).generate_legal(game.state)
        if isinstance(candidate, MoveAction)
        and candidate.from_square == _sq("a1")
        and candidate.to_square == _sq("a2")
    )
    game.play_turn(Turn(PieceSide.WHITE, [action]))
    assert game.state.side_to_move is PieceSide.BLACK
    assert game.can_undo()


def test_material_win_when_one_piece_left() -> None:
    mode = nanai_checkers()
    state, files = _clear(mode)
    state.board_state.cells[_sq("a1").index(files)] = Piece(MAN, PieceSide.WHITE)
    state.board_state.cells[_sq("b1").index(files)] = Piece(MAN, PieceSide.WHITE)
    state.board_state.cells[_sq("c1").index(files)] = Piece(MAN, PieceSide.WHITE)
    state.board_state.cells[_sq("b6").index(files)] = Piece(MAN, PieceSide.BLACK)
    state.side_to_move = PieceSide.WHITE
    status = evaluate_status(mode, MoveGenerator(mode), state, is_live=True)
    assert status is GameStatus.MATERIAL_WIN

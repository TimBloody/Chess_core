from chess_core.core.board import Square
from chess_core.core.move import MoveAction
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import NotationStyle, format_turn, parse_fen, square_name, to_fen
from chess_core.core.outcome import OutcomeStatus
from chess_core.core.piece import Piece, PieceSide
from chess_core.core.state import GameState
from chess_core.modes.checkers import checkers, checkers_mode_id, compose_checkers_mode
from chess_core.modes.checkers_rules import KING, MAN, CheckersOptions


def _sq(name: str) -> Square:
    return Square(ord(name[0]) - ord("a"), int(name[1]) - 1)


def _idx(name: str) -> int:
    return _sq(name).index(8)


def _clear(state: GameState) -> None:
    for index in state.board_state.cells:
        state.board_state.cells[index] = None


def _place(state: GameState, name: str, piece_type, side: PieceSide) -> None:
    state.board_state.cells[_idx(name)] = Piece(piece_type, side)


def _empty(options: CheckersOptions | None = None) -> tuple[object, GameState]:
    mode = checkers(options)
    state = mode.initial_state()
    _clear(state)
    state.side_to_move = PieceSide.WHITE
    return mode, state


def _destinations(moves: list[MoveAction]) -> set[str]:
    return {square_name(move.to_square) for move in moves}


def test_start_position_has_twenty_four_men_on_dark_squares() -> None:
    mode = checkers()
    state = mode.initial_state()
    occupied = [
        index
        for index, piece in state.board_state.cells.items()
        if piece is not None
    ]
    assert len(occupied) == 24
    assert all((index % 8 + index // 8) % 2 == 0 for index in occupied)
    assert state.side_to_move is PieceSide.WHITE
    whites = sum(
        piece is not None and piece.side is PieceSide.WHITE
        for piece in state.board_state.cells.values()
    )
    assert whites == 12


def test_opening_has_seven_quiet_moves() -> None:
    mode = checkers()
    generator = MoveGenerator(mode)
    moves = generator.generate_legal(mode.initial_state())
    assert len(moves) == 7
    assert all(not move.captured_squares for move in moves)


def test_mandatory_capture_forbids_quiet_moves_and_shorter_sequences() -> None:
    mode, state = _empty()
    _place(state, "c3", MAN, PieceSide.WHITE)
    _place(state, "e3", MAN, PieceSide.WHITE)
    _place(state, "d4", MAN, PieceSide.BLACK)
    _place(state, "f4", MAN, PieceSide.BLACK)
    _place(state, "f6", MAN, PieceSide.BLACK)
    generator = MoveGenerator(mode)
    moves = [move for move in generator.generate_legal(state) if isinstance(move, MoveAction)]
    assert all(move.captured_squares for move in moves)
    assert {len(move.captured_squares) for move in moves} == {2}
    assert {square_name(move.from_square) for move in moves} <= {"c3", "e3"}


def test_optional_capture_allows_quiet_but_not_shorter_captures() -> None:
    mode, state = _empty(CheckersOptions(mandatory_capture=False))
    _place(state, "c3", MAN, PieceSide.WHITE)
    _place(state, "e3", MAN, PieceSide.WHITE)
    _place(state, "d4", MAN, PieceSide.BLACK)
    _place(state, "f4", MAN, PieceSide.BLACK)
    _place(state, "f6", MAN, PieceSide.BLACK)
    generator = MoveGenerator(mode)
    moves = [move for move in generator.generate_legal(state) if isinstance(move, MoveAction)]
    quiet = [move for move in moves if not move.captured_squares]
    captures = [move for move in moves if move.captured_squares]
    assert quiet
    assert captures
    assert {len(move.captured_squares) for move in captures} == {2}


def test_man_cannot_capture_backwards_when_disabled() -> None:
    mode, state = _empty(
        CheckersOptions(mandatory_capture=True, backward_capture=False, flying_king=True)
    )
    _place(state, "c5", MAN, PieceSide.WHITE)
    _place(state, "b4", MAN, PieceSide.BLACK)
    generator = MoveGenerator(mode)
    moves = generator.generate_legal(state)
    assert all(not getattr(move, "captured_squares", ()) for move in moves)
    assert "b6" in _destinations(moves) or "d6" in _destinations(moves)


def test_man_captures_backwards_when_enabled() -> None:
    mode, state = _empty()
    _place(state, "c5", MAN, PieceSide.WHITE)
    _place(state, "b4", MAN, PieceSide.BLACK)
    generator = MoveGenerator(mode)
    moves = [move for move in generator.generate_legal(state) if isinstance(move, MoveAction)]
    assert any(square_name(move.to_square) == "a3" for move in moves)
    assert all(move.captured_squares for move in moves)


def test_short_king_steps_one_square_and_jumps_adjacent() -> None:
    mode, state = _empty(
        CheckersOptions(mandatory_capture=True, backward_capture=True, flying_king=False)
    )
    _place(state, "d4", KING, PieceSide.WHITE)
    generator = MoveGenerator(mode)
    quiet = generator.generate_legal(state)
    assert _destinations(quiet) == {"c3", "e3", "c5", "e5"}

    _place(state, "e5", MAN, PieceSide.BLACK)
    captures = [
        move
        for move in generator.generate_legal(state)
        if isinstance(move, MoveAction) and move.captured_squares
    ]
    assert {square_name(move.to_square) for move in captures} == {"f6"}


def test_flying_king_can_land_any_empty_square_behind_victim() -> None:
    mode, state = _empty()
    _place(state, "a1", KING, PieceSide.WHITE)
    _place(state, "c3", MAN, PieceSide.BLACK)
    generator = MoveGenerator(mode)
    landings = {
        square_name(move.to_square)
        for move in generator.generate_legal(state)
        if isinstance(move, MoveAction)
    }
    assert landings == {"d4", "e5", "f6", "g7", "h8"}


def test_captured_piece_blocks_further_jumps_until_sequence_ends() -> None:
    mode, state = _empty()
    _place(state, "e1", KING, PieceSide.WHITE)
    _place(state, "c3", MAN, PieceSide.BLACK)
    _place(state, "c5", MAN, PieceSide.BLACK)
    _place(state, "e7", MAN, PieceSide.BLACK)
    _place(state, "g5", MAN, PieceSide.BLACK)
    _place(state, "e3", MAN, PieceSide.BLACK)
    generator = MoveGenerator(mode)
    moves = [
        move
        for move in generator.generate_legal(state)
        if isinstance(move, MoveAction)
    ]
    assert moves
    longest = max(len(move.captured_squares) for move in moves)
    assert longest >= 3
    for move in moves:
        captured = [square.index(8) for square in move.captured_squares]
        assert len(captured) == len(set(captured))


def test_man_promotes_and_continues_as_king_during_capture() -> None:
    mode, state = _empty()
    _place(state, "f6", MAN, PieceSide.WHITE)
    _place(state, "e7", MAN, PieceSide.BLACK)
    _place(state, "c7", MAN, PieceSide.BLACK)
    generator = MoveGenerator(mode)
    moves = [
        move
        for move in generator.generate_legal(state)
        if isinstance(move, MoveAction)
    ]
    assert any(
        square_name(move.to_square) == "b6"
        and move.promotion_choice == KING
        and len(move.captured_squares) == 2
        for move in moves
    )
    applied = next(move for move in moves if square_name(move.to_square) == "b6")
    result = mode.apply_turn(state, _turn(state, applied), record_history=False)
    piece = result.board_state.piece_at(_idx("b6"))
    assert piece is not None
    assert piece.piece_type == KING
    assert result.board_state.piece_at(_idx("e7")) is None
    assert result.board_state.piece_at(_idx("c7")) is None


def test_cannot_stop_after_first_jump_of_a_longer_sequence() -> None:
    mode, state = _empty()
    _place(state, "c3", MAN, PieceSide.WHITE)
    _place(state, "d4", MAN, PieceSide.BLACK)
    _place(state, "d6", MAN, PieceSide.BLACK)
    generator = MoveGenerator(mode)
    moves = [
        move
        for move in generator.generate_legal(state)
        if isinstance(move, MoveAction)
    ]
    assert {len(move.captured_squares) for move in moves} == {2}
    assert "e5" not in _destinations(moves)


def test_no_legal_moves_is_a_loss() -> None:
    mode, state = _empty()
    _place(state, "a1", MAN, PieceSide.WHITE)
    _place(state, "b2", MAN, PieceSide.BLACK)
    _place(state, "c3", MAN, PieceSide.BLACK)
    state.side_to_move = PieceSide.WHITE
    outcome = mode.outcome(state)
    assert outcome.status is OutcomeStatus.WIN
    assert outcome.winner is PieceSide.BLACK
    assert outcome.reason == "no_legal_moves"


def test_capturing_last_piece_wins() -> None:
    mode, state = _empty()
    _place(state, "c3", MAN, PieceSide.WHITE)
    _place(state, "d4", MAN, PieceSide.BLACK)
    generator = MoveGenerator(mode)
    move = next(
        action
        for action in generator.generate_legal(state)
        if isinstance(action, MoveAction)
    )
    after = mode.apply_turn(state, _turn(state, move), record_history=False)
    outcome = mode.outcome(after)
    assert outcome.status is OutcomeStatus.WIN
    assert outcome.winner is PieceSide.WHITE


def test_capture_notation_uses_colons() -> None:
    mode, state = _empty()
    _place(state, "c3", MAN, PieceSide.WHITE)
    _place(state, "d4", MAN, PieceSide.BLACK)
    generator = MoveGenerator(mode)
    move = next(
        action
        for action in generator.generate_legal(state)
        if isinstance(action, MoveAction)
    )
    turn = _turn(state, move)
    after = mode.apply_turn(state, turn, record_history=False)
    text = format_turn(turn, before=state, after=after, style=NotationStyle.FROM_TO)
    assert text.startswith("c3:")
    assert "e5" in text


def test_checkers_fen_round_trip() -> None:
    mode = checkers()
    fen = to_fen(mode.initial_state())
    restored = parse_fen(fen, mode)
    assert to_fen(restored) == fen
    assert restored.board_state.piece_at(_idx("a1")).piece_type == MAN


def test_default_mode_id_is_plain_checkers() -> None:
    options = CheckersOptions()
    assert checkers_mode_id(options) == "checkers"
    assert checkers().id == "checkers"
    assert compose_checkers_mode(("mandatory_capture", "backward_capture")).id == (
        "checkers+mandatory_capture+backward_capture"
    )


def _turn(state: GameState, move: MoveAction):
    from chess_core.core.move import Turn

    return Turn(state.side_to_move, [move])

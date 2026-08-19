from chess_core.core.board import Square
from chess_core.core.move import MoveAction, PlaceBlockerAction, Turn
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.infra.network_codec import NetworkCodecError, decode_state, decode_turn, encode_state, encode_turn
from chess_core.modes import register_builtin_modes
from chess_core.modes.chess import classic_chess, crazyhouse, duck_chess
from chess_core.core.registry import default_registry


def setup_module() -> None:
    register_builtin_modes()


def _roundtrip(state):
    encoded = encode_state(state)
    decoded = decode_state(encoded, registry=default_registry)
    return encoded, decoded


def test_classic_state_round_trip() -> None:
    mode = classic_chess()
    state = mode.initial_state()
    _, decoded = _roundtrip(state)
    assert decoded.side_to_move is PieceSide.WHITE
    assert decoded.extras["mode"].id == mode.id
    assert decoded.board_state.piece_at(12).piece_type.name == "pawn"
    assert decoded.extras["castling_rights"] == state.extras["castling_rights"]


def test_turn_round_trip() -> None:
    turn = Turn(
        PieceSide.WHITE,
        [MoveAction(Square(4, 1), Square(4, 3), captured_squares=())],
    )
    decoded = decode_turn(encode_turn(turn))
    assert decoded.side is PieceSide.WHITE
    assert decoded.actions == turn.actions


def test_crazyhouse_hands_round_trip() -> None:
    mode = crazyhouse()
    state = mode.initial_state()
    assert state.hands is not None
    state.hands.add(PieceSide.WHITE, Piece(PieceTypeId("knight"), PieceSide.BLACK))
    _, decoded = _roundtrip(state)
    assert decoded.hands is not None
    assert decoded.hands.count(PieceSide.WHITE, "knight") == 1


def test_duck_blocker_round_trip() -> None:
    mode = duck_chess()
    state = mode.initial_state()
    e2e4 = MoveAction(Square(4, 1), Square(4, 3))
    turn = next(
        candidate
        for candidate in mode.legal_turns(state)
        if candidate.actions and candidate.actions[0] == e2e4
    )
    after = mode.apply_turn(state, turn)
    _, decoded = _roundtrip(after)
    blocker = next(
        piece
        for _index, piece in decoded.board_state.iter_occupied()
        if piece.side is PieceSide.NEUTRAL
    )
    assert blocker.piece_type.name == "blocker"
    assert isinstance(turn.actions[1], PlaceBlockerAction)


def test_unknown_extras_value_is_an_error() -> None:
    state = classic_chess().initial_state()
    state.extras["payload"] = object()
    try:
        encode_state(state)
    except NetworkCodecError as exc:
        assert "cannot encode" in str(exc)
    else:
        raise AssertionError("expected NetworkCodecError")

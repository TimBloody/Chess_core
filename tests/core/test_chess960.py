from chess_core.core.board import Square
from chess_core.core.chess960 import CLASSIC_ARRAY_ID, decode_chess960_back_rank
from chess_core.core.move import MoveAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import PieceSide
from chess_core.modes.chess import chess960, classic_chess


def test_chess960_position_518_matches_classic_array() -> None:
    assert decode_chess960_back_rank(CLASSIC_ARRAY_ID) == (
        "rook",
        "knight",
        "bishop",
        "queen",
        "king",
        "bishop",
        "knight",
        "rook",
    )
    classic = classic_chess().initial_state()
    random960 = chess960(CLASSIC_ARRAY_ID).initial_state()
    for index in range(64):
        left = classic.board_state.piece_at(index)
        right = random960.board_state.piece_at(index)
        if left is None or right is None:
            assert left is right
            continue
        assert left.piece_type == right.piece_type
        assert left.side == right.side


def test_all_chess960_ids_are_unique_and_legal() -> None:
    seen: set[tuple[str, ...]] = set()
    for position_id in range(960):
        rank = decode_chess960_back_rank(position_id)
        seen.add(rank)
        rook_files = [index for index, name in enumerate(rank) if name == "rook"]
        king = rank.index("king")
        assert rook_files[0] < king < rook_files[1]
        bishops = [index for index, name in enumerate(rank) if name == "bishop"]
        assert bishops[0] % 2 != bishops[1] % 2
    assert len(seen) == 960


def test_chess960_castles_by_moving_king_to_rook() -> None:
    mode = chess960(518)
    state = mode.initial_state()
    # Clear the path e1-h1 except king and rook.
    for index in (5, 6):
        state.board_state.cells[index] = None
    generator = MoveGenerator(mode)
    castle = MoveAction(Square(4, 0), Square(7, 0))
    assert castle in generator.generate_legal(state)
    result = state.apply_turn(Turn(PieceSide.WHITE, [castle]))
    assert result.board_state.piece_at(6).piece_type.name == "king"
    assert result.board_state.piece_at(5).piece_type.name == "rook"
    assert result.board_state.piece_at(7) is None

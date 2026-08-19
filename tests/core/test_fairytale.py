from chess_core.core.board import Square
from chess_core.core.move import MoveAction
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.modes.chess import fairytale_chess


def sq(alg: str) -> Square:
    return Square(ord(alg[0]) - ord("a"), int(alg[1]) - 1)


def move(frm: str, to: str) -> MoveAction:
    return MoveAction(sq(frm), sq(to))


def piece(name: str, side: PieceSide = PieceSide.WHITE) -> Piece:
    return Piece(PieceTypeId(name), side)


def position(mode, cells: dict[int, Piece], side: PieceSide = PieceSide.WHITE):
    state = mode.initial_state()
    state.board_state.cells = {
        index: cells.get(index) for index in range(mode.board.shape.cell_count)
    }
    state.side_to_move = side
    return state


def legal_from_square(mode, state, square: str) -> set[MoveAction]:
    generator = MoveGenerator(mode)
    return set(generator.generate_legal_for_square(state, sq(square)))


def test_fairytale_mode_is_playable_v1() -> None:
    mode = fairytale_chess()
    assert not mode.is_dummy
    assert mode.modifier_ids == ("fairytale",)
    assert mode.move_resolver is not None
    state = mode.initial_state()
    assert len(MoveGenerator(mode).generate_legal(state)) == 20


def test_rook_on_a_file_slides_like_rook() -> None:
    mode = fairytale_chess()
    state = position(
        mode,
        {
            sq("a4").index(8): piece("rook"),
            sq("e1").index(8): piece("king"),
            sq("e8").index(8): piece("king", PieceSide.BLACK),
        },
    )
    legal = legal_from_square(mode, state, "a4")
    assert move("a4", "a8") in legal
    assert move("a4", "b6") not in legal


def test_knight_on_a_file_moves_as_rook() -> None:
    mode = fairytale_chess()
    state = position(
        mode,
        {
            sq("a4").index(8): piece("knight"),
            sq("e1").index(8): piece("king"),
            sq("e8").index(8): piece("king", PieceSide.BLACK),
        },
    )
    legal = legal_from_square(mode, state, "a4")
    assert move("a4", "a8") in legal
    assert move("a4", "b6") not in legal


def test_bishop_on_b_file_moves_as_knight() -> None:
    mode = fairytale_chess()
    state = position(
        mode,
        {
            sq("b4").index(8): piece("bishop"),
            sq("e1").index(8): piece("king"),
            sq("e8").index(8): piece("king", PieceSide.BLACK),
        },
    )
    legal = legal_from_square(mode, state, "b4")
    assert move("b4", "c6") in legal
    assert move("b4", "a5") not in legal


def test_queen_on_a_file_still_moves_as_queen() -> None:
    mode = fairytale_chess()
    state = position(
        mode,
        {
            sq("a4").index(8): piece("queen"),
            sq("e1").index(8): piece("king"),
            sq("e8").index(8): piece("king", PieceSide.BLACK),
        },
    )
    legal = legal_from_square(mode, state, "a4")
    assert move("a4", "a8") in legal
    assert move("a4", "d4") in legal


def test_king_and_pawn_unchanged_on_a_file() -> None:
    mode = fairytale_chess()
    king_state = position(
        mode,
        {
            sq("a4").index(8): piece("king"),
            sq("e8").index(8): piece("king", PieceSide.BLACK),
        },
    )
    king_legal = legal_from_square(mode, king_state, "a4")
    assert move("a4", "a5") in king_legal
    assert move("a4", "a8") not in king_legal

    pawn_state = position(
        mode,
        {
            sq("a4").index(8): piece("pawn"),
            sq("e1").index(8): piece("king"),
            sq("e8").index(8): piece("king", PieceSide.BLACK),
        },
    )
    pawn_legal = legal_from_square(mode, pawn_state, "a4")
    assert move("a4", "a5") in pawn_legal
    assert move("a4", "a8") not in pawn_legal


def test_attack_detection_uses_file_resolved_patterns() -> None:
    mode = fairytale_chess()
    state = position(
        mode,
        {
            sq("b4").index(8): piece("rook"),
            sq("c6").index(8): piece("king", PieceSide.BLACK),
            sq("e1").index(8): piece("king"),
        },
        side=PieceSide.BLACK,
    )
    generator = MoveGenerator(mode)
    assert generator.is_square_attacked(state, sq("c6"), PieceSide.WHITE)
    assert generator.is_in_check(state)

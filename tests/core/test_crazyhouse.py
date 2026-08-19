from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.modes.chess import classic_chess, crazyhouse
from chess_core.modes.crazyhouse_rules import (
    CrazyhouseDropRule,
    demote_captured_piece,
    mark_promoted,
)
from chess_core.ui.piece_assets import hand_slot_types


def _piece(name: str, side: PieceSide = PieceSide.WHITE) -> Piece:
    return Piece(PieceTypeId(name), side)


def _empty_classic_state():
    state = classic_chess().initial_state()
    cell_count = state.board_state.board.shape.cell_count
    state.board_state.cells = {index: None for index in range(cell_count)}
    return state


def test_pawn_drop_illegal_on_first_and_last_rank() -> None:
    rule = CrazyhouseDropRule()
    state = _empty_classic_state()
    pawn = PieceTypeId("pawn")
    files = state.board_state.board.shape.files
    last_rank = state.board_state.board.shape.ranks - 1

    for file in range(files):
        assert rule.can_drop(pawn, file, state) is False
        assert rule.can_drop(pawn, last_rank * files + file, state) is False


def test_pawn_drop_legal_on_ranks_1_through_6_when_empty() -> None:
    rule = CrazyhouseDropRule()
    state = _empty_classic_state()
    pawn = PieceTypeId("pawn")
    files = state.board_state.board.shape.files
    ranks = state.board_state.board.shape.ranks

    for rank in range(1, ranks - 1):
        for file in range(files):
            assert rule.can_drop(pawn, rank * files + file, state) is True


def test_knight_and_queen_drop_legal_on_first_and_last_rank_if_empty() -> None:
    rule = CrazyhouseDropRule()
    state = _empty_classic_state()
    files = state.board_state.board.shape.files
    last_rank = state.board_state.board.shape.ranks - 1

    for piece_name in ("knight", "queen"):
        piece_type = PieceTypeId(piece_name)
        assert rule.can_drop(piece_type, 0, state) is True
        assert rule.can_drop(piece_type, last_rank * files, state) is True
        assert rule.can_drop(piece_type, files - 1, state) is True
        assert rule.can_drop(piece_type, last_rank * files + files - 1, state) is True


def test_drop_illegal_on_occupied_square() -> None:
    rule = CrazyhouseDropRule()
    state = _empty_classic_state()
    occupied = 27  # d4: rank 3, file 3
    state.board_state.cells[occupied] = _piece("rook", PieceSide.BLACK)

    assert rule.can_drop(PieceTypeId("knight"), occupied, state) is False
    assert rule.can_drop(PieceTypeId("queen"), occupied, state) is False
    assert rule.can_drop(PieceTypeId("pawn"), occupied, state) is False
    assert rule.can_drop(PieceTypeId("pawn"), occupied + 1, state) is True


def test_allowed_faces_is_none() -> None:
    rule = CrazyhouseDropRule()
    for name in ("pawn", "knight", "bishop", "rook", "queen", "king"):
        assert rule.allowed_faces(PieceTypeId(name)) is None


def test_demote_captured_promoted_queen_becomes_pawn() -> None:
    queen = Piece(
        PieceTypeId("queen"),
        PieceSide.BLACK,
        state={"promoted_from": "pawn"},
    )
    demoted = demote_captured_piece(queen)

    assert demoted.piece_type == PieceTypeId("pawn")
    assert demoted.side is PieceSide.BLACK
    assert demoted.state is None
    assert queen.piece_type == PieceTypeId("queen")
    assert queen.state == {"promoted_from": "pawn"}


def test_demote_captured_normal_rook_stays_rook() -> None:
    rook = Piece(PieceTypeId("rook"), PieceSide.WHITE)
    demoted = demote_captured_piece(rook)

    assert demoted.piece_type == PieceTypeId("rook")
    assert demoted.side is PieceSide.WHITE
    assert demoted.state is None
    assert demoted is not rook


def test_mark_promoted_sets_promoted_from() -> None:
    queen = Piece(PieceTypeId("queen"), PieceSide.WHITE)
    marked = mark_promoted(queen)

    assert marked.piece_type == PieceTypeId("queen")
    assert marked.side is PieceSide.WHITE
    assert marked.state == {"promoted_from": "pawn"}
    assert queen.state is None

    from_knight = mark_promoted(queen, "knight")
    assert from_knight.state == {"promoted_from": "knight"}


def test_out_of_range_index_is_not_droppable() -> None:
    rule = CrazyhouseDropRule()
    state = _empty_classic_state()
    cell_count = state.board_state.board.shape.cell_count
    pawn = PieceTypeId("pawn")
    knight = PieceTypeId("knight")

    for index in (-1, cell_count, cell_count + 1, 10_000):
        assert rule.can_drop(pawn, index, state) is False
        assert rule.can_drop(knight, index, state) is False


def test_crazyhouse_hand_reserves_five_droppable_types() -> None:
    assert hand_slot_types(crazyhouse()) == ("pawn", "knight", "bishop", "rook", "queen")

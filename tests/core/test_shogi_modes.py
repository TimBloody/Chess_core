"""Shogi, minishogi, Kyoto, and Dobutsu mode contracts."""

from chess_core.app.game import GameStatus, LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import DropAction, MoveAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import VictoryKind
from chess_core.core.state import HandsState
from chess_core.modes.shogi import dobutsu_shogi, kyoto_shogi, minishogi, shogi
from chess_core.ui.piece_assets import (
    hand_slot_types,
    parse_display_key,
    piece_svg_key,
    piece_svg_key_for,
)


def _piece(name: str, side: PieceSide) -> Piece:
    return Piece(PieceTypeId(name), side)


def _clear(state, cells: dict[int, Piece], side: PieceSide) -> None:
    state.board_state.cells = {
        index: cells.get(index) for index in range(state.board_state.board.shape.cell_count)
    }
    state.side_to_move = side


def test_shogi_family_uses_black_first_and_lishogi_assets() -> None:
    for factory in (shogi, minishogi, kyoto_shogi, dobutsu_shogi):
        mode = factory()
        state = mode.initial_state()
        assert mode.starting_side is PieceSide.BLACK
        assert mode.default_view_side is PieceSide.BLACK
        assert mode.asset_family in {"shogi", "dobutsu"}
        assert mode.facing_opponent is True
        assert state.side_to_move is PieceSide.BLACK
        assert mode.drop_rule is not None
        assert state.hands is not None
        black_back = max(
            index
            for index, piece in state.board_state.cells.items()
            if piece is not None and piece.side is PieceSide.BLACK
        )
        white_back = min(
            index
            for index, piece in state.board_state.cells.items()
            if piece is not None and piece.side is PieceSide.WHITE
        )
        assert black_back // mode.board.shape.files == mode.board.shape.ranks - 1
        assert white_back // mode.board.shape.files == 0
    assert dobutsu_shogi().asset_family == "dobutsu"
    assert shogi().asset_family == "shogi"


def test_shogi_family_uses_uncolored_wedges_not_painted_gote() -> None:
    for factory in (shogi, minishogi, kyoto_shogi, dobutsu_shogi):
        mode = factory()
        for piece_type in mode.pieces.all_types():
            for side in (PieceSide.BLACK, PieceSide.WHITE):
                key = piece_svg_key_for(mode, piece_type.id.name, side)
                stem, owner = parse_display_key(key)
                filename = stem.rsplit("/", 1)[-1]
                assert filename.startswith("0"), key
                assert not filename.startswith("1")
                assert owner is side


def test_standard_shogi_start_and_pawn_advance() -> None:
    mode = shogi()
    state = mode.initial_state()
    assert state.board_state.piece_at(76).piece_type.name == "king"
    assert state.board_state.piece_at(76).side is PieceSide.BLACK
    assert piece_svg_key(mode, state.board_state.piece_at(76)) == "0OU@b"
    assert piece_svg_key(mode, state.board_state.piece_at(4)) == "0OU@w"
    pawn = MoveAction(Square(4, 6), Square(4, 5))
    assert pawn in MoveGenerator(mode).generate_legal(state)
    after = state.apply_turn(Turn(PieceSide.BLACK, [pawn]))
    assert after.board_state.piece_at(49).piece_type.name == "pawn"
    assert after.side_to_move is PieceSide.WHITE


def test_shogi_nifu_and_dead_pawn_drop() -> None:
    mode = shogi()
    state = mode.initial_state()
    _clear(
        state,
        {
            4: _piece("king", PieceSide.WHITE),
            76: _piece("king", PieceSide.BLACK),
            13: _piece("pawn", PieceSide.BLACK),
        },
        PieceSide.BLACK,
    )
    state.hands = HandsState({PieceSide.BLACK: [_piece("pawn", PieceSide.BLACK)]})
    legal = MoveGenerator(mode).generate_legal(state)
    assert DropAction(PieceTypeId("pawn"), Square(4, 3)) not in legal
    assert DropAction(PieceTypeId("pawn"), Square(2, 0)) not in legal
    assert DropAction(PieceTypeId("pawn"), Square(2, 4)) in legal


def test_shogi_optional_and_mandatory_promotion() -> None:
    mode = shogi()
    state = mode.initial_state()
    _clear(
        state,
        {
            4: _piece("king", PieceSide.WHITE),
            76: _piece("king", PieceSide.BLACK),
            12: _piece("pawn", PieceSide.BLACK),
            23: _piece("silver", PieceSide.BLACK),
        },
        PieceSide.BLACK,
    )
    generator = MoveGenerator(mode)
    pawn_moves = [
        action
        for action in generator.generate_legal(state)
        if isinstance(action, MoveAction) and action.from_square == Square(3, 1)
    ]
    assert MoveAction(Square(3, 1), Square(3, 0), PieceTypeId("tokin")) in pawn_moves
    assert all(action.promotion_choice is not None for action in pawn_moves)

    silver_moves = [
        action
        for action in generator.generate_legal(state)
        if isinstance(action, MoveAction) and action.from_square == Square(5, 2)
    ]
    assert MoveAction(Square(5, 2), Square(5, 1)) in silver_moves
    assert MoveAction(Square(5, 2), Square(5, 1), PieceTypeId("promoted_silver")) in silver_moves


def test_shogi_captured_tokin_returns_as_pawn() -> None:
    mode = shogi()
    state = mode.initial_state()
    tokin = _piece("tokin", PieceSide.WHITE)
    _clear(
        state,
        {
            4: _piece("king", PieceSide.WHITE),
            76: _piece("king", PieceSide.BLACK),
            67: _piece("rook", PieceSide.BLACK),
            58: tokin,
        },
        PieceSide.BLACK,
    )
    after = state.apply_turn(Turn(PieceSide.BLACK, [MoveAction(Square(4, 7), Square(4, 6))]))
    assert after.hands is not None
    assert after.hands.count(PieceSide.BLACK, "pawn") == 1
    assert after.hands.count(PieceSide.BLACK, "tokin") == 0


def test_minishogi_start_and_one_rank_zone() -> None:
    mode = minishogi()
    state = mode.initial_state()
    assert mode.board.shape.files == 5
    assert state.board_state.piece_at(24).piece_type.name == "king"
    assert state.board_state.piece_at(24).side is PieceSide.BLACK
    assert state.board_state.piece_at(0).piece_type.name == "king"
    generator = MoveGenerator(mode)
    _clear(
        state,
        {
            4: _piece("king", PieceSide.WHITE),
            24: _piece("king", PieceSide.BLACK),
            6: _piece("bishop", PieceSide.BLACK),
        },
        PieceSide.BLACK,
    )
    legal = generator.generate_legal(state)
    assert MoveAction(Square(1, 1), Square(0, 0)) in legal
    assert MoveAction(Square(1, 1), Square(0, 0), PieceTypeId("horse")) in legal
    assert MoveAction(Square(1, 1), Square(2, 2)) in legal
    assert MoveAction(Square(1, 1), Square(2, 2), PieceTypeId("horse")) not in legal


def test_kyoto_flip_and_face_drop() -> None:
    mode = kyoto_shogi()
    assert mode.initial_state().board_state.piece_at(22).piece_type.name == "king"
    state = mode.initial_state()
    _clear(
        state,
        {
            2: _piece("king", PieceSide.WHITE),
            22: _piece("king", PieceSide.BLACK),
            20: _piece("pawn", PieceSide.BLACK),
        },
        PieceSide.BLACK,
    )
    flipped = state.apply_turn(Turn(PieceSide.BLACK, [MoveAction(Square(0, 4), Square(0, 3))]))
    assert flipped.board_state.piece_at(15).piece_type.name == "rook"

    drop_state = mode.initial_state()
    _clear(
        drop_state,
        {2: _piece("king", PieceSide.WHITE), 22: _piece("king", PieceSide.BLACK)},
        PieceSide.BLACK,
    )
    drop_state.hands = HandsState({PieceSide.BLACK: [_piece("pawn", PieceSide.BLACK)]})
    result = drop_state.apply_turn(
        Turn(PieceSide.BLACK, [DropAction(PieceTypeId("pawn"), Square(1, 1), "rook")])
    )
    assert result.board_state.piece_at(6).piece_type.name == "rook"


def test_dobutsu_chick_promotes_and_lion_try_wins() -> None:
    mode = dobutsu_shogi()
    kinds = (
        mode.victory
        if isinstance(mode.victory, tuple)
        else (mode.victory,)
    )
    assert {condition.kind for condition in kinds} == {
        VictoryKind.KING_CAPTURE,
        VictoryKind.KING_REACHES_ZONE,
    }
    state = mode.initial_state()
    assert state.board_state.piece_at(10).piece_type.name == "lion"
    assert piece_svg_key(mode, state.board_state.piece_at(10)) == "dobutsu/0OU@b"
    _clear(
        state,
        {
            0: _piece("lion", PieceSide.WHITE),
            10: _piece("lion", PieceSide.BLACK),
            4: _piece("chick", PieceSide.BLACK),
        },
        PieceSide.BLACK,
    )
    promoted = [
        action
        for action in MoveGenerator(mode).generate_legal(state)
        if isinstance(action, MoveAction) and action.from_square == Square(1, 1)
    ]
    assert MoveAction(Square(1, 1), Square(1, 0), PieceTypeId("hen")) in promoted

    try_state = mode.initial_state()
    _clear(
        try_state,
        {
            0: _piece("giraffe", PieceSide.WHITE),
            2: _piece("lion", PieceSide.WHITE),
            4: _piece("lion", PieceSide.BLACK),
        },
        PieceSide.BLACK,
    )
    game = LocalGameService(mode, initial_state=try_state)
    game.play(MoveAction(Square(1, 1), Square(0, 0)))
    assert game.status() is GameStatus.VARIANT_WIN


def test_dobutsu_capturing_lion_wins() -> None:
    mode = dobutsu_shogi()
    state = mode.initial_state()
    _clear(
        state,
        {
            1: _piece("lion", PieceSide.WHITE),
            4: _piece("giraffe", PieceSide.BLACK),
            10: _piece("lion", PieceSide.BLACK),
        },
        PieceSide.BLACK,
    )
    game = LocalGameService(mode, initial_state=state)
    game.play(MoveAction(Square(1, 1), Square(1, 0)))
    assert game.status() is GameStatus.CHECKMATE
    assert game.state.board_state.piece_at(1).piece_type.name == "giraffe"


def test_hand_slot_types_cover_every_droppable_face() -> None:
    assert set(hand_slot_types(shogi())) == {
        "pawn",
        "lance",
        "knight",
        "silver",
        "gold",
        "bishop",
        "rook",
    }
    assert set(hand_slot_types(kyoto_shogi())) == {
        "tokin",
        "lance",
        "silver",
        "bishop",
        "gold",
        "knight",
        "pawn",
        "rook",
    }
    assert set(hand_slot_types(dobutsu_shogi())) == {"chick", "giraffe", "elephant"}

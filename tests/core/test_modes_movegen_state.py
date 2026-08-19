import pytest

from chess_core.core.board import Square
from chess_core.core.move import DropAction, MoveAction, PlaceBlockerAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import (
    MovePattern,
    MovePatternKind,
    Piece,
    PieceCatalog,
    PieceSide,
    PieceType,
    PieceTypeId,
)
from chess_core.core.state import HandsState
from chess_core.core.topology import CylindricalFilesTopology
from chess_core.modes.chess import classic_chess, cylindrical_chess, duck_chess
from chess_core.modes.shogi import dobutsu_shogi, kyoto_shogi, minishogi, shogi


def _piece(name: str, side: PieceSide) -> Piece:
    return Piece(PieceTypeId(name), side)


def _position(mode, cells, side=PieceSide.WHITE):
    state = mode.initial_state()
    state.board_state.cells = {
        index: cells.get(index) for index in range(mode.board.shape.cell_count)
    }
    state.side_to_move = side
    return state


def test_piece_catalog_registration_and_mask_key_resolution() -> None:
    catalog = PieceCatalog()
    definition = PieceType(
        PieceTypeId("archer"),
        (MovePattern(MovePatternKind.CUSTOM_MASK, pattern_key="archer-v1"),),
    )
    catalog.register(definition)
    piece = Piece(PieceTypeId("archer"), PieceSide.WHITE)

    assert catalog.get(PieceTypeId("archer")) is definition
    assert catalog.resolve_move_mask_key(piece, Square(0, 0), object()) == "archer-v1"
    with pytest.raises(ValueError):
        catalog.register(definition)


def test_required_mode_factories_are_fully_configured() -> None:
    classic = classic_chess()
    cylinder = cylindrical_chess()
    duck = duck_chess()
    kyoto = kyoto_shogi()
    mini = minishogi()
    standard = shogi()
    dobutsu = dobutsu_shogi()

    assert classic.board.shape.cell_count == 64
    assert len(classic.initial_state().board_state.cells) == 64
    assert sum(piece is not None for piece in classic.initial_state().board_state.cells.values()) == 32
    assert classic.ray_table is not None
    assert classic.promotion_rule is not None
    assert classic.protects_royal()
    assert not classic.allows_royal_capture()
    assert isinstance(cylinder.topology, CylindricalFilesTopology)
    assert cylinder.ray_table is not None
    assert [step.label for step in duck.turn_scenario.steps] == ["move", "duck"]
    assert duck.allows_royal_capture()
    assert not duck.lose_on_no_legal_moves()
    assert kyoto.board.shape.cell_count == 25
    assert kyoto.drop_rule is not None
    assert kyoto.initial_state().hands is not None
    assert sum(piece is not None for piece in kyoto.initial_state().board_state.cells.values()) == 10
    assert kyoto.starting_side is PieceSide.BLACK
    assert mini.board.shape.cell_count == 25
    assert mini.promotion_rule is not None
    assert standard.board.shape.cell_count == 81
    assert standard.drop_rule is not None
    assert dobutsu.board.shape.cell_count == 12
    assert dobutsu.initial_state().side_to_move is PieceSide.BLACK


def test_classic_start_has_twenty_pseudo_and_legal_moves() -> None:
    mode = classic_chess()
    generator = MoveGenerator(mode)

    assert len(generator.generate_pseudo_legal(mode.initial_state())) == 20
    assert len(generator.generate_legal(mode.initial_state())) == 20


def test_fools_mate_has_no_legal_reply() -> None:
    mode = classic_chess()
    state = mode.initial_state()
    for move in (
        MoveAction(Square(5, 1), Square(5, 2)),
        MoveAction(Square(4, 6), Square(4, 4)),
        MoveAction(Square(6, 1), Square(6, 3)),
        MoveAction(Square(3, 7), Square(7, 3)),
    ):
        state = state.apply_turn(Turn(state.side_to_move, [move]))

    assert MoveGenerator(mode).generate_legal(state) == []


def test_legal_generation_filters_move_exposing_king() -> None:
    mode = classic_chess()
    state = _position(
        mode,
        {
            4: _piece("king", PieceSide.WHITE),
            12: _piece("rook", PieceSide.WHITE),
            60: _piece("rook", PieceSide.BLACK),
            56: _piece("king", PieceSide.BLACK),
        },
    )
    generator = MoveGenerator(mode)

    assert MoveAction(Square(4, 1), Square(3, 1)) in generator.generate_pseudo_legal(state)
    assert MoveAction(Square(4, 1), Square(3, 1)) not in generator.generate_legal(state)


def test_state_applies_double_pawn_move_and_castling() -> None:
    mode = classic_chess()
    state = mode.initial_state().apply_turn(
        Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))])
    )
    assert state.side_to_move is PieceSide.BLACK
    assert state.extras["en_passant"] == Square(4, 2)

    castle_state = _position(
        mode,
        {
            4: _piece("king", PieceSide.WHITE),
            7: _piece("rook", PieceSide.WHITE),
            56: _piece("king", PieceSide.BLACK),
        },
    )
    castle_state.extras["castling_rights"] = {"K"}
    castle_state.extras["mode"] = mode
    castle = MoveAction(Square(4, 0), Square(6, 0))
    assert castle in MoveGenerator(mode).generate_legal(castle_state)
    result = castle_state.apply_turn(Turn(PieceSide.WHITE, [castle]))
    assert result.board_state.piece_at(6).piece_type.name == "king"
    assert result.board_state.piece_at(5).piece_type.name == "rook"
    assert result.board_state.piece_at(7) is None


def test_state_applies_en_passant_and_capture_to_hand() -> None:
    mode = classic_chess()
    state = _position(
        mode,
        {
            4: _piece("king", PieceSide.WHITE),
            36: _piece("pawn", PieceSide.WHITE),
            35: _piece("pawn", PieceSide.BLACK),
            60: _piece("king", PieceSide.BLACK),
        },
    )
    state.extras.update({"mode": mode, "en_passant": Square(3, 5)})
    state.hands = HandsState()
    result = state.apply_turn(
        Turn(PieceSide.WHITE, [MoveAction(Square(4, 4), Square(3, 5))])
    )

    assert result.board_state.piece_at(35) is None
    assert result.board_state.piece_at(43).piece_type.name == "pawn"
    assert result.hands.count(PieceSide.WHITE, "pawn") == 1


def test_duck_turn_requires_blocker_and_kyoto_move_flips_piece() -> None:
    duck = duck_chess()
    state = duck.initial_state()
    incomplete = Turn(
        PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 2))]
    )
    with pytest.raises(ValueError, match="scenario"):
        state.apply_turn(incomplete)
    complete = Turn(
        PieceSide.WHITE,
        [
            MoveAction(Square(4, 1), Square(4, 2)),
            PlaceBlockerAction(Square(4, 3)),
        ],
    )
    after_white = state.apply_turn(complete)
    assert after_white.board_state.piece_at(28).side is PieceSide.NEUTRAL
    after_black = after_white.apply_turn(
        Turn(
            PieceSide.BLACK,
            [
                MoveAction(Square(4, 6), Square(4, 5)),
                PlaceBlockerAction(Square(3, 3)),
            ],
        )
    )
    assert after_black.board_state.piece_at(28) is None
    assert after_black.board_state.piece_at(27).side is PieceSide.NEUTRAL
    assert sum(
        piece is not None and piece.side is PieceSide.NEUTRAL
        for piece in after_black.board_state.cells.values()
    ) == 1

    kyoto = kyoto_shogi()
    kyoto_state = _position(
        kyoto,
        {
            0: _piece("pawn", PieceSide.WHITE),
            2: _piece("king", PieceSide.WHITE),
            22: _piece("king", PieceSide.BLACK),
        },
    )
    kyoto_state.extras["mode"] = kyoto
    flipped = kyoto_state.apply_turn(
        Turn(PieceSide.WHITE, [MoveAction(Square(0, 0), Square(0, 1))])
    )
    assert flipped.board_state.piece_at(5).piece_type.name == "rook"


def test_kyoto_drop_validates_face_choice() -> None:
    mode = kyoto_shogi()
    state = _position(
        mode,
        {2: _piece("king", PieceSide.WHITE), 22: _piece("king", PieceSide.BLACK)},
    )
    state.extras["mode"] = mode
    state.hands = HandsState({PieceSide.WHITE: [_piece("pawn", PieceSide.WHITE)]})
    result = state.apply_turn(
        Turn(PieceSide.WHITE, [DropAction(PieceTypeId("pawn"), Square(1, 1), "rook")])
    )
    assert result.board_state.piece_at(6).piece_type.name == "rook"

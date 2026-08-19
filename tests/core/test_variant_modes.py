"""Wired Chess960, Crazyhouse, and Duck Chess mode contracts."""

from chess_core.app.game import GameStatus, LocalGameService
from chess_core.core.board import Square
from chess_core.core.castling import encode_castling
from chess_core.core.move import DropAction, MoveAction, PlaceBlockerAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import VictoryKind
from chess_core.core.state import HandsState
from chess_core.modes.chess import chess960, crazyhouse, duck_chess


def _piece(name: str, side: PieceSide) -> Piece:
    return Piece(PieceTypeId(name), side)


def _clear_except(state, cells: dict[int, Piece]) -> None:
    state.board_state.cells = {
        index: cells.get(index) for index in range(state.board_state.board.shape.cell_count)
    }


def test_chess960_position_518_matches_classic_array_and_castles() -> None:
    mode = chess960(518)
    state = mode.initial_state()
    assert state.extras["chess960_position"] == 518
    assert state.board_state.piece_at(4).piece_type.name == "king"
    assert state.board_state.piece_at(0).piece_type.name == "rook"
    _clear_except(
        state,
        {
            4: _piece("king", PieceSide.WHITE),
            7: _piece("rook", PieceSide.WHITE),
            60: _piece("king", PieceSide.BLACK),
        },
    )
    state.extras["castling_rights"] = {"K"}
    castle = MoveAction(Square(4, 0), Square(6, 0))
    assert castle in MoveGenerator(mode).generate_legal(state)
    after = state.apply_turn(Turn(PieceSide.WHITE, [castle]))
    assert after.board_state.piece_at(6).piece_type.name == "king"
    assert after.board_state.piece_at(5).piece_type.name == "rook"


def test_chess960_castles_to_c_file_when_king_starts_elsewhere() -> None:
    mode = chess960(0)
    back = [mode.start_cells[file].piece_type.name for file in range(8)]
    king_file = back.index("king")
    rook_files = [file for file, name in enumerate(back) if name == "rook"]
    state = mode.initial_state()
    _clear_except(
        state,
        {
            king_file: _piece("king", PieceSide.WHITE),
            rook_files[0]: _piece("rook", PieceSide.WHITE),
            rook_files[1]: _piece("rook", PieceSide.WHITE),
            60: _piece("king", PieceSide.BLACK),
        },
    )
    state.extras["castling_rights"] = {"Q"}
    queenside = next(
        path for path in mode.castling_rule.paths(state, PieceSide.WHITE) if path.right == "Q"
    )
    assert queenside.king_to == Square(2, 0)
    assert queenside.rook_to == Square(3, 0)
    encoded = encode_castling(queenside)
    assert encoded in MoveGenerator(mode).generate_legal(state)
    after = state.apply_turn(Turn(PieceSide.WHITE, [encoded]))
    assert after.board_state.piece_at(2).piece_type.name == "king"
    assert after.board_state.piece_at(3).piece_type.name == "rook"


def test_crazyhouse_drops_and_promoted_capture_becomes_pawn() -> None:
    mode = crazyhouse()
    assert mode.drop_rule is not None
    generator = MoveGenerator(mode)
    state = mode.initial_state()
    _clear_except(
        state,
        {
            4: _piece("king", PieceSide.WHITE),
            60: _piece("king", PieceSide.BLACK),
        },
    )
    state.hands = HandsState(
        {
            PieceSide.WHITE: [
                _piece("knight", PieceSide.WHITE),
                _piece("pawn", PieceSide.WHITE),
            ]
        }
    )
    legal = generator.generate_legal(state)
    assert DropAction(PieceTypeId("knight"), Square(0, 0)) in legal
    assert DropAction(PieceTypeId("pawn"), Square(0, 0)) not in legal
    assert DropAction(PieceTypeId("pawn"), Square(0, 7)) not in legal
    assert DropAction(PieceTypeId("pawn"), Square(3, 3)) in legal

    capture_state = mode.initial_state()
    promoted = _piece("queen", PieceSide.BLACK)
    promoted.state = {"promoted_from": "pawn"}
    _clear_except(
        capture_state,
        {
            4: _piece("king", PieceSide.WHITE),
            12: _piece("rook", PieceSide.WHITE),
            20: promoted,
            60: _piece("king", PieceSide.BLACK),
        },
    )
    capture_state.hands = HandsState()
    after = capture_state.apply_turn(
        Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 2))])
    )
    assert after.hands is not None
    assert after.hands.count(PieceSide.WHITE, "pawn") == 1
    assert after.hands.count(PieceSide.WHITE, "queen") == 0


def test_duck_allows_move_into_check_and_king_capture_wins() -> None:
    mode = duck_chess()
    assert mode.victory.kind is VictoryKind.KING_CAPTURE
    assert mode.victory.lose_on_no_legal_moves is False
    state = mode.initial_state()
    _clear_except(
        state,
        {
            4: _piece("king", PieceSide.WHITE),
            60: _piece("rook", PieceSide.BLACK),
            56: _piece("king", PieceSide.BLACK),
        },
    )
    king_into_file = MoveAction(Square(4, 0), Square(4, 1))
    assert king_into_file in MoveGenerator(mode).generate_legal(state)

    capture_state = mode.initial_state()
    _clear_except(
        capture_state,
        {
            4: _piece("king", PieceSide.WHITE),
            0: _piece("rook", PieceSide.WHITE),
            56: _piece("king", PieceSide.BLACK),
        },
    )
    game = LocalGameService(mode, initial_state=capture_state)
    game.play_turn(
        Turn(
            PieceSide.WHITE,
            [
                MoveAction(Square(0, 0), Square(0, 7)),
                PlaceBlockerAction(Square(4, 3)),
            ],
        )
    )
    assert game.state.board_state.piece_at(56).piece_type.name == "rook"
    assert game.status() is GameStatus.CHECKMATE

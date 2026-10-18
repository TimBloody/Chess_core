"""Threefold repetition: same side, occupancy, pockets, and castling-like rights."""

from __future__ import annotations

from chess_core.app.game import GameStatus, LocalGameService, transcript_result
from chess_core.core.board import Square
from chess_core.core.move import DropAction, MoveAction, Turn
from chess_core.core.notation import parse_fen
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.repetition import is_threefold, position_key, repetition_count, seed_repetition_log
from chess_core.core.state import HandsState
from chess_core.modes.chess import classic_chess
from chess_core.modes.gobblet import gobblet
from chess_core.modes.gobblet_rules import GOBBLET_LARGE, GOBBLET_SMALL, stack_at, sync_cell
from chess_core.modes.shogi import shogi
from chess_core.tools.classical_demo import parse_move


def test_side_to_move_distinguishes_otherwise_identical_positions() -> None:
    mode = classic_chess()
    white = parse_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1", mode)
    black = parse_fen("4k3/8/8/8/8/8/8/4K3 b - - 0 1", mode)
    assert position_key(white) != position_key(black)


def test_castling_rights_distinguish_same_pieces() -> None:
    mode = classic_chess()
    with_rights = parse_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", mode)
    without = parse_fen("r3k2r/8/8/8/8/8/8/R3K2R w - - 0 1", mode)
    assert position_key(with_rights) != position_key(without)


def test_unusable_en_passant_square_does_not_distinguish_positions() -> None:
    mode = classic_chess()
    with_ep = parse_fen("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1", mode)
    without_ep = parse_fen("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1", mode)
    assert position_key(with_ep) == position_key(without_ep)


def test_halfmove_clock_is_not_part_of_position_identity() -> None:
    mode = classic_chess()
    early = parse_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1", mode)
    late = parse_fen("4k3/8/8/8/8/8/8/4K3 w - - 12 8", mode)
    assert position_key(early) == position_key(late)


def test_capturable_en_passant_distinguishes_positions() -> None:
    mode = classic_chess()
    with_ep = parse_fen("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", mode)
    without_ep = parse_fen("4k3/8/8/3pP3/8/8/8/4K3 w - - 0 1", mode)
    assert position_key(with_ep) != position_key(without_ep)


def test_pockets_distinguish_identical_boards() -> None:
    mode = shogi()
    empty_hand = mode.initial_state()
    with_pawn = empty_hand.clone()
    with_pawn.hands = HandsState({PieceSide.WHITE: [Piece(PieceTypeId("pawn"), PieceSide.WHITE)]})
    assert position_key(empty_hand) != position_key(with_pawn)


def test_pocket_order_does_not_matter() -> None:
    mode = shogi()
    state = mode.initial_state()
    a = state.clone()
    b = state.clone()
    a.hands = HandsState(
        {
            PieceSide.WHITE: [
                Piece(PieceTypeId("gold"), PieceSide.WHITE),
                Piece(PieceTypeId("pawn"), PieceSide.WHITE),
                Piece(PieceTypeId("pawn"), PieceSide.WHITE),
            ]
        }
    )
    b.hands = HandsState(
        {
            PieceSide.WHITE: [
                Piece(PieceTypeId("pawn"), PieceSide.WHITE),
                Piece(PieceTypeId("pawn"), PieceSide.WHITE),
                Piece(PieceTypeId("gold"), PieceSide.WHITE),
            ]
        }
    )
    assert position_key(a) == position_key(b)


def test_classic_knight_shuffle_is_draw_on_third_startpos() -> None:
    game = LocalGameService(classic_chess())
    cycle = ("g1f3", "g8f6", "f3g1", "f6g8")
    for token in cycle:
        game.play(parse_move(token))
    assert game.status() is GameStatus.ACTIVE
    assert repetition_count(game.state) == 2
    for token in cycle:
        game.play(parse_move(token))
    assert game.status() is GameStatus.REPETITION_DRAW
    assert is_threefold(game.state)
    result, comment = transcript_result(game.mode, game.state, game.status())
    assert result == "1/2-1/2"
    assert "троекратное" in comment


def test_lost_castling_rights_prevent_a_false_repetition() -> None:
    mode = classic_chess()
    start = parse_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", mode)
    returned = parse_fen("r3k2r/8/8/8/8/8/8/R3K2R w - - 0 1", mode)
    assert position_key(start) != position_key(returned)
    game = LocalGameService(mode, start)
    game.play(MoveAction(Square(4, 0), Square(4, 1)))
    game.play(MoveAction(Square(4, 7), Square(4, 6)))
    game.play(MoveAction(Square(4, 1), Square(4, 0)))
    game.play(MoveAction(Square(4, 6), Square(4, 7)))
    assert position_key(game.state) != position_key(start)
    assert game.status() is GameStatus.ACTIVE


def test_shogi_gold_wiggle_draws_on_threefold() -> None:
    game = LocalGameService(shogi())
    cycle = (
        MoveAction(Square(3, 0), Square(3, 1)),
        MoveAction(Square(3, 8), Square(3, 7)),
        MoveAction(Square(3, 1), Square(3, 0)),
        MoveAction(Square(3, 7), Square(3, 8)),
    )
    for move in cycle:
        game.play(move)
    assert game.status() is GameStatus.ACTIVE
    for move in cycle:
        game.play(move)
    assert game.status() is GameStatus.REPETITION_DRAW
    assert game.state.hands is not None
    for side in (PieceSide.WHITE, PieceSide.BLACK):
        assert game.state.hands.count(side, "gold") == 0


def test_shogi_same_board_with_pawn_in_hand_is_not_the_same_position() -> None:
    game = LocalGameService(shogi())
    after_cycle = game.state.clone()
    after_cycle.hands = HandsState(
        {PieceSide.WHITE: [Piece(PieceTypeId("pawn"), PieceSide.WHITE)]}
    )
    seed_repetition_log(after_cycle)
    assert position_key(game.state) != position_key(after_cycle)


def test_gobblet_hidden_stack_distinguishes_visible_tops() -> None:
    mode = gobblet()
    bare = mode.initial_state()
    covered = mode.initial_state()
    stack_at(bare, 4).append(Piece(GOBBLET_LARGE, PieceSide.WHITE))
    sync_cell(bare, 4)
    stack_at(covered, 4).append(Piece(GOBBLET_SMALL, PieceSide.BLACK))
    stack_at(covered, 4).append(Piece(GOBBLET_LARGE, PieceSide.WHITE))
    sync_cell(covered, 4)
    assert bare.board_state.piece_at(4) is not None
    assert covered.board_state.piece_at(4) is not None
    assert bare.board_state.piece_at(4).piece_type == covered.board_state.piece_at(4).piece_type
    assert position_key(bare) != position_key(covered)


def test_gobblet_moving_a_piece_back_and_forth_draws() -> None:
    game = LocalGameService(gobblet())
    setup = (
        Turn(PieceSide.WHITE, [DropAction(GOBBLET_LARGE, Square(1, 1))]),
        Turn(PieceSide.BLACK, [DropAction(GOBBLET_LARGE, Square(0, 0))]),
    )
    cycle = (
        Turn(PieceSide.WHITE, [MoveAction(Square(1, 1), Square(2, 2))]),
        Turn(PieceSide.BLACK, [MoveAction(Square(0, 0), Square(0, 2))]),
        Turn(PieceSide.WHITE, [MoveAction(Square(2, 2), Square(1, 1))]),
        Turn(PieceSide.BLACK, [MoveAction(Square(0, 2), Square(0, 0))]),
    )
    for turn in setup:
        game.play_turn(turn)
    base = position_key(game.state)
    assert game.status() is GameStatus.ACTIVE
    for turn in cycle:
        game.play_turn(turn)
    assert position_key(game.state) == base
    assert game.status() is GameStatus.ACTIVE
    for turn in cycle:
        game.play_turn(turn)
    assert position_key(game.state) == base
    assert game.status() is GameStatus.REPETITION_DRAW


def test_undo_after_threefold_restores_play() -> None:
    game = LocalGameService(classic_chess())
    cycle = ("g1f3", "g8f6", "f3g1", "f6g8")
    for token in (*cycle, *cycle):
        game.play(parse_move(token))
    assert game.status() is GameStatus.REPETITION_DRAW
    game.undo()
    assert game.status() is GameStatus.ACTIVE

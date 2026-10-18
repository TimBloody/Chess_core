"""Tests for LocalGameService undo and load."""

from datetime import datetime

from chess_core.app.game import GameStatus, LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import MoveAction
from chess_core.core.piece import PieceSide
from chess_core.modes.chess import classic_chess
from chess_core.tools.classical_demo import parse_move


def test_undo_restores_previous_position() -> None:
    game = LocalGameService(classic_chess())
    game.play(MoveAction(Square(4, 1), Square(4, 3)))
    assert game.state.side_to_move is PieceSide.BLACK
    game.undo()
    assert game.state.side_to_move is PieceSide.WHITE
    assert game.state.board_state.piece_at(12) is not None


def test_load_position_resets_history() -> None:
    game = LocalGameService(classic_chess())
    game.play(MoveAction(Square(4, 1), Square(4, 3)))
    loaded = classic_chess().initial_state()
    game.load_position(loaded)
    assert game.record.live_revision == 0
    assert game.can_undo() is False


def test_export_transcript_after_scholars_mate() -> None:
    game = LocalGameService(classic_chess())
    for value in ("e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"):
        game.play(parse_move(value))
    when = datetime(2026, 8, 31, 16, 40)
    text = game.export_transcript(exported_at=when)
    assert '[Mode "classic_chess"]' in text
    assert '[Result "1-0"]' in text
    assert "мат" in text
    assert game.transcript_filename(exported_at=when) == "classic_chess-20260831-1640.pgn"
    game.go_to_revision(2)
    replayed = game.export_transcript(exported_at=when)
    assert '[Result "1-0"]' in replayed
    assert '[PlyCount "7"]' in replayed


def test_status_after_mate_keeps_live_result_when_browsing() -> None:
    game = LocalGameService(classic_chess())
    for value in ("e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"):
        game.play(parse_move(value))
    assert game.status() is GameStatus.CHECKMATE
    assert game.state.side_to_move is PieceSide.BLACK

    game.go_to_revision(1)
    assert not game.is_live
    assert game.state.side_to_move is PieceSide.BLACK
    assert game.status() is not GameStatus.CHECKMATE
    assert game.live_status() is GameStatus.CHECKMATE

    game.go_to_revision(2)
    assert game.state.side_to_move is PieceSide.WHITE
    assert game.status() is not GameStatus.CHECKMATE
    assert game.live_status() is GameStatus.CHECKMATE

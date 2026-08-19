"""Tests for SFEN import/export."""

from chess_core.app.editor import BoardEditorService
from chess_core.core.sfen import parse_sfen, to_sfen
from chess_core.core.piece import PieceSide
from chess_core.modes.shogi import kyoto_shogi


def test_kyoto_sfen_round_trip() -> None:
    mode = kyoto_shogi()
    state = mode.initial_state()
    encoded = to_sfen(state)
    restored = parse_sfen(encoded, mode)
    assert restored.side_to_move is PieceSide.BLACK
    assert restored.board_state.piece_at(0).piece_type.name == "tokin"
    assert restored.board_state.piece_at(20).piece_type.name == "pawn"
    assert to_sfen(restored) == encoded


def test_sfen_hands_round_trip() -> None:
    mode = kyoto_shogi()
    encoded = "5/5/5/5/4K b 2P 1"
    state = parse_sfen(encoded, mode)
    assert state.hands is not None
    assert state.hands.count(PieceSide.WHITE, "pawn") == 2
    assert "P" in to_sfen(state)


def test_editor_imports_and_exports_sfen() -> None:
    editor = BoardEditorService(kyoto_shogi())
    editor.load_start_position()
    exported = editor.export_notation()
    editor.new_empty_position()
    editor.import_notation(exported)
    assert editor.state.board_state.piece_at(2).piece_type.name == "king"

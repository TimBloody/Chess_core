"""Tests for game record timeline."""

from datetime import datetime

from chess_core.app.game_record import GameRecord, transcript_filename
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, Turn
from chess_core.core.piece import PieceSide
from chess_core.modes.chess import classic_chess


def test_append_undo_and_go_to_revision() -> None:
    mode = classic_chess()
    record = GameRecord.from_mode(mode)
    e4 = Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))])
    record.append_turn(e4, notation="e4")
    assert record.live_revision == 1
    record.go_to(0)
    assert record.view_revision == 0
    assert record.current_view_state().board_state.piece_at(12) is not None
    record.go_live()
    assert record.is_live
    record.undo_last_turn()
    assert record.live_revision == 0
    assert record.turn_at(0) is None


def test_turn_at_returns_the_ply_that_produced_a_revision() -> None:
    mode = classic_chess()
    record = GameRecord.from_mode(mode)
    e4 = Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))])
    e5 = Turn(PieceSide.BLACK, [MoveAction(Square(4, 6), Square(4, 4))])
    record.append_turn(e4, notation="e4")
    record.append_turn(e5, notation="e5")
    assert record.turn_at(0) is None
    assert record.turn_at(1) == e4
    assert record.turn_at(2) == e5
    record.go_to(1)
    assert record.turn_at(record.view_revision) == e4


def test_move_log_lines_use_ply_revisions_not_row_numbers() -> None:
    mode = classic_chess()
    record = GameRecord.from_mode(mode)
    record.append_turn(
        Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]),
        notation="e4",
    )
    record.append_turn(
        Turn(PieceSide.BLACK, [MoveAction(Square(4, 6), Square(4, 4))]),
        notation="e5",
    )
    record.append_turn(
        Turn(PieceSide.WHITE, [MoveAction(Square(6, 0), Square(5, 2))]),
        notation="Nf3",
    )
    record.append_turn(
        Turn(PieceSide.BLACK, [MoveAction(Square(1, 7), Square(2, 5))]),
        notation="Nc6",
    )
    lines = record.move_log_lines()
    assert len(lines) == 2
    assert lines[0].number == 1
    assert lines[0].white_revision == 1
    assert lines[0].black_revision == 2
    assert lines[0].end_revision == 2
    assert lines[1].white_revision == 3
    assert lines[1].black_revision == 4
    assert lines[1].end_revision == 4
    assert record.move_log() == ["1. e4  e5", "2. Nf3  Nc6"]
    record.go_to(4)
    assert record.current_view_state().board_state.piece_at(21) is not None
    record.go_to(2)
    assert record.current_view_state().board_state.piece_at(21) is None


def test_viewing_history_blocks_live_append() -> None:
    mode = classic_chess()
    record = GameRecord.from_mode(mode)
    record.append_turn(
        Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]),
        notation="e4",
    )
    record.go_to(0)
    try:
        record.append_turn(
            Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]),
            notation="e4",
        )
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def test_format_transcript_is_mode_agnostic_plain_text() -> None:
    record = GameRecord.from_mode(classic_chess())
    record.append_turn(
        Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]),
        notation="e4",
    )
    record.append_turn(
        Turn(PieceSide.BLACK, [MoveAction(Square(4, 6), Square(4, 4))]),
        notation="e5",
    )
    when = datetime(2026, 8, 31, 16, 40)
    text = record.format_transcript(result="*", comment="партия не окончена", exported_at=when)
    assert '[Mode "classic_chess"]' in text
    assert '[Date "2026.08.31"]' in text
    assert '[Round "-"]' in text
    assert "1. e4 e5" in text.replace("  ", " ")
    assert "{партия не окончена}" in text
    assert text.strip().endswith("*")
    assert transcript_filename("gobblet", when) == "gobblet-20260831-1640.pgn"


def test_append_snapshot_keeps_view_and_truncate_restores_position() -> None:
    mode = classic_chess()
    record = GameRecord.from_mode(mode)
    start = record.live_state()
    after_e4 = start.apply_turn(
        Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]),
        record_history=False,
    )
    record.append_snapshot(after_e4, notation="e4")
    assert record.live_revision == 1
    record.go_to(0)
    record.append_snapshot(
        after_e4.apply_turn(
            Turn(PieceSide.BLACK, [MoveAction(Square(4, 6), Square(4, 4))]),
            record_history=False,
        ),
        keep_view=True,
    )
    assert record.view_revision == 0
    assert record.live_revision == 2
    record.truncate_to(1)
    assert record.live_revision == 1
    assert record.view_revision == 0


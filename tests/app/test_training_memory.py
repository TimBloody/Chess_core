from random import Random

import pytest

from chess_core.app.editor import BoardEditorService
from chess_core.app.training.memory import (
    PositionMemoryService,
    SequenceMemoryService,
    ShapeMemoryService,
)
from chess_core.core.piece import PieceSide
from chess_core.modes.chess import classic_chess
from chess_core.modes.shogi import dobutsu_shogi


def test_shape_memory_grades_exact_figure() -> None:
    service = ShapeMemoryService()
    prompt = service.generate(size=4, cell_count=5, reveal_ms=1200, rng=Random(3))

    assert prompt.size == 4
    assert len(prompt.cells) == 5
    assert service.is_perfect(prompt, set(prompt.cells))
    assert service.grade(prompt, set(prompt.cells)) == pytest.approx(1.0)
    assert service.grade(prompt, set()) == pytest.approx(0.0)


def test_sequence_memory_scores_prefix_and_rejects_out_of_bounds() -> None:
    service = SequenceMemoryService()
    prompt = service.generate(size=3, length=4, step_ms=400, rng=Random(7))

    assert prompt.sequence
    assert service.is_perfect(prompt, list(prompt.sequence))
    assert service.grade(prompt, list(prompt.sequence[:2])) == pytest.approx(0.5)
    with pytest.raises(ValueError, match="outside"):
        service.grade(prompt, [99])


def test_position_memory_places_both_kings_and_reuses_editor_grader() -> None:
    mode = classic_chess()
    service = PositionMemoryService()
    target = service.generate(mode, piece_count=6, reveal_seconds=2.0, rng=Random(11))
    occupied = [piece for piece in target.board_state.cells.values() if piece is not None]
    sides = {piece.side for piece in occupied if mode.piece_is_royal(piece)}

    assert len(occupied) == 6
    assert sides == {PieceSide.WHITE, PieceSide.BLACK}
    assert service.grade(target, target) == pytest.approx(1.0)

    editor = BoardEditorService(mode)
    editor.new_empty_position()
    assert service.grade(target, editor.state) < 1.0


def test_position_memory_compare_marks_extra_mismatch_and_missed() -> None:
    mode = classic_chess()
    service = PositionMemoryService()
    target = service.generate(mode, piece_count=4, reveal_seconds=1.0, rng=Random(5))
    occupied = [
        index
        for index, piece in target.board_state.cells.items()
        if piece is not None
    ]
    empty = [
        index
        for index in range(target.board_state.board.shape.cell_count)
        if target.board_state.cells.get(index) is None
    ]
    source = occupied[0]
    piece = target.board_state.cells[source]
    assert piece is not None

    editor = BoardEditorService(mode)
    editor.new_empty_position()
    editor.set_piece(empty[0], "pawn", "white")
    wrong_type = "bishop" if piece.piece_type.name != "bishop" else "knight"
    editor.set_piece(source, wrong_type, piece.side.name.lower())
    diff = service.compare(target, editor.state)

    assert empty[0] in diff.extra
    assert source in diff.mismatch
    assert occupied[1] in diff.missed
    assert source not in diff.missed
    assert empty[0] not in diff.missed


def test_position_memory_works_on_dobutsu_board() -> None:
    mode = dobutsu_shogi()
    target = PositionMemoryService().generate(mode, piece_count=4, rng=Random(2))
    occupied = sum(piece is not None for piece in target.board_state.cells.values())
    assert occupied == 4
    assert target.board_state.board.shape.files == 3

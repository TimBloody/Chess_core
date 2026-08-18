import pytest

from chess_core.app.editor import BoardEditorService
from chess_core.app.memory import MemoryTrainingService
from chess_core.app.puzzles import PuzzleService
from chess_core.core.board import Board, BoardShape, Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import MoveAction
from chess_core.core.piece import Piece, PieceCatalog, PieceSide, PieceTypeId
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.state import BoardState, GameState
from chess_core.core.topology import FlatTopology
from chess_core.core.turn import AlternatingSides, StepKind, TurnScenario, TurnStep


def _mode(files: int = 2, ranks: int = 2) -> GameMode:
    shape = BoardShape(files=files, ranks=ranks)
    return GameMode(
        id="test",
        name="Test Mode",
        board=Board(shape),
        topology=FlatTopology(shape),
        pieces=PieceCatalog(),
        turn_scenario=TurnScenario((TurnStep(StepKind.MOVE_OR_CAPTURE),)),
        turn_order=AlternatingSides(("white", "black")),
        victory=VictoryCondition(VictoryKind.KING_CAPTURE),
    )


def _state_with_cells(cells: dict[int, Piece | None]) -> GameState:
    mode = _mode()
    return GameState(
        board_state=BoardState(board=mode.board, cells=cells),
        side_to_move=PieceSide.WHITE,
    )


def test_editor_creates_empty_position_and_edits_by_square_index() -> None:
    editor = BoardEditorService(_mode())
    state = editor.new_empty_position()

    assert state.side_to_move == PieceSide.WHITE
    assert state.board_state.cells == {0: None, 1: None, 2: None, 3: None}

    editor.set_piece(1, "king", "white")

    piece = state.board_state.cells[1]
    assert piece == Piece(PieceTypeId("king"), PieceSide.WHITE)

    editor.remove_piece(1)

    assert state.board_state.cells[1] is None


def test_editor_rejects_out_of_bounds_square_index() -> None:
    editor = BoardEditorService(_mode())
    editor.new_empty_position()

    with pytest.raises(ValueError):
        editor.set_piece(4, "king", "white")


def test_editor_validate_for_mode_uses_king_helper_and_callback() -> None:
    editor = BoardEditorService(_mode(files=4, ranks=2), require_one_king_per_side=True)
    editor.new_empty_position()
    editor.set_piece(0, "king", "white")
    editor.set_piece(7, "king", "black")

    errors = editor.validate_for_mode(lambda state: ["custom error"])

    assert errors == ["custom error"]

    editor.remove_piece(7)

    assert editor.validate_for_mode() == ["expected exactly one black king, found 0"]


def test_memory_training_grades_piece_type_and_side_by_index() -> None:
    target = _state_with_cells(
        {
            0: Piece(PieceTypeId("king"), PieceSide.WHITE),
            1: None,
            2: Piece(PieceTypeId("rook"), PieceSide.BLACK),
            3: None,
        }
    )
    attempt = _state_with_cells(
        {
            0: Piece(PieceTypeId("king"), PieceSide.WHITE),
            1: None,
            2: Piece(PieceTypeId("rook"), PieceSide.WHITE),
            3: None,
        }
    )
    service = MemoryTrainingService()

    round_ = service.start_round(target, reveal_seconds=2.5)

    assert round_.target_state is target
    assert round_.reveal_seconds == 2.5
    assert service.grade_reconstruction(target, attempt) == pytest.approx(0.75)


def test_puzzle_service_loads_fen_and_uses_solution_move_list() -> None:
    service = PuzzleService(_mode(files=8, ranks=8))
    solution = [MoveAction(Square(0, 0), Square(1, 0))]
    state = _state_with_cells({})
    state.extras["solution"] = solution

    loaded = service.load_from_fen("8/8/8/8/8/8/8/8 w - - 0 1")
    assert loaded.side_to_move is PieceSide.WHITE
    assert all(piece is None for piece in loaded.board_state.cells.values())

    assert service.is_solution(state, solution)
    assert not service.is_solution(state, [])
    assert service.solve(state, max_depth=1) == solution
    assert service.solve(state, max_depth=0) is None

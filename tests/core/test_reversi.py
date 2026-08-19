"""Tests for Reversi / Othello mode."""

from chess_core.app.game import LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import PassAction, PlaceAction, Turn
from chess_core.core.outcome import OutcomeStatus
from chess_core.core.piece import Piece, PieceSide
from chess_core.modes.reversi import reversi
from chess_core.modes.reversi_rules import DISC, flips_for_placement, legal_placements


def _sq(name: str) -> Square:
    return Square(ord(name[0]) - ord("a"), int(name[1]) - 1)


def test_mode_metadata_and_starting_position() -> None:
    mode = reversi()
    assert mode.id == "reversi"
    assert mode.name == "Реверси"

    state = mode.initial_state()
    assert state.side_to_move is PieceSide.BLACK
    assert state.board_state.piece_at(27).side is PieceSide.WHITE  # d4
    assert state.board_state.piece_at(28).side is PieceSide.BLACK  # e4
    assert state.board_state.piece_at(35).side is PieceSide.BLACK  # d5
    assert state.board_state.piece_at(36).side is PieceSide.WHITE  # e5


def test_four_opening_placements_for_black() -> None:
    mode = reversi()
    state = mode.initial_state()
    targets = {
        (action.to_square.file, action.to_square.rank)
        for turn in mode.legal_turns(state)
        for action in turn.actions
        if isinstance(action, PlaceAction)
    }
    assert targets == {
        (_sq("c4").file, _sq("c4").rank),
        (_sq("d3").file, _sq("d3").rank),
        (_sq("e6").file, _sq("e6").rank),
        (_sq("f5").file, _sq("f5").rank),
    }


def test_c4_flips_d4() -> None:
    mode = reversi()
    state = mode.initial_state()
    turn = Turn(PieceSide.BLACK, [PlaceAction(DISC, _sq("c4"))])
    after = mode.apply_turn(state, turn, record_history=False)

    assert after.board_state.piece_at(_sq("c4").index(8)).side is PieceSide.BLACK
    assert after.board_state.piece_at(_sq("d4").index(8)).side is PieceSide.BLACK
    assert after.board_state.piece_at(_sq("e4").index(8)).side is PieceSide.BLACK


def test_multi_axis_flip() -> None:
    mode = reversi()
    state = mode.initial_state()
    files = mode.board.shape.files
    for index in range(mode.board.shape.cell_count):
        state.board_state.cells[index] = None
    placements = {
        _sq("b4"): PieceSide.WHITE,
        _sq("c4"): PieceSide.BLACK,
        _sq("e4"): PieceSide.BLACK,
        _sq("f4"): PieceSide.WHITE,
        _sq("d2"): PieceSide.WHITE,
        _sq("d3"): PieceSide.BLACK,
        _sq("d5"): PieceSide.BLACK,
        _sq("d6"): PieceSide.WHITE,
    }
    for name, side in placements.items():
        state.board_state.cells[name.index(files)] = Piece(DISC, side)
    state.side_to_move = PieceSide.WHITE

    flips = flips_for_placement(state, _sq("d4"), PieceSide.WHITE)
    assert _sq("c4").index(files) in flips
    assert _sq("e4").index(files) in flips
    assert _sq("d3").index(files) in flips
    assert _sq("d5").index(files) in flips
    assert len(flips) == 4

    turn = Turn(PieceSide.WHITE, [PlaceAction(DISC, _sq("d4"))])
    after = mode.apply_turn(state, turn, record_history=False)
    assert after.board_state.piece_at(_sq("d3").index(files)).side is PieceSide.WHITE
    assert after.board_state.piece_at(_sq("d4").index(files)).side is PieceSide.WHITE
    assert after.board_state.piece_at(_sq("d5").index(files)).side is PieceSide.WHITE


def test_illegal_placement_rejected() -> None:
    mode = reversi()
    state = mode.initial_state()
    occupied = Turn(PieceSide.BLACK, [PlaceAction(DISC, _sq("d4"))])
    assert occupied not in mode.legal_turns(state)

    isolated = Turn(PieceSide.BLACK, [PlaceAction(DISC, _sq("a1"))])
    assert isolated not in mode.legal_turns(state)

    try:
        mode.apply_turn(state, isolated, record_history=False)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_pass_when_only_opponent_can_move() -> None:
    mode = reversi()
    state = mode.initial_state()
    files = mode.board.shape.files
    for index in range(mode.board.shape.cell_count):
        state.board_state.cells[index] = None
    state.board_state.cells[_sq("a1").index(files)] = Piece(DISC, PieceSide.BLACK)
    state.board_state.cells[_sq("b1").index(files)] = Piece(DISC, PieceSide.WHITE)
    state.board_state.cells[_sq("c1").index(files)] = Piece(DISC, PieceSide.BLACK)
    state.side_to_move = PieceSide.BLACK

    assert legal_placements(state, PieceSide.BLACK) == []
    assert legal_placements(state, PieceSide.WHITE)

    turns = mode.legal_turns(state)
    assert len(turns) == 1
    assert isinstance(turns[0].actions[0], PassAction)

    after = mode.apply_turn(state, turns[0], record_history=False)
    assert after.side_to_move is PieceSide.WHITE
    assert mode.outcome(after).status is OutcomeStatus.ACTIVE


def test_endgame_by_disc_count_and_draw() -> None:
    mode = reversi()
    files = mode.board.shape.files

    win_state = mode.initial_state()
    for index in range(mode.board.shape.cell_count):
        win_state.board_state.cells[index] = Piece(
            DISC, PieceSide.WHITE if index < 33 else PieceSide.BLACK
        )
    win_state.side_to_move = PieceSide.BLACK

    win_outcome = mode.outcome(win_state)
    assert win_outcome.status is OutcomeStatus.WIN
    assert win_outcome.winner is PieceSide.WHITE
    assert win_outcome.score == (33, 31)
    assert win_outcome.reason == "disc_count"
    assert mode.legal_turns(win_state) == []

    draw_state = mode.initial_state()
    for index in range(mode.board.shape.cell_count):
        draw_state.board_state.cells[index] = Piece(
            DISC, PieceSide.WHITE if index % 2 == 0 else PieceSide.BLACK
        )
    draw_state.side_to_move = PieceSide.WHITE

    draw_outcome = mode.outcome(draw_state)
    assert draw_outcome.status is OutcomeStatus.DRAW
    assert draw_outcome.score == (32, 32)
    assert draw_outcome.reason == "disc_count"


def test_local_game_service_play_turn() -> None:
    game = LocalGameService(reversi())
    assert game.state.side_to_move is PieceSide.BLACK

    turn = next(
        candidate
        for candidate in game.legal_turns()
        if candidate.actions
        and isinstance(candidate.actions[0], PlaceAction)
        and candidate.actions[0].to_square == _sq("c4")
    )
    game.play_turn(turn)
    assert game.state.side_to_move is PieceSide.WHITE
    assert game.state.board_state.piece_at(_sq("d4").index(8)).side is PieceSide.BLACK
    assert game.can_undo()

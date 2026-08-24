from pathlib import Path

import pytest

from chess_core.app.editor import BoardEditorService
from chess_core.app.game import LocalGameService
from chess_core.app.memory import MemoryTrainingService
from chess_core.core.board import Board, BoardShape, Square
from chess_core.core.masks import MaskTableLoader
from chess_core.core.move import MoveAction, Turn
from chess_core.core.piece import PieceSide
from chess_core.core.topology import FlatTopology, PortalLink, PortalTopology
from chess_core.infra.network import GameClient, GameServer, StateMessage, TurnMessage
from chess_core.infra.network_messages import LobbyState, MatchEnvelope, StateEnvelope
from chess_core.modes.chess import classic_chess
from chess_core.tools.mask_builder import MaskBuilder


def test_editor_fen_round_trip_and_puzzle_ready_position() -> None:
    editor = BoardEditorService(classic_chess())
    state = editor.import_notation(
        "r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 3 17"
    )
    assert state.board_state.piece_at(60).piece_type.name == "king"
    assert editor.export_notation() == "r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 3 17"


def test_memory_rejects_different_board_shapes() -> None:
    target = classic_chess().initial_state()
    other = target.clone()
    other.board_state.board = Board(BoardShape(5, 5))
    with pytest.raises(ValueError, match="shapes"):
        MemoryTrainingService().grade_reconstruction(target, other)


def test_state_clone_shares_mode_but_isolates_position_owned_piece_state() -> None:
    state = classic_chess().initial_state()
    state.board_state.piece_at(0).state = {"flags": ["original"]}
    cloned = state.clone()

    assert cloned.extras["mode"] is state.extras["mode"]
    cloned.board_state.piece_at(0).state["flags"].append("clone")
    assert state.board_state.piece_at(0).state == {"flags": ["original"]}


def test_mask_builder_output_loads_back_with_same_ray(tmp_path: Path) -> None:
    builder = MaskBuilder(tmp_path)
    path = builder.build_mode("flat_8x8")
    table = MaskTableLoader().load(path)
    assert table.ray_mask(0, (1, 0)) == sum(1 << index for index in range(1, 8))


def test_portal_neighbors_include_link_and_validate_target() -> None:
    shape = BoardShape(3, 3)
    portal = PortalTopology(
        shape, (PortalLink(Square(2, 2), Square(0, 0)),)
    )
    assert portal.neighbors(Square(2, 2)).value & 1
    with pytest.raises(ValueError):
        PortalTopology(shape, (PortalLink(Square(2, 2), Square(3, 0)),))


def test_two_client_server_assigns_sides_and_broadcasts_state() -> None:
    mode = classic_chess()
    server = GameServer(mode.initial_state())
    server.host(8765)
    white = GameClient()
    black = GameClient()
    white_session = white.connect(server)
    black_session = black.connect(server)

    assert white_session.side is PieceSide.WHITE
    assert black_session.side is PieceSide.BLACK
    assert any(isinstance(item, (StateMessage, StateEnvelope, MatchEnvelope, LobbyState)) for item in white_session.inbox)
    assert TurnMessage("id", Turn(PieceSide.WHITE, [])).session_id == "id"
    spectator = GameClient().connect(server)
    assert spectator.seat == "spectator"

    white.submit_turn(
        Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))])
    )
    assert server.state.side_to_move is PieceSide.BLACK
    assert server.state.board_state.piece_at(28) is not None
    with pytest.raises(PermissionError):
        white.submit_turn(
            Turn(PieceSide.BLACK, [MoveAction(Square(4, 6), Square(4, 4))])
        )


def test_local_game_service_plays_only_legal_moves() -> None:
    game = LocalGameService(classic_chess())
    game.play(MoveAction(Square(4, 1), Square(4, 3)))
    assert game.state.side_to_move is PieceSide.BLACK
    with pytest.raises(ValueError, match="legal"):
        game.play(MoveAction(Square(0, 0), Square(0, 3)))


def test_local_selection_generates_one_piece_and_reuses_cached_moves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = LocalGameService(classic_chess())
    game.status()  # populate the independent position-status cache
    calls = {"all": 0, "selected": 0}
    original_all = game._generator.generate_legal
    original_selected = game._generator.generate_legal_for_square

    def count_all(state):
        calls["all"] += 1
        return original_all(state)

    def count_selected(state, square):
        calls["selected"] += 1
        return original_selected(state, square)

    monkeypatch.setattr(game._generator, "generate_legal", count_all)
    monkeypatch.setattr(
        game._generator, "generate_legal_for_square", count_selected
    )

    selected = game.legal_moves_for_square(12)
    e2e4 = MoveAction(Square(4, 1), Square(4, 3))
    assert e2e4 in selected
    knight_moves = game.legal_moves_for_square(1)
    assert knight_moves
    assert all(move.from_square == Square(1, 0) for move in knight_moves)
    assert e2e4 not in game.selected_moves
    game.legal_moves_for_square(12)
    game.play_selected(e2e4)

    assert calls == {"all": 0, "selected": 3}
    assert game.selected_moves == ()
    with pytest.raises(ValueError, match="current selection"):
        game.play_selected(e2e4)
    game.legal_moves_for_square(48)
    game.reset()
    assert game.selected_moves == ()

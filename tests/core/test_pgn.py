"""Tests for PGN import/export."""

import pytest

from chess_core.app.game import LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, PlaceBlockerAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import parse_fen
from chess_core.core.piece import PieceSide
from chess_core.core.pgn import export_pgn, parse_pgn, resolve_turn
from chess_core.modes.chess import classic_chess
from chess_core.modes.shogi import shogi


def test_pgn_round_trip_classic_game() -> None:
    game = LocalGameService(classic_chess())
    game.play(MoveAction(Square(4, 1), Square(4, 3)))
    game.play(MoveAction(Square(4, 6), Square(4, 4)))
    text = game.export_pgn(headers={"White": "A", "Black": "B"})
    parsed = parse_pgn(text)
    assert parsed.headers["White"] == "A"
    assert parsed.moves[0] in {"e4", "e2-e4"}
    restored = LocalGameService(classic_chess())
    restored.import_pgn(text)
    assert restored.record.live_revision == 2
    assert restored.state.board_state.piece_at(28) is not None
    assert restored.state.board_state.piece_at(36) is not None


def test_pgn_parses_coordinate_and_san_tokens() -> None:
    mode = classic_chess()
    state = mode.initial_state()
    turn = resolve_turn(state, "e2e4")
    assert isinstance(turn.actions[0], MoveAction)
    assert turn.actions[0].to_square == Square(4, 3)


def test_pgn_exports_composite_duck_turn() -> None:
    mode = classic_chess()
    state = mode.initial_state()
    turn = Turn(
        PieceSide.WHITE,
        [
            MoveAction(Square(4, 1), Square(4, 3)),
            PlaceBlockerAction(Square(0, 3)),
        ],
    )
    text = export_pgn(
        mode=mode,
        initial=state,
        notations=["e2-e4·@a4"],
    )
    parsed = parse_pgn(text)
    assert parsed.moves == ("e2-e4·@a4",)
    resolved = resolve_turn(state, parsed.moves[0])
    assert isinstance(resolved.actions[1], PlaceBlockerAction)


def test_pgn_uses_seven_tag_order_and_escapes_metadata() -> None:
    mode = classic_chess()
    text = export_pgn(
        mode=mode,
        initial=mode.initial_state(),
        notations=[],
        headers={"Event": 'Coach "A" \\ notes', "Annotator": "Trainer"},
    )
    lines = text.splitlines()
    assert [line.split()[0] for line in lines[:7]] == [
        "[Event",
        "[Site",
        "[Date",
        "[Round",
        "[White",
        "[Black",
        "[Result",
    ]
    assert parse_pgn(text).headers["Event"] == 'Coach "A" \\ notes'


def test_pgn_numbers_first_move_for_black_from_setup_position() -> None:
    mode = classic_chess()
    initial = mode.initial_state()
    initial.side_to_move = PieceSide.BLACK
    text = export_pgn(
        mode=mode,
        initial=initial,
        notations=["e5", "Nf3"],
    )
    assert "1... e5 2. Nf3 *" in text


def test_pgn_import_resolves_castling_san() -> None:
    game = LocalGameService(classic_chess())
    game.import_pgn(
        """
[Event "Castling"]
[Result "*"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. O-O *
"""
    )
    assert game.state.board_state.piece_at(6).piece_type.name == "king"
    assert game.state.board_state.piece_at(5).piece_type.name == "rook"


def test_shogi_pgn_uses_sfen_for_custom_start_position() -> None:
    mode = shogi()
    initial = mode.initial_state()
    initial.board_state.cells[0] = None
    text = export_pgn(mode=mode, initial=initial, notations=[])
    assert '[SFEN "' in text

    restored = LocalGameService(mode)
    restored.import_pgn(text)
    assert restored.state.board_state.piece_at(0) is None
    assert restored.state.side_to_move is PieceSide.BLACK


@pytest.mark.parametrize("token", ("Nbd7", "N8d7", "Nb8d7", "Nb8-d7"))
def test_pgn_parser_accepts_disambiguated_and_long_notation(token: str) -> None:
    mode = classic_chess()
    state = parse_fen(
        "1n2k3/8/5n2/8/8/8/8/4K3 b - - 0 1",
        mode,
    )
    turn = resolve_turn(state, token, MoveGenerator(mode))
    assert turn.actions[0].from_square == Square(1, 7)
    assert turn.actions[0].to_square == Square(3, 6)


def test_pgn_parser_rejects_truly_ambiguous_short_move() -> None:
    mode = classic_chess()
    state = parse_fen(
        "1n2k3/8/5n2/8/8/8/8/4K3 b - - 0 1",
        mode,
    )
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_turn(state, "Nd7", MoveGenerator(mode))


def test_pgn_parser_accepts_optional_capture_and_en_passant_suffix() -> None:
    mode = classic_chess()
    state = parse_fen(
        "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1",
        mode,
    )
    generator = MoveGenerator(mode)
    for token in ("exd6", "ed6", "e5d6", "exd6e.p."):
        turn = resolve_turn(state, token, generator)
        assert turn.actions[0] == MoveAction(Square(4, 4), Square(3, 5))

    parsed = parse_pgn("1. exd6 e.p. *")
    assert parsed.moves == ("exd6",)


@pytest.mark.parametrize("token", ("e8=Q+", "e8Q", "e8(Q)", "e8/Q", "e7e8q"))
def test_pgn_parser_accepts_promotion_spellings(token: str) -> None:
    mode = classic_chess()
    state = parse_fen("7k/4P3/8/8/8/8/8/4K3 w - - 0 1", mode)
    turn = resolve_turn(state, token, MoveGenerator(mode))
    action = turn.actions[0]
    assert isinstance(action, MoveAction)
    assert action.promotion_choice is not None
    assert action.promotion_choice.name == "queen"


def test_parenthesized_promotion_is_not_mistaken_for_a_rav() -> None:
    assert parse_pgn("1. e8(Q) *").moves == ("e8=Q",)


def test_pgn_parser_handles_attached_numbers_comments_and_variations() -> None:
    parsed = parse_pgn(
        """
[Result "*"]

1.e4 {main line} e5 2.Nf3 (2.Bc4 Nc6 (2...Nf6)) Nc6
3.Bb5!? a6 $1 *
"""
    )
    assert parsed.moves == ("e4", "e5", "Nf3", "Nc6", "Bb5", "a6")


@pytest.mark.parametrize("token", ("O-O", "0-0", "o-o+", "O-O++"))
def test_pgn_parser_accepts_castling_spellings(token: str) -> None:
    mode = classic_chess()
    state = parse_fen("4k3/8/8/8/8/8/8/4K2R w K - 0 1", mode)
    turn = resolve_turn(state, token, MoveGenerator(mode))
    assert turn.actions[0] == MoveAction(Square(4, 0), Square(6, 0))


@pytest.mark.parametrize("token", ("Bxf7+", "Bf7", "Bc4xf7", "Bc4:f7"))
def test_pgn_parser_accepts_capture_variants(token: str) -> None:
    mode = classic_chess()
    state = parse_fen("4k3/5p2/8/8/2B5/8/8/4K3 w - - 0 1", mode)
    turn = resolve_turn(state, token, MoveGenerator(mode))
    assert turn.actions[0] == MoveAction(Square(2, 3), Square(5, 6))

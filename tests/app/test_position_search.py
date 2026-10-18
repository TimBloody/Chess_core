"""Position index finds a board position even after a move-order transposition."""

from chess_core.app.game import LocalGameService
from chess_core.app.pgn_replay import resolve_turn
from chess_core.app.position_search import build_position_index
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import to_fen
from chess_core.core.pgn import parse_pgn
from chess_core.core.repetition import position_key
from chess_core.modes import resolve_mode

_DATABASE = """[Event "A"]
[White "Alpha"]
[Black "Beta"]
[Result "*"]

1. Nf3 Nf6 2. d4 d5 3. c4 *

[Event "B"]
[White "Gamma"]
[Black "Delta"]
[Result "*"]

1. d4 d5 2. Nf3 Nf6 3. e3 *

[Event "C"]
[White "Epsilon"]
[Black "Zeta"]
[Result "*"]

1. e4 e5 *

[Event "Broken"]
[White "Oops"]
[Black "Oops"]
[Result "*"]

1. Nf3 Nf3 *
"""

_VARIATION = """[Event "Sideline"]
[White "V"]
[Black "V"]
[Result "*"]

1. e4 e5 (1... c5) 2. Nf3 *

[Event "Main"]
[White "M"]
[Black "M"]
[Result "*"]

1. e4 c5 *
"""

_UPGRADE = """[Event "Both"]
[White "U"]
[Black "U"]
[Result "*"]

1. Nf3 Nf6 (1... Nf6 2. d4) 2. d4 *
"""


def _play(sans: tuple[str, ...]):
    mode = resolve_mode("chess")
    service = LocalGameService(mode)
    generator = MoveGenerator(mode)
    for san in sans:
        service.play_turn(resolve_turn(service.state, san, generator))
    return service


def test_transposition_matches_despite_different_clocks() -> None:
    via_knight = _play(("Nf3", "Nf6", "d4", "d5"))
    via_pawn = _play(("d4", "d5", "Nf3", "Nf6"))
    assert position_key(via_knight.state) == position_key(via_pawn.state)
    assert to_fen(via_knight.state) != to_fen(via_pawn.state)

    index = build_position_index(parse_pgn(_DATABASE), resolve_mode("chess"))
    first = index.find(via_knight.state)
    assert first is index.find(via_pawn.state)
    assert [hit.game_index for hit in first] == [0, 1]
    assert all(hit.on_mainline and hit.ply == 4 for hit in first)
    assert index.find(_play(("e4", "e5")).state)[0].game_index == 2


def test_start_position_lists_every_game_including_a_broken_one() -> None:
    mode = resolve_mode("chess")
    index = build_position_index(parse_pgn(_DATABASE), mode)
    hits = index.find(mode.initial_state())
    assert [hit.game_index for hit in hits] == [0, 1, 2, 3]
    assert all(hit.ply == 0 and hit.on_mainline for hit in hits)
    after_nf3 = index.find(_play(("Nf3",)).state)
    assert [hit.game_index for hit in after_nf3] == [0, 3]


def test_variation_is_found_and_later_mainline_wins_the_ply() -> None:
    mode = resolve_mode("chess")
    index = build_position_index(parse_pgn(_VARIATION), mode)
    sicilian = index.find(_play(("e4", "c5")).state)
    assert [(hit.game_index, hit.ply, hit.on_mainline) for hit in sicilian] == [
        (0, 1, False),
        (1, 2, True),
    ]

    upgraded = build_position_index(parse_pgn(_UPGRADE), mode)
    reached = _play(("Nf3", "Nf6", "d4"))
    hits = upgraded.find(reached.state)
    assert len(hits) == 1
    assert hits[0].on_mainline is True
    assert hits[0].ply == 3


def test_fen_start_is_the_position_at_ply_zero() -> None:
    reached = _play(("Nf3", "Nf6", "d4", "d5"))
    fen = to_fen(reached.state)
    text = f"""[Event "Setup"]
[White "F"]
[Black "F"]
[Result "*"]
[SetUp "1"]
[FEN "{fen}"]

*
"""
    index = build_position_index(parse_pgn(text), resolve_mode("chess"))
    hits = index.find(reached.state)
    assert len(hits) == 1
    assert hits[0].ply == 0
    assert hits[0].on_mainline is True

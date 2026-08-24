"""Lichess puzzle parsing and interactive solving."""

from chess_core.app.puzzles import (
    PuzzleJudgement,
    PuzzleSession,
    legal_move_for_uci,
    parse_lichess_csv,
    parse_lichess_json,
    puzzle_line_is_legal,
)
from chess_core.core.board import Square
from chess_core.core.notation import parse_uci
from chess_core.core.piece import PieceSide
from chess_core.modes.chess import classic_chess

_CSV = """PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags
00008,r6k/pp2r2p/4Rp1Q/3p4/8/1N1P2R1/PqP2bPP/7K b - - 0 24,f2g3 e6e7 b2b1 b3c1 b1c1 h6c1,1760,80,83,72,crushing hangingPiece long middlegame,https://lichess.org/787zsVup/black#48,
00sHx,q3k1nr/1pp1nQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 b k - 0 17,e8d7 a2e6 d7d8 f7f8,1760,80,83,72,mate mateIn2 middlegame short,https://lichess.org/yyznGmXs/black#34,Italian_Game
"""

_API_JSON = """
{
  "puzzles": [
    {
      "id": "00008",
      "fen": "r6k/pp2r2p/4Rp1Q/3p4/8/1N1P2b1/PqP3PP/7K w - - 0 1",
      "lastMove": "f2g3",
      "solution": ["e6e7", "b2b1", "b3c1", "b1c1", "h6c1"],
      "rating": 1763,
      "themes": ["middlegame", "crushing", "long", "hangingPiece"],
      "gameId": "787zsVup"
    }
  ]
}
"""


def test_parse_official_lichess_csv() -> None:
    puzzles = parse_lichess_csv(_CSV)
    assert [puzzle.puzzle_id for puzzle in puzzles] == ["00008", "00sHx"]
    first = puzzles[0]
    assert first.fen.startswith("r6k/")
    assert first.last_move_uci == "f2g3"
    assert first.solution_uci[0] == "e6e7"
    assert "hangingPiece" in first.themes


def test_parse_lichess_api_json_uses_presented_fen() -> None:
    puzzles = parse_lichess_json(_API_JSON)
    assert len(puzzles) == 1
    puzzle = puzzles[0]
    assert puzzle.fen_is_before_last_move is False
    assert puzzle.last_move_uci == "f2g3"
    assert puzzle.solution_uci[0] == "e6e7"


def test_lichess_sample_lines_are_legal_in_classic_engine() -> None:
    mode = classic_chess()
    for puzzle in parse_lichess_csv(_CSV):
        assert puzzle_line_is_legal(mode, puzzle)


def test_bundled_mini_catalog_loads() -> None:
    from chess_core.infra.storage.lichess_puzzles import load_lichess_puzzles

    puzzles = load_lichess_puzzles()
    assert len(puzzles) >= 20
    mode = classic_chess()
    session = PuzzleSession(mode, puzzles[:3])
    assert session.solver_side in {PieceSide.WHITE, PieceSide.BLACK}
    assert session.expected_uci is not None


def test_session_applies_setup_move_and_accepts_solution() -> None:
    mode = classic_chess()
    puzzle = parse_lichess_csv(_CSV)[0]
    session = PuzzleSession(mode, [puzzle])
    assert session.solver_side is PieceSide.WHITE
    bishop = session.game.state.board_state.piece_at(Square(6, 2).index(8))
    assert bishop is not None
    assert bishop.piece_type.name == "bishop"

    first = legal_move_for_uci(mode, session.game.state, "e6e7")
    assert first is not None
    result = session.attempt(first)
    assert result.judgement is PuzzleJudgement.CORRECT
    assert session.solver_side is PieceSide.WHITE


def test_wrong_move_reveals_expected_then_next_puzzle() -> None:
    mode = classic_chess()
    puzzles = parse_lichess_csv(_CSV)
    session = PuzzleSession(mode, puzzles)
    wrong = legal_move_for_uci(mode, session.game.state, "h6h7")
    if wrong is None:
        wrong = next(
            move
            for move in session.game.legal_moves()
            if move.to_square != parse_uci("e6e7").to_square
        )
    result = session.attempt(wrong)
    assert result.judgement is PuzzleJudgement.WRONG
    assert result.expected is not None
    assert result.notation
    played = session.play_expected()
    assert played is not None
    session.next_puzzle()
    assert session.puzzle.puzzle_id == "00sHx"


def test_mate_in_one_accepts_any_checkmate() -> None:
    csv_text = (
        "PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags\n"
        "mate1,5k2/5ppp/8/8/8/8/8/R3R1K1 b - - 0 1,f8g8 a1a8,800,80,90,10,mate mateIn1,,"
    )
    mode = classic_chess()
    puzzle = parse_lichess_csv(csv_text)[0]
    assert puzzle_line_is_legal(mode, puzzle)
    session = PuzzleSession(mode, [puzzle])
    mates = [
        move
        for move in session.game.legal_moves()
        if _is_mate(mode, session.game.state, move)
    ]
    assert mates
    other_mate = next(
        move
        for move in mates
        if not (
            move.from_square.file == 0
            and move.from_square.rank == 0
            and move.to_square.file == 0
            and move.to_square.rank == 7
        )
    )
    result = session.attempt(other_mate)
    assert result.judgement is PuzzleJudgement.SOLVED


def test_previous_puzzle_and_hint_action() -> None:
    mode = classic_chess()
    puzzles = parse_lichess_csv(_CSV)
    session = PuzzleSession(mode, puzzles)
    session.next_puzzle()
    assert session.puzzle.puzzle_id == "00sHx"
    session.previous_puzzle()
    assert session.puzzle.puzzle_id == "00008"
    hint = session.hint_action()
    assert hint is not None
    ply, total = session.player_progress
    assert ply == 1
    assert total == 3


def _is_mate(mode, state, move) -> bool:
    from chess_core.app.puzzles import _gives_checkmate

    return _gives_checkmate(mode, state, move)

"""Puzzle solver application service, including Lichess FEN/UCI catalogs."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto

from chess_core.app.game import LocalGameService
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Action, MoveAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import (
    NotationStyle,
    format_turn,
    format_uci,
    parse_fen,
    parse_uci,
)
from chess_core.core.outcome import OutcomeStatus
from chess_core.core.piece import PieceSide
from chess_core.core.state import GameState

_LICHESS_CSV_FIELDS = (
    "PuzzleId",
    "FEN",
    "Moves",
    "Rating",
    "RatingDeviation",
    "Popularity",
    "NbPlays",
    "Themes",
    "GameUrl",
    "OpeningTags",
)


class PuzzleJudgement(Enum):
    ILLEGAL = auto()
    WRONG = auto()
    CORRECT = auto()
    SOLVED = auto()


@dataclass(frozen=True, slots=True)
class LichessPuzzle:
    """One Lichess puzzle in official dump semantics.

    ``fen`` is the position *before* the opponent's last move. ``moves_uci[0]``
    is that setup move; the rest is the solution the solver must play.
    """

    puzzle_id: str
    fen: str
    moves_uci: tuple[str, ...]
    rating: int = 0
    rating_deviation: int = 0
    popularity: int = 0
    nb_plays: int = 0
    themes: tuple[str, ...] = ()
    game_url: str = ""
    opening_tags: tuple[str, ...] = ()
    fen_is_before_last_move: bool = True

    @property
    def last_move_uci(self) -> str:
        if not self.moves_uci:
            raise ValueError("puzzle has no moves")
        return self.moves_uci[0]

    @property
    def solution_uci(self) -> tuple[str, ...]:
        return self.moves_uci[1:]


@dataclass(frozen=True, slots=True)
class PuzzleAttempt:
    judgement: PuzzleJudgement
    expected: MoveAction | None = None
    notation: str = ""


class PuzzleService:
    def __init__(self, mode: GameMode) -> None:
        self._mode = mode

    def load_from_fen(self, fen: str) -> GameState:
        return parse_fen(fen, self._mode)

    def is_solution(self, state: GameState, moves: list[Action]) -> bool:
        expected = self._solution_from_state(state)
        return expected is not None and list(moves) == expected

    def solve(self, state: GameState, max_depth: int) -> list[Action] | None:
        if max_depth < 0:
            raise ValueError("max_depth must be non-negative")

        expected = self._solution_from_state(state)
        if expected is None or len(expected) > max_depth:
            return None
        return list(expected)

    def _solution_from_state(self, state: GameState) -> list[MoveAction] | None:
        solution = state.extras.get("solution")
        if solution is None:
            return None
        if not isinstance(solution, list) or not all(
            isinstance(action, MoveAction) for action in solution
        ):
            raise TypeError("state.extras['solution'] must be a list[MoveAction]")
        return solution


class PuzzleSession:
    """Interactive Lichess-style solver: check the player move, reveal, next."""

    def __init__(self, mode: GameMode, puzzles: Sequence[LichessPuzzle]) -> None:
        if not puzzles:
            raise ValueError("puzzles must not be empty")
        self.mode = mode
        self._puzzles = tuple(puzzles)
        self._game = LocalGameService(mode)
        self._index = 0
        self._ply = 0
        self._awaiting_reveal = False
        self.load_index(0)

    @property
    def game(self) -> LocalGameService:
        return self._game

    @property
    def puzzles(self) -> tuple[LichessPuzzle, ...]:
        return self._puzzles

    @property
    def puzzle(self) -> LichessPuzzle:
        return self._puzzles[self._index]

    @property
    def index(self) -> int:
        return self._index

    @property
    def total(self) -> int:
        return len(self._puzzles)

    @property
    def solver_side(self) -> PieceSide:
        return self._game.state.side_to_move

    @property
    def last_move(self) -> MoveAction | None:
        uci = self.puzzle.last_move_uci
        files = self.mode.board.shape.files
        ranks = self.mode.board.shape.ranks
        try:
            return parse_uci(uci, files=files, ranks=ranks)
        except ValueError:
            return None

    @property
    def expected_uci(self) -> str | None:
        solution = self.puzzle.solution_uci
        if self._ply >= len(solution):
            return None
        return solution[self._ply]

    @property
    def hint_move(self) -> MoveAction | None:
        """Last shown ply: opponent setup at the start, otherwise the previous solution move."""
        if self._ply == 0:
            return self.last_move
        previous = self.puzzle.solution_uci[self._ply - 1]
        shape = self.mode.board.shape
        try:
            return parse_uci(previous, files=shape.files, ranks=shape.ranks)
        except ValueError:
            return None

    def load_index(self, index: int) -> GameState:
        if not 0 <= index < len(self._puzzles):
            raise IndexError("puzzle index out of range")
        puzzle = self._puzzles[index]
        state = parse_fen(puzzle.fen, self.mode)
        self._game.load_position(state)
        if puzzle.fen_is_before_last_move:
            setup = legal_move_for_uci(self.mode, self._game.state, puzzle.last_move_uci)
            if setup is None:
                raise ValueError(f"setup move is not legal for puzzle {puzzle.puzzle_id}")
            self._game.play(setup)
        self._index = index
        self._ply = 0
        self._awaiting_reveal = False
        return self._game.state

    def next_puzzle(self) -> GameState:
        return self.load_index((self._index + 1) % len(self._puzzles))

    def attempt(self, move: MoveAction) -> PuzzleAttempt:
        if self._awaiting_reveal:
            return PuzzleAttempt(PuzzleJudgement.ILLEGAL)
        legal = {action for action in self._game.legal_moves()}
        if move not in legal:
            return PuzzleAttempt(PuzzleJudgement.ILLEGAL)

        expected_uci = self.expected_uci
        expected = (
            legal_move_for_uci(self.mode, self._game.state, expected_uci)
            if expected_uci is not None
            else None
        )
        notation = (
            _notation_for(self.mode, self._game.state, expected)
            if expected is not None
            else ""
        )
        if _gives_checkmate(self.mode, self._game.state, move):
            self._game.play(move)
            self._ply = len(self.puzzle.solution_uci)
            return PuzzleAttempt(PuzzleJudgement.SOLVED, expected=move, notation=notation)

        if expected is None or not moves_match(move, expected):
            self._awaiting_reveal = True
            return PuzzleAttempt(
                PuzzleJudgement.WRONG, expected=expected, notation=notation
            )

        self._game.play(move)
        self._ply += 1
        if self._ply >= len(self.puzzle.solution_uci):
            return PuzzleAttempt(PuzzleJudgement.SOLVED, expected=move, notation=notation)
        reply_uci = self.puzzle.solution_uci[self._ply]
        reply = legal_move_for_uci(self.mode, self._game.state, reply_uci)
        if reply is None:
            return PuzzleAttempt(PuzzleJudgement.SOLVED, expected=move, notation=notation)
        self._game.play(reply)
        self._ply += 1
        if self._ply >= len(self.puzzle.solution_uci):
            return PuzzleAttempt(PuzzleJudgement.SOLVED, expected=move, notation=notation)
        return PuzzleAttempt(PuzzleJudgement.CORRECT, expected=move, notation=notation)

    def play_expected(self) -> MoveAction | None:
        """Play the correct move so the UI can show it after a wrong attempt."""
        expected_uci = self.expected_uci
        if expected_uci is None:
            return None
        expected = legal_move_for_uci(self.mode, self._game.state, expected_uci)
        if expected is None:
            return None
        self._game.play(expected)
        return expected


def moves_match(played: MoveAction, expected: MoveAction) -> bool:
    if played.from_square != expected.from_square:
        return False
    if played.to_square != expected.to_square:
        return False
    if expected.promotion_choice is None:
        return True
    return played.promotion_choice == expected.promotion_choice


def legal_move_for_uci(
    mode: GameMode, state: GameState, uci: str
) -> MoveAction | None:
    shape = mode.board.shape
    try:
        target = parse_uci(uci, files=shape.files, ranks=shape.ranks)
    except ValueError:
        return None
    for action in MoveGenerator(mode).generate_legal(state):
        if isinstance(action, MoveAction) and moves_match(action, target):
            return action
    return None


def puzzle_line_is_legal(mode: GameMode, puzzle: LichessPuzzle) -> bool:
    """Return True when every UCI ply of the puzzle is legal in ``mode``."""
    try:
        state = parse_fen(puzzle.fen, mode)
        plies = (
            puzzle.moves_uci
            if puzzle.fen_is_before_last_move
            else puzzle.solution_uci
        )
        for uci in plies:
            move = legal_move_for_uci(mode, state, uci)
            if move is None:
                return False
            state = mode.apply_turn(
                state, Turn(state.side_to_move, [move]), record_history=False
            )
    except (ValueError, TypeError):
        return False
    return True


def parse_lichess_csv(text: str) -> list[LichessPuzzle]:
    reader = csv.DictReader(io.StringIO(text))
    puzzles: list[LichessPuzzle] = []
    for row in reader:
        puzzle_id = (row.get("PuzzleId") or "").strip()
        fen = (row.get("FEN") or "").strip()
        moves = tuple(
            token.lower()
            for token in (row.get("Moves") or "").split()
            if token.strip()
        )
        if not puzzle_id or not fen or len(moves) < 2:
            continue
        themes = _split_tags(row.get("Themes"))
        opening = _split_tags(row.get("OpeningTags"))
        puzzles.append(
            LichessPuzzle(
                puzzle_id=puzzle_id,
                fen=fen,
                moves_uci=moves,
                rating=_as_int(row.get("Rating")),
                rating_deviation=_as_int(row.get("RatingDeviation")),
                popularity=_as_int(row.get("Popularity")),
                nb_plays=_as_int(row.get("NbPlays")),
                themes=themes,
                game_url=(row.get("GameUrl") or "").strip(),
                opening_tags=opening,
            )
        )
    return puzzles


def parse_lichess_json(text: str) -> list[LichessPuzzle]:
    payload = json.loads(text)
    if isinstance(payload, dict):
        rows = payload.get("puzzles", payload.get("rows", []))
    else:
        rows = payload
    if not isinstance(rows, list):
        raise ValueError("JSON puzzle catalog must be a list or an object with puzzles")
    puzzles: list[LichessPuzzle] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = _puzzle_from_mapping(row)
        if parsed is not None:
            puzzles.append(parsed)
    return puzzles


def format_lichess_csv(puzzles: Sequence[LichessPuzzle]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_LICHESS_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for puzzle in puzzles:
        writer.writerow(
            {
                "PuzzleId": puzzle.puzzle_id,
                "FEN": puzzle.fen,
                "Moves": " ".join(puzzle.moves_uci),
                "Rating": puzzle.rating,
                "RatingDeviation": puzzle.rating_deviation,
                "Popularity": puzzle.popularity,
                "NbPlays": puzzle.nb_plays,
                "Themes": " ".join(puzzle.themes),
                "GameUrl": puzzle.game_url,
                "OpeningTags": " ".join(puzzle.opening_tags),
            }
        )
    return buffer.getvalue()


def _puzzle_from_mapping(row: dict[str, object]) -> LichessPuzzle | None:
    if "PuzzleId" in row or "FEN" in row:
        puzzle_id = str(row.get("PuzzleId") or row.get("id") or "").strip()
        fen = str(row.get("FEN") or row.get("fen") or "").strip()
        moves_raw = row.get("Moves") or row.get("moves") or ""
        if isinstance(moves_raw, str):
            moves = tuple(token.lower() for token in moves_raw.split() if token.strip())
        elif isinstance(moves_raw, list):
            moves = tuple(str(token).lower() for token in moves_raw)
        else:
            moves = ()
        if not puzzle_id or not fen or len(moves) < 2:
            return None
        themes = _tags_from_value(row.get("Themes") or row.get("themes"))
        opening = _tags_from_value(row.get("OpeningTags") or row.get("openingTags"))
        game_url = str(row.get("GameUrl") or row.get("game_url") or "").strip()
        if not game_url:
            game_id = str(row.get("GameId") or row.get("gameId") or "").strip()
            if game_id:
                game_url = (
                    game_id
                    if game_id.startswith("http")
                    else f"https://lichess.org/{game_id.lstrip('/')}"
                )
        return LichessPuzzle(
            puzzle_id=puzzle_id,
            fen=fen,
            moves_uci=moves,
            rating=_as_int(row.get("Rating") or row.get("rating")),
            rating_deviation=_as_int(
                row.get("RatingDeviation") or row.get("ratingDeviation")
            ),
            popularity=_as_int(row.get("Popularity") or row.get("popularity")),
            nb_plays=_as_int(row.get("NbPlays") or row.get("plays") or row.get("nbPlays")),
            themes=themes,
            game_url=game_url,
            opening_tags=opening,
        )

    puzzle_id = str(row.get("id") or "").strip()
    presented = str(row.get("fen") or "").strip()
    last_move = str(row.get("lastMove") or row.get("last_move") or "").strip().lower()
    solution_raw = row.get("solution") or ()
    if isinstance(solution_raw, str):
        solution = tuple(token.lower() for token in solution_raw.split() if token.strip())
    else:
        solution = tuple(str(token).lower() for token in solution_raw)
    if not puzzle_id or not presented or not last_move or not solution:
        return None
    game_id = str(row.get("gameId") or row.get("game_id") or "").strip()
    game_url = (
        game_id
        if game_id.startswith("http")
        else (f"https://lichess.org/{game_id}" if game_id else "")
    )
    return LichessPuzzle(
        puzzle_id=puzzle_id,
        fen=presented,
        moves_uci=(last_move, *solution),
        rating=_as_int(row.get("rating")),
        nb_plays=_as_int(row.get("plays")),
        themes=_tags_from_value(row.get("themes")),
        game_url=game_url,
        fen_is_before_last_move=False,
    )


def _gives_checkmate(mode: GameMode, state: GameState, move: MoveAction) -> bool:
    after = mode.apply_turn(
        state, Turn(state.side_to_move, [move]), record_history=False
    )
    outcome = mode.outcome(after)
    return outcome.status is OutcomeStatus.WIN and outcome.reason == "checkmate"


def _notation_for(mode: GameMode, state: GameState, move: MoveAction) -> str:
    turn = Turn(state.side_to_move, [move])
    after = mode.apply_turn(state, turn, record_history=False)
    return format_turn(
        turn, before=state, after=after, style=NotationStyle.FROM_TO
    ) or format_uci(move)


def _split_tags(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(token for token in value.split() if token)


def _tags_from_value(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return _split_tags(value)
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


def _as_int(value: object) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(str(value)))
    except ValueError:
        return 0

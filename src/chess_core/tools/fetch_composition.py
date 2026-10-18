"""Download a small orthodox chess-composition pack from YACPDB.

The pack is direct mates in 3–5 whose first move is quiet (not a check), so they
are composition problems rather than a forcing series of checks. Each row keeps
the author and a link to the YACPDB entry. Only one author line is stored: the
puzzle player follows that main variation.

Usage::

    python -m chess_core.tools.fetch_composition
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from chess_core.app.game import GameStatus, evaluate_status
from chess_core.app.puzzles import legal_move_for_uci
from chess_core.core.move import Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import parse_fen
from chess_core.infra.paths import puzzles_dir
from chess_core.infra.storage.lichess_puzzles import COMPOSITION_CSV_NAME
from chess_core.modes.chess import classic_chess

YACPDB_ENTRY = "https://www.yacpdb.org/json.php?entry&id={problem_id}"
_USER_AGENT = "ChessCoreEducation/1.0"
_MATE_LENGTHS = (3, 4, 5)
_RATINGS = {3: 1900, 4: 2200, 5: 2500}
_ALLOWED_OPTION = re.compile(
    r"^(?:defence\s+\d+|set\s*play|threat|white to play|black to play)$",
    re.IGNORECASE,
)
_PIECE_TOKEN = re.compile(r"^[KQRBSP][a-h][1-8]$")
_MOVE = (
    r"(?:[KQRBS][a-h][1-8]|[a-h][1-8])"
    r"[x*-][a-h][1-8]"
    r"(?:=[QRBSN])?"
)
_MOVE_RE = re.compile(_MOVE, re.IGNORECASE)
_KEY_RE = re.compile(rf"1\.(?!\.)\s*({_MOVE})\s*!", re.IGNORECASE)
_COMMENT_RE = re.compile(r"\{[^{}]*\}|\([^()]*\)")
_PROMO = {"Q": "q", "R": "r", "B": "b", "S": "n", "N": "n"}
_FEN_LETTER = {"K": "k", "Q": "q", "R": "r", "B": "b", "S": "n", "P": "p"}


@dataclass(frozen=True, slots=True)
class CompositionPuzzle:
    problem_id: int
    fen: str
    moves_uci: tuple[str, ...]
    mate_in: int
    author: str
    source: str

    @property
    def puzzle_id(self) -> str:
        return f"Y{self.problem_id}"

    @property
    def themes(self) -> str:
        return f"composition mateIn{self.mate_in} quietMove long"

    @property
    def url(self) -> str:
        return f"https://www.yacpdb.org/#{self.problem_id}"


def fen_from_algebraic(algebraic: dict) -> str | None:
    white = algebraic.get("white") or []
    black = algebraic.get("black") or []
    board = [["." for _file in range(8)] for _rank in range(8)]
    for side, tokens in (("w", white), ("b", black)):
        for token in tokens:
            if not isinstance(token, str) or _PIECE_TOKEN.match(token) is None:
                return None
            letter = _FEN_LETTER[token[0]]
            file = ord(token[1]) - ord("a")
            rank = int(token[2]) - 1
            if board[rank][file] != ".":
                return None
            board[rank][file] = letter.upper() if side == "w" else letter
    rows: list[str] = []
    for rank in range(7, -1, -1):
        empty = 0
        row = ""
        for file in range(8):
            cell = board[rank][file]
            if cell == ".":
                empty += 1
                continue
            if empty:
                row += str(empty)
                empty = 0
            row += cell
        if empty:
            row += str(empty)
        rows.append(row)
    return f"{'/'.join(rows)} w - - 0 1"


def move_to_uci(token: str) -> str | None:
    match = _MOVE_RE.fullmatch(token)
    if match is None:
        return None
    squares = re.findall(r"[a-h][1-8]", token.lower())
    if len(squares) != 2:
        return None
    promo = ""
    promo_match = re.search(r"=([QRBSN])", token, re.IGNORECASE)
    if promo_match:
        promo = _PROMO[promo_match.group(1).upper()]
    return f"{squares[0]}{squares[1]}{promo}"


def main_line(solution: str, mate_in: int, fen: str) -> tuple[str, ...] | None:
    """Author key plus the first defence that mates in exactly ``mate_in`` white moves."""

    stripped = _COMMENT_RE.sub(" ", solution or "")
    key_match = None
    for candidate in _KEY_RE.finditer(stripped):
        key_match = candidate
    if key_match is None:
        return None
    key = move_to_uci(key_match.group(1))
    if key is None:
        return None
    rest = stripped[key_match.end() :]
    variations = [
        part for part in re.split(r"(?=1\.\.\.)", rest) if part.strip().startswith("1...")
    ]
    if not variations:
        return None
    mode = classic_chess()
    for variation in variations:
        tokens = [move_to_uci(token) for token in _MOVE_RE.findall(variation)]
        uci_tokens = [token for token in tokens if token]
        line = _play_line(mode, fen, key, uci_tokens, mate_in)
        if line is not None:
            return line
    return None


def composition_from_entry(entry: dict) -> CompositionPuzzle | None:
    stipulation = str(entry.get("stipulation") or "")
    mate = re.fullmatch(r"#(\d+)", stipulation)
    if mate is None:
        return None
    mate_in = int(mate.group(1))
    if mate_in not in _MATE_LENGTHS:
        return None
    if entry.get("twins"):
        return None
    options = entry.get("options") or []
    if any(not isinstance(option, str) or _ALLOWED_OPTION.match(option) is None for option in options):
        return None
    algebraic = entry.get("algebraic")
    if not isinstance(algebraic, dict):
        return None
    fen = fen_from_algebraic(algebraic)
    if fen is None:
        return None
    line = main_line(str(entry.get("solution") or ""), mate_in, fen)
    if line is None:
        return None
    if not _quiet_key(fen, line[0]):
        return None
    authors = entry.get("authors") or []
    author = authors[0] if authors and isinstance(authors[0], str) else ""
    source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    source_name = str(source.get("name") or "")
    problem_id = entry.get("id")
    if not isinstance(problem_id, int):
        return None
    return CompositionPuzzle(
        problem_id=problem_id,
        fen=fen,
        moves_uci=line,
        mate_in=mate_in,
        author=author,
        source=source_name,
    )


def write_composition_csv(puzzles: list[CompositionPuzzle], path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = (
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
        "Diagram",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for puzzle in puzzles:
            writer.writerow(
                {
                    "PuzzleId": puzzle.puzzle_id,
                    "FEN": puzzle.fen,
                    "Moves": " ".join(puzzle.moves_uci),
                    "Rating": _RATINGS[puzzle.mate_in],
                    "RatingDeviation": 0,
                    "Popularity": 100,
                    "NbPlays": 0,
                    "Themes": puzzle.themes,
                    "GameUrl": puzzle.url,
                    "OpeningTags": puzzle.author,
                    "Diagram": "1",
                }
            )


def fetch_composition_pack(
    *,
    limit: int = 48,
    start_id: int = 200000,
    stop_id: int = 460000,
    step: int = 700,
    workers: int = 6,
) -> list[CompositionPuzzle]:
    ids = list(range(start_id, stop_id, step))
    found: list[CompositionPuzzle] = []
    seen: set[int] = set()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_download_entry, problem_id): problem_id for problem_id in ids}
        for future in as_completed(futures):
            entry = future.result()
            if entry is None:
                continue
            puzzle = composition_from_entry(entry)
            if puzzle is None or puzzle.problem_id in seen:
                continue
            seen.add(puzzle.problem_id)
            found.append(puzzle)
            if len(found) >= limit:
                break
    found.sort(key=lambda puzzle: (puzzle.mate_in, puzzle.problem_id))
    return found[:limit]


def _download_entry(problem_id: int) -> dict | None:
    url = YACPDB_ENTRY.format(problem_id=problem_id)
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        raw = urllib.request.urlopen(request, timeout=25).read()
    except OSError:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not payload.get("solution"):
        return None
    return payload


def _play_line(
    mode,
    fen: str,
    key: str,
    reply_uci: list[str],
    mate_in: int,
) -> tuple[str, ...] | None:
    try:
        state = parse_fen(fen, mode)
    except ValueError:
        return None
    played: list[str] = []
    for uci in (key, *reply_uci):
        move = legal_move_for_uci(mode, state, uci)
        if move is None:
            break
        state = state.apply_turn(Turn(state.side_to_move, [move]), record_history=False)
        played.append(uci)
        status = evaluate_status(mode, MoveGenerator(mode), state, is_live=True)
        if status is GameStatus.CHECKMATE:
            white_moves = (len(played) + 1) // 2
            if white_moves == mate_in:
                return tuple(played)
            return None
    return None


def _quiet_key(fen: str, key_uci: str) -> bool:
    mode = classic_chess()
    state = parse_fen(fen, mode)
    move = legal_move_for_uci(mode, state, key_uci)
    if move is None:
        return False
    after = state.apply_turn(Turn(state.side_to_move, [move]), record_history=False)
    status = evaluate_status(mode, MoveGenerator(mode), after, is_live=True)
    return status not in {GameStatus.CHECK, GameStatus.CHECKMATE}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=48)
    args = parser.parse_args()
    puzzles = fetch_composition_pack(limit=args.limit)
    if len(puzzles) < 12:
        raise SystemExit(f"only {len(puzzles)} composition problems verified")
    destination = puzzles_dir() / COMPOSITION_CSV_NAME
    write_composition_csv(puzzles, destination)
    print(f"wrote {len(puzzles)} problems to {destination}")


if __name__ == "__main__":
    main()

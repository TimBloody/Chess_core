"""Game record: turn journal, timeline navigation, local undo."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from re import sub

from chess_core.core.gamemode import GameMode
from chess_core.core.move import Turn
from chess_core.core.notation import to_fen
from chess_core.core.repetition import seed_repetition_log
from chess_core.core.pgn import (
    PgnGame,
    chessbase_variant,
    format_pgn_game,
    pgn_game_from_tags,
)
from chess_core.core.piece import PieceSide
from chess_core.core.state import GameState


def position_snapshot(state: GameState) -> GameState:
    """Position-only clone without history (for replay and movegen probes)."""
    return state.clone(include_history=False)


def strip_history(state: GameState) -> GameState:
    """Return a position snapshot with empty history and a fresh repetition log."""
    return seed_repetition_log(position_snapshot(state))


@dataclass(frozen=True, slots=True)
class TurnRecord:
    turn: Turn
    revision: int
    notation: str = ""


@dataclass(frozen=True, slots=True)
class MoveLogLine:
    """One numbered notation row: white ply, black ply, or both."""

    number: int
    white: str = ""
    black: str = ""
    white_revision: int | None = None
    black_revision: int | None = None

    @property
    def text(self) -> str:
        if self.black:
            return f"{self.number}. {self.white}  {self.black}".strip()
        if self.white:
            return f"{self.number}. {self.white}"
        return ""

    @property
    def end_revision(self) -> int:
        if self.black_revision is not None:
            return self.black_revision
        if self.white_revision is not None:
            return self.white_revision
        return 0

    def ply_revisions(self) -> tuple[int, ...]:
        plies: list[int] = []
        if self.white_revision is not None:
            plies.append(self.white_revision)
        if self.black_revision is not None:
            plies.append(self.black_revision)
        return tuple(plies)


@dataclass
class GameRecord:
    mode: GameMode
    initial: GameState
    turns: list[TurnRecord] = field(default_factory=list)
    live_revision: int = 0
    view_revision: int = 0
    _snapshots: list[GameState] = field(default_factory=list)

    @classmethod
    def from_mode(cls, mode: GameMode, initial: GameState | None = None) -> GameRecord:
        start = strip_history(initial or mode.initial_state())
        start.extras["mode"] = mode
        record = cls(mode=mode, initial=deepcopy(start))
        record._snapshots = [deepcopy(start)]
        return record

    @property
    def is_live(self) -> bool:
        return self.view_revision == self.live_revision

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def state_at(self, revision: int) -> GameState:
        if not 0 <= revision <= self.live_revision:
            raise ValueError(f"revision {revision} out of range 0..{self.live_revision}")
        if revision < len(self._snapshots):
            return self._snapshots[revision].clone(include_history=False)
        state = self.initial.clone(include_history=False)
        for index in range(revision):
            state = state.apply_turn(self.turns[index].turn, record_history=False)
        return state

    def current_view_state(self) -> GameState:
        return self.state_at(self.view_revision)

    def live_state(self) -> GameState:
        return self.state_at(self.live_revision)

    def turn_at(self, revision: int) -> Turn | None:
        """Turn that produced ``revision``. The start position (0) has none."""
        if revision <= 0:
            return None
        index = revision - 1
        if 0 <= index < len(self.turns) and self.turns[index].revision == revision:
            return self.turns[index].turn
        for record in self.turns:
            if record.revision == revision:
                return record.turn
        return None

    def go_to(self, revision: int) -> GameState:
        self.view_revision = revision
        return self.current_view_state()

    def go_live(self) -> GameState:
        self.view_revision = self.live_revision
        return self.live_state()

    def branch_from_view(self) -> GameRecord:
        """Copy the record and discard moves after the currently viewed position."""
        branch = deepcopy(self)
        branch.turns = branch.turns[: branch.view_revision]
        branch._snapshots = branch._snapshots[: branch.view_revision + 1]
        branch.live_revision = branch.view_revision
        return branch

    def append_turn(
        self,
        turn: Turn,
        *,
        notation: str = "",
    ) -> GameState:
        if not self.is_live:
            raise RuntimeError("cannot play while viewing history; call go_live() first")
        if self.view_revision < len(self.turns):
            self.turns = self.turns[: self.view_revision]
            self._snapshots = self._snapshots[: self.view_revision + 1]

        prev = self.live_state()
        next_state = prev.apply_turn(turn, record_history=True)
        self.live_revision += 1
        self.view_revision = self.live_revision
        self.turns.append(
            TurnRecord(
                turn=turn,
                revision=self.live_revision,
                notation=notation,
            )
        )
        self._snapshots.append(next_state.clone(include_history=False))
        return next_state

    def undo_last_turn(self) -> GameState:
        if self.live_revision == 0:
            raise RuntimeError("no turns to undo")
        self.turns.pop()
        self._snapshots.pop()
        self.live_revision -= 1
        self.view_revision = self.live_revision
        return self.live_state()

    def append_snapshot(self, state: GameState, *, notation: str = "", keep_view: bool = False) -> GameState:
        """Record a new live position without a reconstructed turn (network sync)."""

        saved_view = self.view_revision
        moved_side = self.live_state().side_to_move
        next_state = strip_history(state)
        next_state.extras["mode"] = self.mode
        self.live_revision += 1
        self._snapshots.append(deepcopy(next_state))
        self.turns.append(
            TurnRecord(
                turn=Turn(moved_side, []),
                revision=self.live_revision,
                notation=notation or "…",
            )
        )
        self.view_revision = min(saved_view, self.live_revision) if keep_view else self.live_revision
        return self.current_view_state()

    def truncate_to(self, revision: int) -> GameState:
        if not 0 <= revision <= self.live_revision:
            raise ValueError(f"revision {revision} out of range 0..{self.live_revision}")
        self.turns = self.turns[:revision]
        self._snapshots = self._snapshots[: revision + 1]
        self.live_revision = revision
        self.view_revision = min(self.view_revision, revision)
        return self.current_view_state()

    def reset(self, initial: GameState | None = None) -> GameState:
        start = strip_history(initial or self.mode.initial_state())
        start.extras["mode"] = self.mode
        self.initial = deepcopy(start)
        self.turns.clear()
        self._snapshots = [deepcopy(start)]
        self.live_revision = 0
        self.view_revision = 0
        return self.live_state()

    def move_log_lines(self) -> list[MoveLogLine]:
        """Pair consecutive White/Black turns into numbered notation rows.

        Each ``Turn`` is one ply. Row *n* is a full move, not ply *n*.
        """
        lines: list[MoveLogLine] = []
        move_number = 1
        index = 0
        while index < len(self.turns):
            white = ""
            black = ""
            white_revision: int | None = None
            black_revision: int | None = None
            if self.turns[index].turn.side is PieceSide.WHITE:
                white = self.turns[index].notation
                white_revision = self.turns[index].revision
                index += 1
                if index < len(self.turns) and self.turns[index].turn.side is PieceSide.BLACK:
                    black = self.turns[index].notation
                    black_revision = self.turns[index].revision
                    index += 1
            else:
                black = self.turns[index].notation
                black_revision = self.turns[index].revision
                index += 1
            lines.append(
                MoveLogLine(
                    number=move_number,
                    white=white,
                    black=black,
                    white_revision=white_revision,
                    black_revision=black_revision,
                )
            )
            move_number += 1
        return lines

    def move_log(self, *, paired: bool = True) -> list[str]:
        if not paired:
            return [entry.notation for entry in self.turns if entry.notation]
        return [line.text for line in self.move_log_lines() if line.text]

    def to_pgn_game(
        self,
        *,
        result: str = "*",
        comment: str = "",
        exported_at: datetime | None = None,
        white: str = "?",
        black: str = "?",
    ) -> PgnGame:
        """Seven-tag PGN game for ChessBase 16 / multi-game .pgn databases."""
        when = exported_at or datetime.now()
        date = when.strftime("%Y.%m.%d")
        tags: list[tuple[str, str]] = [
            ("Event", "Chess Core"),
            ("Site", "Local"),
            ("Date", date),
            ("Round", "-"),
            ("White", white or "?"),
            ("Black", black or "?"),
            ("Result", result),
            ("EventDate", date),
            ("Mode", self.mode.id),
            ("ModeName", self.mode.name),
            ("PlyCount", str(self.turn_count)),
        ]
        variant = chessbase_variant(self.mode.id)
        if variant:
            tags.append(("Variant", variant))
        if comment:
            tags.append(("Termination", comment))
        setup = _setup_fen(self.initial, self.mode)
        if setup is not None:
            tags.append(("SetUp", "1"))
            tags.append(("FEN", setup))
        moves = " ".join(self.move_log())
        return pgn_game_from_tags(tags, moves, comment=comment)

    def format_transcript(
        self,
        *,
        result: str = "*",
        comment: str = "",
        exported_at: datetime | None = None,
        white: str = "?",
        black: str = "?",
    ) -> str:
        """ChessBase-compatible PGN for any mode: STR tags, moves, result.

        New modes inherit this from the turn journal. Do not format a
        transcript by branching on ``mode.id``.
        """
        return format_pgn_game(
            self.to_pgn_game(
                result=result,
                comment=comment,
                exported_at=exported_at,
                white=white,
                black=black,
            )
        )


def transcript_filename(mode_id: str, exported_at: datetime | None = None) -> str:
    when = exported_at or datetime.now()
    safe = sub(r"[^A-Za-z0-9_-]+", "-", mode_id).strip("-") or "game"
    return f"{safe}-{when.strftime('%Y%m%d-%H%M')}.pgn"


def _setup_fen(initial: GameState, mode: GameMode) -> str | None:
    try:
        current = to_fen(initial)
        start = to_fen(mode.initial_state())
    except ValueError:
        return None
    if current == start:
        return None
    return current

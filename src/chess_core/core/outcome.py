"""Game outcome: active, win, draw with optional winner and reason."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from chess_core.core.piece import PieceSide


class OutcomeStatus(Enum):
    ACTIVE = auto()
    WIN = auto()
    DRAW = auto()


@dataclass(frozen=True, slots=True)
class GameOutcome:
    status: OutcomeStatus
    winner: PieceSide | None = None
    reason: str | None = None
    score: tuple[int, int] | None = None

    @property
    def is_finished(self) -> bool:
        return self.status is not OutcomeStatus.ACTIVE

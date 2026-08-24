"""Tournament pairing models. No UI and no game rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PairingSystem(Enum):
    COLOR_DRAW = "color_draw"
    ROUND_ROBIN = "round_robin"
    SWISS = "swiss"
    KNOCKOUT = "knockout"
    SCHEVENINGEN = "scheveningen"


@dataclass(frozen=True, slots=True)
class Player:
    player_id: str
    name: str
    rating: int = 0
    team: str | None = None


@dataclass(frozen=True, slots=True)
class Pairing:
    round_index: int
    board: int
    white_id: str | None
    black_id: str | None
    result: str | None = None

    @property
    def is_bye(self) -> bool:
        return self.white_id is None or self.black_id is None


@dataclass(frozen=True, slots=True)
class Standing:
    player: Player
    points: float
    games: int
    wins: int
    draws: int
    losses: int
    buchholz: float = 0.0
    white_games: int = 0
    black_games: int = 0


RESULT_WHITE = "1-0"
RESULT_BLACK = "0-1"
RESULT_DRAW = "1/2-1/2"
RESULT_BYE = "bye"

VALID_RESULTS = frozenset({RESULT_WHITE, RESULT_BLACK, RESULT_DRAW, RESULT_BYE})


def parse_player_line(line: str, *, index: int) -> Player:
    """Parse ``Name|rating|team``; rating and team are optional."""
    raw = line.strip()
    if not raw:
        raise ValueError("player line is empty")
    parts = [part.strip() for part in raw.split("|")]
    name = parts[0]
    if not name:
        raise ValueError("player name is required")
    rating = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    team = parts[2] if len(parts) > 2 and parts[2] else None
    return Player(player_id=f"p{index}", name=name, rating=rating, team=team)


def parse_player_list(text: str) -> tuple[Player, ...]:
    players: list[Player] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        players.append(parse_player_line(line, index=len(players) + 1))
    return tuple(players)


def points_for(pairing: Pairing, player_id: str) -> float | None:
    if pairing.result is None:
        return None
    if pairing.is_bye:
        if player_id in {pairing.white_id, pairing.black_id} and pairing.result == RESULT_BYE:
            return 1.0
        return None
    if pairing.result == RESULT_DRAW:
        return 0.5
    if pairing.result == RESULT_WHITE:
        return 1.0 if player_id == pairing.white_id else 0.0
    if pairing.result == RESULT_BLACK:
        return 1.0 if player_id == pairing.black_id else 0.0
    raise ValueError(f"unknown result: {pairing.result}")

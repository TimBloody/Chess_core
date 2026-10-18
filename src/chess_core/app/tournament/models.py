"""Tournament pairing models. No UI and no game rules."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum


class PairingSystem(Enum):
    COLOR_DRAW = "color_draw"
    ROUND_ROBIN = "round_robin"
    SWISS = "swiss"
    SWISS_NO_COLOR = "swiss_no_color"
    KNOCKOUT = "knockout"
    SCHEVENINGEN = "scheveningen"

    @property
    def is_swiss(self) -> bool:
        return self in {PairingSystem.SWISS, PairingSystem.SWISS_NO_COLOR}


class PlayerStatus(Enum):
    ACTIVE = "active"
    ABSENT = "absent"
    WITHDRAWN = "withdrawn"
    LATE_ENTRY = "late_entry"


class ResultKind(Enum):
    PLAYED = "played"
    FORFEIT = "forfeit"
    BYE = "bye"
    ZERO_POINT_BYE = "zpb"
    HALF_POINT_BYE = "hpb"


TITLE_RANK: dict[str, int] = {
    "GM": 8,
    "IM": 7,
    "WGM": 6,
    "FM": 5,
    "WIM": 4,
    "CM": 3,
    "WFM": 2,
    "WCM": 1,
}


@dataclass(frozen=True, slots=True)
class Player:
    player_id: str
    name: str
    rating: int = 0
    team: str | None = None
    title: str = ""
    federation: str = ""
    status: PlayerStatus = PlayerStatus.ACTIVE
    start_number: int = 0

    @property
    def title_rank(self) -> int:
        return TITLE_RANK.get(self.title.upper(), 0)

    def with_status(self, status: PlayerStatus) -> Player:
        return replace(self, status=status)

    def with_start_number(self, start_number: int) -> Player:
        return replace(self, start_number=start_number)

    def with_updates(self, **fields: object) -> Player:
        allowed = {"name", "rating", "team", "title", "federation", "status"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"cannot update player fields: {sorted(unknown)}")
        return replace(self, **fields)


@dataclass(frozen=True, slots=True)
class Pairing:
    round_index: int
    board: int
    white_id: str | None
    black_id: str | None
    result: str | None = None
    result_kind: ResultKind | None = None
    manual: bool = False

    @property
    def is_bye(self) -> bool:
        return self.white_id is None or self.black_id is None

    @property
    def kind(self) -> ResultKind | None:
        if self.result_kind is not None:
            return self.result_kind
        if self.result is None:
            return None
        return result_kind_for(self.result)

    def player_ids(self) -> tuple[str, ...]:
        return tuple(player_id for player_id in (self.white_id, self.black_id) if player_id)


@dataclass(frozen=True, slots=True)
class Standing:
    player: Player
    points: float
    games: int
    wins: int
    draws: int
    losses: int
    buchholz: float = 0.0
    sonneborn_berger: float = 0.0
    white_games: int = 0
    black_games: int = 0
    place: int = 0


@dataclass(frozen=True, slots=True)
class CrosstableCell:
    """One round in a ranking crosstable (Swiss Manager style)."""

    round_index: int
    opponent_start: int | None
    color: str
    points: float | None
    label: str


@dataclass(frozen=True, slots=True)
class AuditEntry:
    action: str
    reason: str
    round_index: int | None = None
    detail: str = ""
    warnings: tuple[str, ...] = ()


RESULT_WHITE = "1-0"
RESULT_BLACK = "0-1"
RESULT_DRAW = "1/2-1/2"
RESULT_BYE = "bye"
RESULT_FORFEIT_WHITE = "1-0F"
RESULT_FORFEIT_BLACK = "0-1F"
RESULT_DOUBLE_FORFEIT = "0-0"
RESULT_ZPB = "zpb"
RESULT_HPB = "hpb"

VALID_RESULTS = frozenset(
    {
        RESULT_WHITE,
        RESULT_BLACK,
        RESULT_DRAW,
        RESULT_BYE,
        RESULT_FORFEIT_WHITE,
        RESULT_FORFEIT_BLACK,
        RESULT_DOUBLE_FORFEIT,
        RESULT_ZPB,
        RESULT_HPB,
    }
)

UNPLAYED_RESULTS = frozenset(
    {
        RESULT_BYE,
        RESULT_FORFEIT_WHITE,
        RESULT_FORFEIT_BLACK,
        RESULT_DOUBLE_FORFEIT,
        RESULT_ZPB,
        RESULT_HPB,
    }
)


def result_kind_for(result: str) -> ResultKind:
    if result == RESULT_BYE:
        return ResultKind.BYE
    if result == RESULT_ZPB:
        return ResultKind.ZERO_POINT_BYE
    if result == RESULT_HPB:
        return ResultKind.HALF_POINT_BYE
    if result in {RESULT_FORFEIT_WHITE, RESULT_FORFEIT_BLACK, RESULT_DOUBLE_FORFEIT}:
        return ResultKind.FORFEIT
    if result in {RESULT_WHITE, RESULT_BLACK, RESULT_DRAW}:
        return ResultKind.PLAYED
    raise ValueError(f"unknown result: {result}")


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
    if player_id not in pairing.player_ids():
        return None
    result = pairing.result
    if pairing.is_bye:
        if result == RESULT_BYE:
            return 1.0
        if result == RESULT_HPB:
            return 0.5
        if result in {RESULT_ZPB, RESULT_DOUBLE_FORFEIT, RESULT_BLACK, RESULT_WHITE}:
            return 0.0
        if result == RESULT_FORFEIT_WHITE and player_id == pairing.white_id:
            return 1.0
        return 0.0
    if result in {RESULT_DRAW, RESULT_HPB}:
        return 0.5
    if result in {RESULT_WHITE, RESULT_FORFEIT_WHITE}:
        return 1.0 if player_id == pairing.white_id else 0.0
    if result in {RESULT_BLACK, RESULT_FORFEIT_BLACK}:
        return 1.0 if player_id == pairing.black_id else 0.0
    if result in {RESULT_DOUBLE_FORFEIT, RESULT_ZPB}:
        return 0.0
    raise ValueError(f"unknown result: {result}")


def is_played_game(pairing: Pairing) -> bool:
    return pairing.result in {RESULT_WHITE, RESULT_BLACK, RESULT_DRAW} and not pairing.is_bye


def is_full_point_unplayed_win(pairing: Pairing, player_id: str) -> bool:
    """True when the player scored a win without playing (PAB or forfeit win)."""
    if pairing.result is None or player_id not in pairing.player_ids():
        return False
    if pairing.result == RESULT_BYE and pairing.is_bye:
        return True
    if pairing.result == RESULT_FORFEIT_WHITE and player_id == pairing.white_id:
        return True
    if pairing.result == RESULT_FORFEIT_BLACK and player_id == pairing.black_id:
        return True
    return False


def ranking_key(player: Player) -> tuple:
    return (-player.rating, -player.title_rank, player.name.casefold(), player.player_id)


def assign_pairing_numbers(players: tuple[Player, ...] | list[Player]) -> tuple[Player, ...]:
    ordered = sorted(players, key=ranking_key)
    return tuple(player.with_start_number(index) for index, player in enumerate(ordered, start=1))

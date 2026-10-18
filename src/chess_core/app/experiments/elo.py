"""Elo rating math for the experiments branch."""

from __future__ import annotations

from dataclasses import dataclass
import random


def expected_score(rating_a: float, rating_b: float, *, scale: float = 400.0) -> float:
    """Probability that A scores against B under the classic Elo model."""

    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / scale))


def update_elo(
    rating: float,
    expected: float,
    score: float,
    *,
    k: float = 20.0,
) -> float:
    return rating + k * (score - expected)


@dataclass(frozen=True, slots=True)
class RatedPlayer:
    name: str
    rating: float
    games: int = 0
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class SimulatedGame:
    white: str
    black: str
    result: str
    expected_white: float


def simulate_match(
    white: RatedPlayer,
    black: RatedPlayer,
    *,
    k: float = 20.0,
    rng: random.Random | None = None,
) -> tuple[RatedPlayer, RatedPlayer, SimulatedGame]:
    """Play one game whose result is drawn from Elo expectation, then update both ratings."""

    dice = rng or random.Random()
    expected_white = expected_score(white.rating, black.rating)
    draw_p = 0.16 * (1.0 - abs(expected_white - 0.5))
    p_white = max(0.0, expected_white * (1.0 - draw_p))
    roll = dice.random()
    if roll < p_white:
        white_score, result = 1.0, "1-0"
    elif roll < p_white + draw_p:
        white_score, result = 0.5, "½-½"
    else:
        white_score, result = 0.0, "0-1"
    black_score = 1.0 - white_score
    new_white = RatedPlayer(
        name=white.name,
        rating=update_elo(white.rating, expected_white, white_score, k=k),
        games=white.games + 1,
        score=white.score + white_score,
    )
    new_black = RatedPlayer(
        name=black.name,
        rating=update_elo(black.rating, 1.0 - expected_white, black_score, k=k),
        games=black.games + 1,
        score=black.score + black_score,
    )
    game = SimulatedGame(white.name, black.name, result, expected_white)
    return new_white, new_black, game


def round_robin(
    players: list[RatedPlayer],
    *,
    k: float = 20.0,
    rng: random.Random | None = None,
) -> tuple[list[RatedPlayer], list[SimulatedGame]]:
    dice = rng or random.Random()
    by_name = {player.name: player for player in players}
    games: list[SimulatedGame] = []
    names = [player.name for player in players]
    for i, white_name in enumerate(names):
        for black_name in names[i + 1 :]:
            white, black, game = simulate_match(by_name[white_name], by_name[black_name], k=k, rng=dice)
            by_name[white_name] = white
            by_name[black_name] = black
            games.append(game)
    ordered = [by_name[player.name] for player in players]
    ordered.sort(key=lambda item: item.rating, reverse=True)
    return ordered, games

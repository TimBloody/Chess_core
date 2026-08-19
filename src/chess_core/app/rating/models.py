"""Pure Elo mathematics and deterministic league simulations."""

from __future__ import annotations

from dataclasses import dataclass
from math import log10, sqrt
from random import Random


@dataclass(frozen=True, slots=True)
class EloParameters:
    """Parameters that define an Elo model and a synthetic player pool."""

    player_count: int = 50
    rounds: int = 40
    initial_rating: float = 1500.0
    strength_spread: float = 600.0
    k_factor: float = 24.0
    scale: float = 400.0
    draw_probability: float = 0.25
    white_advantage: float = 35.0
    provisional_multiplier: float = 1.5
    k_decay_games: int = 40
    rating_floor: float = 100.0
    certainty: float = 0.99
    seed: int = 42

    def validate(self) -> None:
        if self.player_count < 2:
            raise ValueError("player_count must be at least 2")
        if self.rounds < 1:
            raise ValueError("rounds must be positive")
        if self.k_factor <= 0 or self.scale <= 0:
            raise ValueError("k_factor and scale must be positive")
        if not 0.0 <= self.draw_probability < 1.0:
            raise ValueError("draw_probability must be in [0, 1)")
        if self.provisional_multiplier < 1.0:
            raise ValueError("provisional_multiplier must be at least 1")
        if self.k_decay_games < 1:
            raise ValueError("k_decay_games must be positive")
        if not 0.5 < self.certainty < 1.0:
            raise ValueError("certainty must be between 0.5 and 1")


@dataclass(frozen=True, slots=True)
class PlayerSnapshot:
    rank: int
    player_id: int
    name: str
    rating: float
    true_strength: float
    games: int
    wins: int
    draws: int
    losses: int


@dataclass(frozen=True, slots=True)
class SimulationResult:
    parameters: EloParameters
    players: tuple[PlayerSnapshot, ...]
    history: dict[int, tuple[float, ...]]
    rating_error: float

    @property
    def top_ten(self) -> tuple[PlayerSnapshot, ...]:
        return self.players[:10]


@dataclass(slots=True)
class _Player:
    player_id: int
    name: str
    rating: float
    true_strength: float
    games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0


def expected_score(
    rating_a: float,
    rating_b: float,
    *,
    scale: float = 400.0,
    advantage_a: float = 0.0,
) -> float:
    """Return A's expected score under the logistic Elo curve."""

    if scale <= 0:
        raise ValueError("scale must be positive")
    exponent = (rating_b - rating_a - advantage_a) / scale
    return 1.0 / (1.0 + 10.0**exponent)


def rating_gap_for_probability(probability: float, *, scale: float = 400.0) -> float:
    """Return the rating lead needed for a chosen practical certainty.

    Elo never reaches a literal 100% probability for a finite rating gap.
    """

    if not 0.5 < probability < 1.0:
        raise ValueError("probability must be between 0.5 and 1")
    if scale <= 0:
        raise ValueError("scale must be positive")
    return scale * log10(probability / (1.0 - probability))


def effective_k(parameters: EloParameters, games_played: int) -> float:
    """Use a larger provisional K and gradually stabilize established ratings."""

    progress = min(1.0, games_played / parameters.k_decay_games)
    provisional = parameters.provisional_multiplier + (
        1.0 - parameters.provisional_multiplier
    ) * progress
    established_decay = 1.0 / sqrt(
        1.0 + max(0, games_played - parameters.k_decay_games)
        / parameters.k_decay_games
    )
    return parameters.k_factor * provisional * established_decay


def update_pair(
    rating_a: float,
    rating_b: float,
    score_a: float,
    *,
    k_a: float,
    k_b: float | None = None,
    scale: float = 400.0,
    advantage_a: float = 0.0,
    rating_floor: float = 100.0,
) -> tuple[float, float]:
    """Update two ratings from one result."""

    if score_a not in (0.0, 0.5, 1.0):
        raise ValueError("score_a must be 0, 0.5, or 1")
    if k_a <= 0 or (k_b is not None and k_b <= 0):
        raise ValueError("K factors must be positive")
    expected_a = expected_score(
        rating_a, rating_b, scale=scale, advantage_a=advantage_a
    )
    k_b = k_a if k_b is None else k_b
    new_a = max(rating_floor, rating_a + k_a * (score_a - expected_a))
    new_b = max(rating_floor, rating_b + k_b * ((1.0 - score_a) - (1.0 - expected_a)))
    return new_a, new_b


def simulate_league(parameters: EloParameters) -> SimulationResult:
    """Simulate repeated random pairings with reproducible synthetic outcomes."""

    parameters.validate()
    rng = Random(parameters.seed)
    count = parameters.player_count
    step = parameters.strength_spread / max(1, count - 1)
    strongest = parameters.initial_rating + parameters.strength_spread / 2.0
    players = [
        _Player(
            player_id=index,
            name=f"Игрок {index + 1:03d}",
            rating=parameters.initial_rating,
            true_strength=strongest - index * step,
        )
        for index in range(count)
    ]
    history: dict[int, list[float]] = {
        player.player_id: [player.rating] for player in players
    }

    for _round in range(parameters.rounds):
        order = list(range(count))
        rng.shuffle(order)
        if len(order) % 2:
            order.pop()
        for offset in range(0, len(order), 2):
            white = players[order[offset]]
            black = players[order[offset + 1]]
            true_expectation = expected_score(
                white.true_strength,
                black.true_strength,
                scale=parameters.scale,
                advantage_a=parameters.white_advantage,
            )
            roll = rng.random()
            if roll < parameters.draw_probability:
                score_white = 0.5
                white.draws += 1
                black.draws += 1
            else:
                decisive_roll = (roll - parameters.draw_probability) / (
                    1.0 - parameters.draw_probability
                )
                if decisive_roll < true_expectation:
                    score_white = 1.0
                    white.wins += 1
                    black.losses += 1
                else:
                    score_white = 0.0
                    white.losses += 1
                    black.wins += 1
            white.rating, black.rating = update_pair(
                white.rating,
                black.rating,
                score_white,
                k_a=effective_k(parameters, white.games),
                k_b=effective_k(parameters, black.games),
                scale=parameters.scale,
                advantage_a=parameters.white_advantage,
                rating_floor=parameters.rating_floor,
            )
            white.games += 1
            black.games += 1
        for player in players:
            history[player.player_id].append(player.rating)

    ranked = sorted(players, key=lambda player: player.rating, reverse=True)
    snapshots = tuple(
        PlayerSnapshot(
            rank=rank,
            player_id=player.player_id,
            name=player.name,
            rating=player.rating,
            true_strength=player.true_strength,
            games=player.games,
            wins=player.wins,
            draws=player.draws,
            losses=player.losses,
        )
        for rank, player in enumerate(ranked, start=1)
    )
    mean_error = sum(
        abs(player.rating - player.true_strength) for player in players
    ) / len(players)
    return SimulationResult(
        parameters=parameters,
        players=snapshots,
        history={key: tuple(values) for key, values in history.items()},
        rating_error=mean_error,
    )

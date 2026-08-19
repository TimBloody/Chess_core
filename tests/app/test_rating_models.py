from dataclasses import replace

import pytest

from chess_core.app.rating import (
    EloParameters,
    expected_score,
    rating_gap_for_probability,
    simulate_league,
    update_pair,
)


def test_expected_score_is_symmetric_and_uses_standard_scale() -> None:
    assert expected_score(1500, 1500) == pytest.approx(0.5)
    assert expected_score(1900, 1500) == pytest.approx(10 / 11)
    assert expected_score(1700, 1500) + expected_score(1500, 1700) == pytest.approx(1)


def test_probability_gap_is_inverse_of_expected_score() -> None:
    for probability in (0.90, 0.95, 0.99, 0.999):
        gap = rating_gap_for_probability(probability)
        assert expected_score(gap, 0) == pytest.approx(probability)


def test_pair_update_rewards_upset_and_preserves_sum_without_floor() -> None:
    winner, loser = update_pair(1400, 1800, 1.0, k_a=24)
    assert winner > 1420
    assert loser < 1780
    assert winner + loser == pytest.approx(3200)


def test_simulation_is_reproducible_and_ranks_top_ten() -> None:
    parameters = EloParameters(player_count=30, rounds=25, seed=7)
    first = simulate_league(parameters)
    second = simulate_league(parameters)
    assert first == second
    assert len(first.players) == 30
    assert len(first.top_ten) == 10
    assert [player.rank for player in first.top_ten] == list(range(1, 11))
    assert all(
        first.players[index].rating >= first.players[index + 1].rating
        for index in range(len(first.players) - 1)
    )
    assert all(len(values) == parameters.rounds + 1 for values in first.history.values())


def test_more_rounds_produce_more_recorded_games() -> None:
    short = simulate_league(EloParameters(player_count=20, rounds=5, seed=11))
    long = simulate_league(EloParameters(player_count=20, rounds=15, seed=11))
    assert sum(player.games for player in long.players) > sum(
        player.games for player in short.players
    )


def test_changed_k_factor_changes_ratings() -> None:
    base = EloParameters(player_count=20, rounds=20, seed=3)
    low = simulate_league(replace(base, k_factor=8))
    high = simulate_league(replace(base, k_factor=48))
    assert [player.rating for player in low.players] != [
        player.rating for player in high.players
    ]


@pytest.mark.parametrize(
    "parameters",
    (
        EloParameters(player_count=1),
        EloParameters(k_factor=0),
        EloParameters(scale=0),
        EloParameters(draw_probability=1),
        EloParameters(certainty=1),
    ),
)
def test_invalid_parameters_are_rejected(parameters: EloParameters) -> None:
    with pytest.raises(ValueError):
        simulate_league(parameters)

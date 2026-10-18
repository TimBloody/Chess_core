"""Elo experiment math."""

from random import Random

from chess_core.app.experiments.elo import RatedPlayer, expected_score, round_robin, update_elo


def test_expected_score_is_symmetric() -> None:
    assert abs(expected_score(1600, 1600) - 0.5) < 1e-9
    high = expected_score(2000, 1600)
    low = expected_score(1600, 2000)
    assert abs(high + low - 1.0) < 1e-9
    assert high > 0.8


def test_update_elo_rewards_an_upset() -> None:
    expected = expected_score(1400, 1800)
    after_win = update_elo(1400, expected, 1.0, k=20)
    after_loss = update_elo(1400, expected, 0.0, k=20)
    assert after_win > 1400
    assert after_loss < 1400


def test_round_robin_is_deterministic_with_seed() -> None:
    players = [
        RatedPlayer("A", 1600),
        RatedPlayer("B", 1500),
        RatedPlayer("C", 1400),
    ]
    first, games = round_robin(players, k=20, rng=Random(1))
    second, again = round_robin(players, k=20, rng=Random(1))
    assert [player.rating for player in first] == [player.rating for player in second]
    assert [(game.white, game.black, game.result) for game in games] == [
        (game.white, game.black, game.result) for game in again
    ]
    assert len(games) == 3
    assert all(player.games == 2 for player in first)

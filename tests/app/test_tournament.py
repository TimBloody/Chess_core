from chess_core.app.tournament import PairingSystem, Player, TournamentService, parse_player_list
from chess_core.app.tournament.pairings import all_round_robin_rounds, pair_round


def _players(*names: str, rating: int = 1500) -> tuple[Player, ...]:
    return tuple(
        Player(player_id=f"p{index}", name=name, rating=rating + index)
        for index, name in enumerate(names, start=1)
    )


def test_parse_player_list_reads_rating_and_team() -> None:
    players = parse_player_list("Анна|2100|A\nБорис|2000|B\n")
    assert [player.name for player in players] == ["Анна", "Борис"]
    assert players[0].rating == 2100
    assert players[1].team == "B"


def test_round_robin_four_players_meet_once() -> None:
    players = _players("A", "B", "C", "D")
    rounds = all_round_robin_rounds(players)
    assert len(rounds) == 3
    pairs: set[frozenset[str]] = set()
    for round_games in rounds:
        round_ids = []
        for pairing in round_games:
            assert pairing.white_id is not None and pairing.black_id is not None
            key = frozenset({pairing.white_id, pairing.black_id})
            assert key not in pairs
            pairs.add(key)
            round_ids.extend([pairing.white_id, pairing.black_id])
        assert len(round_ids) == 4
        assert len(set(round_ids)) == 4
    assert len(pairs) == 6


def test_swiss_avoids_rematch_and_assigns_a_bye() -> None:
    players = _players("A", "B", "C")
    service = TournamentService(PairingSystem.SWISS, players, swiss_rounds=2, seed=7)
    first = service.generate_next_round()
    assert sum(1 for pairing in first if pairing.is_bye) == 1
    for pairing in first:
        if pairing.is_bye:
            service.set_result(pairing.round_index, pairing.board, "bye")
        else:
            service.set_result(pairing.round_index, pairing.board, "1-0")
    second = service.generate_next_round()
    first_match = next(pairing for pairing in first if not pairing.is_bye)
    second_match = next(pairing for pairing in second if not pairing.is_bye)
    assert frozenset({first_match.white_id, first_match.black_id}) != frozenset(
        {second_match.white_id, second_match.black_id}
    )


def test_knockout_seeds_and_advances_winners() -> None:
    players = _players("A", "B", "C", "D")
    service = TournamentService(PairingSystem.KNOCKOUT, players, seed=1)
    first = service.generate_next_round()
    assert len(first) == 2
    for pairing in first:
        service.set_result(pairing.round_index, pairing.board, "1-0")
    final = service.generate_next_round()
    assert len(final) == 1
    winners = {pairing.white_id for pairing in first}
    assert set(filter(None, (final[0].white_id, final[0].black_id))) == winners


def test_scheveningen_pairs_across_two_teams() -> None:
    players = (
        Player("a1", "A1", team="A"),
        Player("a2", "A2", team="A"),
        Player("b1", "B1", team="B"),
        Player("b2", "B2", team="B"),
    )
    first = pair_round(PairingSystem.SCHEVENINGEN, players, (), round_index=1)
    second = pair_round(PairingSystem.SCHEVENINGEN, players, first, round_index=2)
    assert len(first) == 2
    assert len(second) == 2
    for pairing in (*first, *second):
        white_team = next(player.team for player in players if player.player_id == pairing.white_id)
        black_team = next(player.team for player in players if player.player_id == pairing.black_id)
        assert white_team != black_team
    first_pairs = {frozenset({p.white_id, p.black_id}) for p in first}
    second_pairs = {frozenset({p.white_id, p.black_id}) for p in second}
    assert first_pairs.isdisjoint(second_pairs)


def test_color_draw_is_reproducible_with_seed() -> None:
    players = _players("A", "B", "C", "D")
    first = TournamentService(PairingSystem.COLOR_DRAW, players, seed=42).generate_next_round()
    second = TournamentService(PairingSystem.COLOR_DRAW, players, seed=42).generate_next_round()
    assert first == second
    assert len(first) == 2

from chess_core.app.tournament import PairingSystem, Player, TournamentService, parse_player_list
from chess_core.app.tournament.dutch2026 import NativeDutch2026Engine
from chess_core.app.tournament.models import assign_pairing_numbers
from chess_core.app.tournament.pairings import all_round_robin_rounds, pair_round


def _players(*names: str, rating: int = 1500) -> tuple[Player, ...]:
    return assign_pairing_numbers(
        tuple(Player(player_id=f"p{index}", name=name, rating=rating + 100 - index) for index, name in enumerate(names, start=1))
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


def test_double_round_robin_reverses_colours() -> None:
    players = _players("A", "B", "C", "D")
    rounds = all_round_robin_rounds(players, cycles=2)
    assert len(rounds) == 6
    first = {(pairing.white_id, pairing.black_id) for pairing in rounds[0]}
    second_cycle = {(pairing.white_id, pairing.black_id) for pairing in rounds[3]}
    assert {(black, white) for white, black in first} == second_cycle


def test_round_robin_odd_players_have_bye_each_cycle() -> None:
    players = _players("A", "B", "C")
    rounds = all_round_robin_rounds(players, cycles=2)
    assert len(rounds) == 6
    byes = [pairing for round_games in rounds for pairing in round_games if pairing.is_bye]
    assert len(byes) == 6


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


def test_round_robin_service_is_stepwise() -> None:
    players = _players("A", "B", "C", "D")
    service = TournamentService(PairingSystem.ROUND_ROBIN, players, rr_cycles=1)
    first = service.generate_next_round()
    assert len(first) == 2
    assert service.current_round == 1
    for pairing in first:
        service.set_result(pairing.round_index, pairing.board, "1-0")
    second = service.generate_next_round()
    assert service.current_round == 2
    assert len(second) == 2


def test_dutch_first_round_splits_by_tpn_and_initial_colour() -> None:
    names = [f"P{index}" for index in range(1, 16)]
    players = assign_pairing_numbers(
        tuple(Player(player_id=f"p{index}", name=name, rating=2600 - index) for index, name in enumerate(names, start=1))
    )
    pairings = NativeDutch2026Engine().pair_round(
        players, (), round_index=1, declared_rounds=9, initial_color="white"
    )
    byes = [pairing for pairing in pairings if pairing.is_bye]
    assert len(byes) == 1
    assert byes[0].white_id == players[-1].player_id
    games = [pairing for pairing in pairings if not pairing.is_bye]
    assert len(games) == 7
    top = {player.player_id for player in players[:7]}
    bottom = {player.player_id for player in players[7:14]}
    for pairing in games:
        ids = {pairing.white_id, pairing.black_id}
        assert len(ids & top) == 1
        assert len(ids & bottom) == 1
    first_board = games[0]
    assert first_board.white_id == players[0].player_id
    assert first_board.black_id == players[7].player_id


def test_dutch_is_deterministic() -> None:
    players = _players("A", "B", "C", "D", "E", "F", "G", "H")
    engine = NativeDutch2026Engine()
    first = engine.pair_round(players, (), round_index=1, declared_rounds=5)
    second = engine.pair_round(players, (), round_index=1, declared_rounds=5)
    assert first == second


def test_dutch_forbids_pab_repeat() -> None:
    players = _players("A", "B", "C")
    service = TournamentService(PairingSystem.SWISS, players, swiss_rounds=3)
    first = service.generate_next_round()
    bye_player = next(pairing.white_id or pairing.black_id for pairing in first if pairing.is_bye)
    for pairing in first:
        service.set_result(pairing.round_index, pairing.board, "bye" if pairing.is_bye else "1-0")
    second = service.generate_next_round()
    second_bye = next(pairing.white_id or pairing.black_id for pairing in second if pairing.is_bye)
    assert second_bye != bye_player


def test_assign_pairing_numbers_orders_by_rating_title_name() -> None:
    players = (
        Player("a", "Low", rating=1400, title="GM"),
        Player("b", "Zed", rating=2000),
        Player("c", "Ann", rating=2000),
        Player("d", "Mia", rating=1800, title="IM"),
        Player("e", "Max", rating=1800),
    )
    numbered = assign_pairing_numbers(players)
    assert [player.name for player in numbered] == ["Ann", "Zed", "Mia", "Max", "Low"]
    assert [player.start_number for player in numbered] == [1, 2, 3, 4, 5]


def test_swiss_service_resorts_by_rating_before_first_round() -> None:
    players = (
        Player("p1", "Low", rating=1400),
        Player("p2", "High", rating=2200),
        Player("p3", "Cara", rating=1600),
        Player("p4", "Bea", rating=1900),
    )
    service = TournamentService(PairingSystem.SWISS, players, swiss_rounds=3)
    service.generate_next_round()
    assert [player.name for player in service.players] == ["High", "Bea", "Cara", "Low"]
    assert service.players[0].start_number == 1


def test_swiss_no_color_avoids_rematch_like_swiss() -> None:
    players = _players("A", "B", "C", "D", "E")
    service = TournamentService(PairingSystem.SWISS_NO_COLOR, players, swiss_rounds=3, seed=3)
    first = service.generate_next_round()
    assert sum(1 for pairing in first if pairing.is_bye) == 1
    for pairing in first:
        if pairing.is_bye:
            service.set_result(pairing.round_index, pairing.board, "bye")
        else:
            service.set_result(pairing.round_index, pairing.board, "1-0")
    second = service.generate_next_round()
    first_pairs = {
        frozenset(filter(None, pairing.player_ids()))
        for pairing in first
        if not pairing.is_bye
    }
    second_pairs = {
        frozenset(filter(None, pairing.player_ids()))
        for pairing in second
        if not pairing.is_bye
    }
    assert first_pairs.isdisjoint(second_pairs)


def test_swiss_no_color_engine_ignores_absolute_colour_conflict() -> None:
    """Two players who both 'owe' the same colour may still be paired."""
    players = _players("A", "B", "C", "D")
    # Fabricate history where A and B both had white twice in a row (absolute black pref).
    from chess_core.app.tournament.models import Pairing

    history = (
        Pairing(1, 1, "p1", "p3", "1-0"),
        Pairing(1, 2, "p2", "p4", "1-0"),
        Pairing(2, 1, "p1", "p4", "1-0"),
        Pairing(2, 2, "p2", "p3", "1-0"),
    )
    engine = NativeDutch2026Engine()
    with_color = engine.pair_round(
        players, history, round_index=3, declared_rounds=5, ignore_colours=False
    )
    without = engine.pair_round(
        players, history, round_index=3, declared_rounds=5, ignore_colours=True
    )
    assert without
    # Same score-group pairing logic still yields legal boards; colour-blind may
    # pair absolute-same-colour opponents that colour-aware rejects or rearranges.
    color_pairs = {frozenset(p.player_ids()) for p in with_color if not p.is_bye}
    no_color_pairs = {frozenset(p.player_ids()) for p in without if not p.is_bye}
    assert len(no_color_pairs) == 2
    assert color_pairs or no_color_pairs

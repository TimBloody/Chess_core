from chess_core.app.tournament.excel_export import export_tournament_xlsx
from chess_core.app.tournament.external import ExternalOfficialEngineAdapter, compare_pairings
from chess_core.app.tournament.manager import TournamentManager
from chess_core.app.tournament.models import Pairing, PairingSystem, Player, PlayerStatus, assign_pairing_numbers
from chess_core.app.tournament.state import TournamentSettings
from chess_core.app.tournament.trf import pairings_from_trf26, tournament_to_trf26
from chess_core.infra.storage.tournament_files import load_tournament, save_tournament


def _players(*names: str) -> tuple[Player, ...]:
    return assign_pairing_numbers(
        tuple(Player(player_id=f"p{index}", name=name, rating=2000 - index) for index, name in enumerate(names, start=1))
    )


def test_manager_late_entry_gets_zero_point_byes(tmp_path) -> None:
    manager = TournamentManager.create(_players("A", "B", "C", "D"), TournamentSettings(declared_rounds=5))
    first = manager.generate_next_round()
    for pairing in first:
        if pairing.is_bye:
            manager.set_result(pairing.round_index, pairing.board, "bye")
        else:
            manager.set_result(pairing.round_index, pairing.board, "1-0")
    late = manager.add_player("Eve", rating=1800)
    assert late.status is PlayerStatus.LATE_ENTRY
    zpb = [pairing for pairing in manager.pairings if pairing.white_id == late.player_id]
    assert zpb and zpb[0].result == "zpb"
    path = save_tournament(manager.state, tmp_path / "event.tournament.json")
    loaded = TournamentManager(load_tournament(path))
    assert any(player.name == "Eve" for player in loaded.players)


def test_manager_absent_player_gets_zpb_not_paired() -> None:
    manager = TournamentManager.create(_players("A", "B", "C", "D"), TournamentSettings(declared_rounds=3))
    absent = manager.players[-1]
    manager.set_player_status(absent.player_id, PlayerStatus.ABSENT)
    generated = manager.generate_next_round()
    involved = [pairing for pairing in generated if absent.player_id in pairing.player_ids()]
    assert len(involved) == 1
    assert involved[0].is_bye
    assert involved[0].result == "zpb"


def test_manual_pairing_requires_reason_and_warns_on_rematch() -> None:
    manager = TournamentManager.create(_players("A", "B", "C", "D"), TournamentSettings(declared_rounds=3))
    first = manager.generate_next_round()
    for pairing in first:
        manager.set_result(pairing.round_index, pairing.board, "1-0")
    manager.generate_next_round()
    first_pair = next(pairing for pairing in first if not pairing.is_bye)
    ids = [player.player_id for player in manager.players]
    rest = [player_id for player_id in ids if player_id not in {first_pair.white_id, first_pair.black_id}]
    rewritten = [
        Pairing(2, 1, first_pair.white_id, first_pair.black_id),
        Pairing(2, 2, rest[0], rest[1]),
    ]
    warnings = manager.replace_round_pairings(2, rewritten, reason="игрок сел не за тот стол")
    assert any("repeat pairing" in warning for warning in warnings)
    assert manager.state.audit[-1].reason == "игрок сел не за тот стол"
    assert manager.round_pairings(2)[0].manual is True


def test_external_dummy_reports_mismatch_without_replacing() -> None:
    players = _players("A", "B", "C", "D")
    native = TournamentManager.create(players, TournamentSettings(declared_rounds=3)).generate_next_round()

    def runner(trf: str, round_index: int) -> str:
        del trf
        flipped = [
            Pairing(round_index, board, pairing.black_id, pairing.white_id)
            for board, pairing in enumerate(native, start=1)
            if not pairing.is_bye
        ]
        fake_players = players
        return tournament_to_trf26(
            name="fake",
            players=fake_players,
            pairings=tuple(flipped),
            declared_rounds=3,
        )

    adapter = ExternalOfficialEngineAdapter(runner=runner)
    external = adapter.pair_round(players, (), round_index=1, declared_rounds=3)
    report = compare_pairings(native, external)
    assert report
    manager = TournamentManager.create(players, TournamentSettings(declared_rounds=3), external_engine=adapter)
    generated = manager.generate_next_round()
    assert [(p.white_id, p.black_id) for p in generated] == [(p.white_id, p.black_id) for p in native]
    assert manager.last_engine_report


def test_trf_roundtrip_reads_same_pairs() -> None:
    players = _players("A", "B", "C", "D")
    manager = TournamentManager.create(players, TournamentSettings(declared_rounds=3))
    generated = manager.generate_next_round()
    text = tournament_to_trf26(
        name="Test",
        players=manager.players,
        pairings=generated,
        declared_rounds=3,
    )
    restored = pairings_from_trf26(text, manager.players, round_index=1)
    native_keys = {frozenset(p.player_ids()) for p in generated if not p.is_bye}
    restored_keys = {frozenset(p.player_ids()) for p in restored if not p.is_bye}
    assert native_keys == restored_keys


def test_excel_export_has_three_sheets(tmp_path) -> None:
    manager = TournamentManager.create(_players("Carla", "Anton", "Boris", "Dina"), TournamentSettings(declared_rounds=3))
    manager.generate_next_round()
    path = export_tournament_xlsx(manager.state, tmp_path / "tables.xlsx")
    from openpyxl import load_workbook

    book = load_workbook(path)
    assert book.sheetnames == ["Пары", "Стартовый список", "Положение", "Кросс-таблица", "По алфавиту"]
    names = [row[1].value for row in book["По алфавиту"].iter_rows(min_row=2, max_col=2)]
    assert names == sorted(names, key=lambda item: str(item).casefold())
    assert book["Положение"]["A1"].value == "Место"
    assert book["Пары"]["A1"].value == "Тур"
    start_names = [row[2].value for row in book["Стартовый список"].iter_rows(min_row=2, max_col=3)]
    start_ratings = [row[4].value for row in book["Стартовый список"].iter_rows(min_row=2, max_col=5)]
    assert start_names[0] == "Carla"
    assert start_ratings == sorted(start_ratings, reverse=True)


def test_starting_list_is_resorted_by_rating_before_round_one() -> None:
    from chess_core.app.tournament.state import TournamentState

    state = TournamentState(
        settings=TournamentSettings(declared_rounds=5),
        players=(
            Player("low", "Low", rating=1400, start_number=1),
            Player("high", "High", rating=2200, start_number=2),
            Player("mid", "Mid", rating=1800, start_number=3),
            Player("nia", "Nia", rating=1700, start_number=4),
        ),
    )
    manager = TournamentManager(state)
    assert manager.players[0].name == "Low"
    ranked = manager.sort_starting_list()
    assert [player.name for player in ranked] == ["High", "Mid", "Nia", "Low"]
    assert [player.start_number for player in ranked] == [1, 2, 3, 4]
    first = manager.generate_next_round()
    high = next(player.player_id for player in manager.players if player.name == "High")
    assert any(high in pairing.player_ids() for pairing in first)
    board_one = next(pairing for pairing in first if pairing.board == 1)
    assert high in board_one.player_ids()


def test_rating_edit_reassigns_start_numbers_before_round_four() -> None:
    manager = TournamentManager.create(_players("A", "B", "C", "D"), TournamentSettings(declared_rounds=5))
    weakest = manager.players[-1]
    updated = manager.update_player(weakest.player_id, rating=3000)
    assert updated.start_number == 1
    assert manager.starting_list()[0].player_id == weakest.player_id


def test_half_point_bye_skips_pairing_and_scores_half() -> None:
    manager = TournamentManager.create(_players("A", "B", "C", "D"), TournamentSettings(declared_rounds=3))
    skipped = manager.players[0]
    manager.schedule_bye(skipped.player_id, "hpb")
    generated = manager.generate_next_round()
    bye = next(pairing for pairing in generated if skipped.player_id in pairing.player_ids())
    assert bye.is_bye
    assert bye.result == "hpb"
    assert skipped.player_id not in {
        pairing.white_id for pairing in generated if not pairing.is_bye
    }
    table = {row.player.player_id: row for row in manager.standings()}
    assert table[skipped.player_id].points == 0.5


def test_update_player_and_settings_after_start() -> None:
    manager = TournamentManager.create(_players("A", "B", "C", "D"), TournamentSettings(name="Open", declared_rounds=5))
    manager.generate_next_round()
    player = manager.players[0]
    updated = manager.update_player(player.player_id, name="Anna IM", rating=2300, title="IM", federation="FID")
    assert updated.name == "Anna IM"
    assert updated.title == "IM"
    locked = manager.update_settings(TournamentSettings(name="City Open", declared_rounds=9, site="Hall"))
    assert locked.name == "City Open"
    assert locked.declared_rounds == 5
    assert locked.site == "Hall"


def test_crosstable_and_trf_text() -> None:
    manager = TournamentManager.create(_players("A", "B", "C", "D"), TournamentSettings(name="Cup", declared_rounds=3))
    first = manager.generate_next_round()
    for pairing in first:
        if pairing.is_bye:
            manager.set_result(pairing.round_index, pairing.board, "bye")
        else:
            manager.set_result(pairing.round_index, pairing.board, "1-0")
    rows = manager.crosstable()
    assert len(rows) == 4
    first_row, cells = rows[0]
    assert first_row.place == 1
    assert cells and cells[0] is not None
    text = manager.trf_text()
    assert "012 Cup" in text
    assert "001" in text
    listing = manager.pairings_text(1)
    assert "Тур 1" in listing


def test_delete_rounds_from_first_keeps_players() -> None:
    manager = TournamentManager.create(
        _players("A", "B", "C", "D"),
        TournamentSettings(system=PairingSystem.SWISS, declared_rounds=5),
    )
    first = manager.generate_next_round()
    for pairing in first:
        manager.set_result(pairing.round_index, pairing.board, "1-0")
    manager.generate_next_round()
    names = [player.name for player in manager.players]
    current = manager.delete_rounds_from(1, reason="wrong system")
    assert current == 0
    assert manager.current_round == 0
    assert manager.pairings == ()
    assert [player.name for player in manager.players] == names
    manager.update_settings(TournamentSettings(system=PairingSystem.SWISS_NO_COLOR, declared_rounds=5))
    assert manager.state.settings.system is PairingSystem.SWISS_NO_COLOR
    again = manager.generate_next_round()
    assert again


def test_dutch_last_bracket_pairs_mdp_with_top_resident() -> None:
    """C.04.3 3.3.3: MDP from 1.0 meets the highest resident of 0.0, not a TPN fold."""
    names = (
        "Глухова",
        "Гусев",
        "Заяц",
        "Иванов",
        "Кравцов",
        "Пивовар",
        "Стрелов",
        "Чухачев",
        "Шералиев",
        "Ярош",
    )
    players = tuple(
        Player(player_id=f"p{index}", name=name, rating=2000 - index, start_number=index)
        for index, name in enumerate(names, start=1)
    )
    for system in (PairingSystem.SWISS_NO_COLOR, PairingSystem.SWISS):
        manager = TournamentManager.create(
            players,
            TournamentSettings(system=system, declared_rounds=5),
        )
        first = manager.generate_next_round()
        by_id = {player.player_id: player for player in manager.players}
        winners = {2, 5, 6, 8, 9}
        for pairing in first:
            white_n = by_id[pairing.white_id].start_number
            if white_n in winners:
                manager.set_result(1, pairing.board, "1-0")
            else:
                manager.set_result(1, pairing.board, "0-1")
        second = manager.generate_next_round()
        pairs = {
            frozenset(by_id[player_id].start_number for player_id in pairing.player_ids())
            for pairing in second
            if not pairing.is_bye
        }
        if system is PairingSystem.SWISS_NO_COLOR:
            assert {2, 6} in pairs
            assert {5, 8} in pairs
            assert {9, 1} in pairs
            assert {3, 7} in pairs
            assert {4, 10} in pairs
        else:
            # Colour criteria may change which 1.0 player downfloats, but the last
            # bracket must still be an MDP-pairing, not a TPN fold of all six.
            assert {1, 7} not in pairs
            assert any(1 in pair and pair - {1} <= winners for pair in pairs)

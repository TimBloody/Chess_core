from chess_core.app.tournament.manager import TournamentManager
from chess_core.app.tournament.models import PairingSystem, Player, assign_pairing_numbers
from chess_core.app.tournament.state import TournamentSettings
from chess_core.app.tournament.trf import state_from_trf, tournament_to_trf26
from chess_core.app.tournament.tunx import state_from_tunx
from chess_core.infra.storage.tournament_files import load_tournament, save_trf, save_tournament


def _players(*names: str) -> tuple[Player, ...]:
    return assign_pairing_numbers(
        tuple(Player(player_id=f"p{index}", name=name, rating=2000 - index) for index, name in enumerate(names, start=1))
    )


def test_trf16_roundtrip_restores_players_and_results(tmp_path) -> None:
    manager = TournamentManager.create(
        _players("Anna", "Boris", "Carla", "Dina"),
        TournamentSettings(name="City Open", declared_rounds=5, site="Hall", arbiter="IA Test"),
    )
    first = manager.generate_next_round()
    for pairing in first:
        if pairing.is_bye:
            manager.set_result(pairing.round_index, pairing.board, "bye")
        else:
            manager.set_result(pairing.round_index, pairing.board, "1-0")
    path = save_trf(manager.state, tmp_path / "city.trf")
    loaded = TournamentManager(load_tournament(path))
    assert loaded.state.settings.name == "City Open"
    assert loaded.state.settings.site == "Hall"
    assert loaded.current_round == 1
    names = {player.name for player in loaded.players}
    assert names == {"Anna", "Boris", "Carla", "Dina"}
    by_start = {player.start_number: player for player in loaded.players}
    assert set(by_start) == {player.start_number for player in manager.players}

    def pair_keys(state) -> set[frozenset[int]]:
        names = state.player_map()
        keys: set[frozenset[int]] = set()
        for pairing in state.pairings:
            if pairing.round_index != 1 or pairing.is_bye:
                continue
            white = names[pairing.white_id or ""].start_number
            black = names[pairing.black_id or ""].start_number
            keys.add(frozenset({white, black}))
        return keys

    assert pair_keys(loaded.state) == pair_keys(manager.state)
    assert any(pairing.result == "1-0" for pairing in loaded.pairings)
    text = path.read_text(encoding="utf-8-sig")
    again = state_from_trf(text)
    assert again.settings.arbiter == "IA Test"


def test_json_save_still_roundtrips(tmp_path) -> None:
    manager = TournamentManager.create(_players("A", "B", "C", "D"), TournamentSettings(declared_rounds=3))
    manager.generate_next_round()
    path = save_tournament(manager.state, tmp_path / "event.tournament.json")
    loaded = load_tournament(path)
    assert loaded.settings.name == manager.state.settings.name
    assert len(loaded.players) == 4


def test_tunx_reader_loads_players_and_pairing() -> None:
    data = _minimal_tunx()
    state = state_from_tunx(data)
    assert state.settings.name == "Tunx Cup"
    assert state.settings.system is PairingSystem.SWISS
    assert [player.name for player in state.players] == ["Ivanov, Petr", "Petrov, Anna"]
    assert state.players[0].rating == 2100
    assert state.current_round == 1
    assert len(state.pairings) == 1
    assert state.pairings[0].result == "1-0"


def test_load_tournament_dispatches_tunx(tmp_path) -> None:
    path = tmp_path / "event.tunx"
    path.write_bytes(_minimal_tunx())
    state = load_tournament(path)
    assert state.settings.name == "Tunx Cup"


def test_tunx_keeps_unpaired_and_bye_records_in_later_rounds() -> None:
    data = _tunx_with_unpaired_overflow()
    state = state_from_tunx(data)
    by_round = {1: [], 2: []}
    for pairing in state.pairings:
        by_round[pairing.round_index].append(pairing)
    assert {(p.white_id, p.black_id) for p in by_round[1]} == {("tun-1", "tun-2"), ("tun-3", "tun-4")}
    second = {(p.white_id, p.black_id, p.result) for p in by_round[2]}
    assert ("tun-1", "tun-3", "1-0") in second
    assert ("tun-2", None, "zpb") in second
    assert ("tun-4", None, "zpb") in second
    text = tournament_to_trf26(
        name=state.settings.name,
        players=state.players,
        pairings=state.pairings,
        declared_rounds=2,
    )
    by_start = {}
    for line in text.splitlines():
        if line.startswith("001"):
            by_start[int(line[4:8])] = line[91:]
    assert "0000 - Z" in by_start[2]
    assert "0000 - Z" in by_start[4]
    assert not any(line.startswith("XXP ") and line.endswith(" 0") for line in text.splitlines())
    assert "XXP " not in text


def test_team_swiss_manager_extension_is_rejected(tmp_path) -> None:
    path = tmp_path / "teams.tumx"
    path.write_bytes(b"not a tunx")
    try:
        load_tournament(path)
    except ValueError as exc:
        assert "командные" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def _tunx_with_unpaired_overflow() -> bytes:
    """Round 2 has more records than (n+1)//2 because of bye + unpaired extras."""
    magic = bytes((0x93, 0xFF, 0x89, 0x44))
    header = magic + bytes(104)
    metadata = _utf16("Overflow Cup")
    config = bytearray(32)
    config[0:2] = (2).to_bytes(2, "little")
    config[0x0B] = 0
    config[0x11] = 2
    config[0x13:0x15] = (4).to_bytes(2, "little")
    config_section = bytes((0x95, 0xFF, 0x89, 0x44)) + bytes(config)
    players = b"".join(
        _tunx_player(name, "P", 2000 - index)
        for index, name in enumerate(("Anna", "Boris", "Carla", "Dina"), start=1)
    )
    player_section = bytes((0xA5, 0xFF, 0x89, 0x44)) + players
    records = [
        _tunx_pairing(1, 2, 1),
        _tunx_pairing(3, 4, 1),
        _tunx_pairing(1, 3, 1),
        _tunx_pairing(2, 0xFFFF, 9),
        _tunx_pairing(4, 0xFFFE, 3),
    ]
    pairing_section = bytes((0xB3, 0xFF, 0x89, 0x44)) + b"".join(records)
    trailer = bytes((0xD3, 0xFF, 0x89, 0x44)) + bytes(16)
    return header + metadata + config_section + player_section + pairing_section + trailer


def _tunx_pairing(white: int, black: int, code: int) -> bytes:
    record = bytearray(21)
    record[0:2] = white.to_bytes(2, "little")
    record[2:4] = black.to_bytes(2, "little")
    record[4:6] = code.to_bytes(2, "little")
    return bytes(record)


def _minimal_tunx() -> bytes:
    magic = bytes((0x93, 0xFF, 0x89, 0x44))
    header = magic + bytes(104)
    metadata = _utf16("Tunx Cup")
    config = bytearray(32)
    config[0:2] = (1).to_bytes(2, "little")
    config[0x0B] = 0
    config[0x11] = 1
    config[0x13:0x15] = (2).to_bytes(2, "little")
    config_section = bytes((0x95, 0xFF, 0x89, 0x44)) + bytes(config)
    players = _tunx_player("Ivanov", "Petr", 2100) + _tunx_player("Petrov", "Anna", 1900)
    player_section = bytes((0xA5, 0xFF, 0x89, 0x44)) + players
    pairing = bytearray(21)
    pairing[0:2] = (1).to_bytes(2, "little")
    pairing[2:4] = (2).to_bytes(2, "little")
    pairing[4:6] = (1).to_bytes(2, "little")
    pairing_section = bytes((0xB3, 0xFF, 0x89, 0x44)) + bytes(pairing)
    return header + metadata + config_section + player_section + pairing_section


def _tunx_player(surname: str, first: str, rating: int) -> bytes:
    strings = [_utf16(surname), _utf16(first)]
    strings.extend(_utf16("") for _ in range(28))
    numeric = bytearray(110)
    numeric[0x08:0x0A] = int(rating).to_bytes(2, "little")
    return b"".join(strings) + bytes(numeric)


def _utf16(text: str) -> bytes:
    encoded = text.encode("utf-16le")
    return (len(encoded) // 2).to_bytes(2, "little") + encoded

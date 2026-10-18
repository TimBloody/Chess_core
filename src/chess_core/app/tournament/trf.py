"""TRF16/TRF26 helpers: FIDE exchange, dummy engine, and Swiss-Manager import."""

from __future__ import annotations

from chess_core.app.tournament.models import (
    RESULT_BLACK,
    RESULT_BYE,
    RESULT_DRAW,
    RESULT_FORFEIT_BLACK,
    RESULT_FORFEIT_WHITE,
    RESULT_HPB,
    RESULT_WHITE,
    RESULT_ZPB,
    AuditEntry,
    Pairing,
    PairingSystem,
    Player,
    points_for,
    result_kind_for,
)
from chess_core.app.tournament.state import TournamentSettings, TournamentState

TRF_CODES = {
    "1-0": ("1", "0"),
    "0-1": ("0", "1"),
    "1/2-1/2": ("=", "="),
    "bye": ("+", "-"),
    "1-0F": ("+", "-"),
    "0-1F": ("-", "+"),
    "0-0": ("-", "-"),
    "zpb": ("0", "0"),
    "hpb": ("H", "H"),
}

_CODE_FROM_WHITE = {
    "1": RESULT_WHITE,
    "W": RESULT_WHITE,
    "0": RESULT_BLACK,
    "L": RESULT_BLACK,
    "=": RESULT_DRAW,
    "D": RESULT_DRAW,
    "+": RESULT_FORFEIT_WHITE,
    "-": RESULT_FORFEIT_BLACK,
}

_BYE_CODES = {
    "F": RESULT_BYE,
    "+": RESULT_BYE,
    "H": RESULT_HPB,
    "D": RESULT_HPB,
    "Z": RESULT_ZPB,
    "U": RESULT_ZPB,
    "0": RESULT_ZPB,
    "-": RESULT_ZPB,
}


def looks_like_trf(text: str) -> bool:
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        return line.startswith(("012", "001", "022", "092", "XXR", "XXC", "093"))
    return False


def tournament_to_trf26(
    *,
    name: str,
    players: tuple[Player, ...],
    pairings: tuple[Pairing, ...],
    declared_rounds: int,
    site: str = "",
    arbiter: str = "",
    time_control: str = "",
    system: PairingSystem | None = None,
) -> str:
    rounds = max(declared_rounds, 1)
    by_round: dict[int, list[Pairing]] = {}
    for pairing in pairings:
        by_round.setdefault(pairing.round_index, []).append(pairing)

    points_by_id: dict[str, float] = {player.player_id: 0.0 for player in players}
    for pairing in pairings:
        for player_id in pairing.player_ids():
            score = points_for(pairing, player_id)
            if score is not None:
                points_by_id[player_id] = points_by_id.get(player_id, 0.0) + score
    ranked = sorted(players, key=lambda item: (-points_by_id.get(item.player_id, 0.0), item.start_number or 0))
    rank_by_id: dict[str, int] = {}
    place = 1
    for index, player in enumerate(ranked):
        if index > 0:
            previous = ranked[index - 1]
            if points_by_id.get(player.player_id, 0.0) < points_by_id.get(previous.player_id, 0.0):
                place = index + 1
        rank_by_id[player.player_id] = place

    kind = "SWISS"
    if system is PairingSystem.ROUND_ROBIN:
        kind = "ROUND ROBIN"

    lines = [
        f"012 {name}",
        f"022 {site}".rstrip(),
        f"092 {kind}",
        f"102 {arbiter}".rstrip(),
        f"122 {time_control}".rstrip(),
        f"XXR {rounds}",
        "XXC white1",
        f"093 {rounds}",
    ]
    paired_rounds = set(by_round)
    for player in sorted(players, key=lambda item: item.start_number or 0):
        tpn = player.start_number or 0
        results: list[str] = []
        for round_index in range(1, rounds + 1):
            found = None
            for pairing in by_round.get(round_index, ()):
                if player.player_id in pairing.player_ids():
                    found = pairing
                    break
            results.append(
                _result_block(
                    player,
                    found,
                    players,
                    missing_code="U" if round_index in paired_rounds else "0",
                )
            )
        points = points_by_id.get(player.player_id, 0.0)
        rank = rank_by_id.get(player.player_id, tpn)
        lines.append(_format_001(player, points, rank, "".join(results)))
    return "\r\n".join(lines) + "\r\n"


def state_from_trf(text: str) -> TournamentState:
    header = _parse_header(text)
    parsed: list[_TrfPlayer] = []
    for raw in text.splitlines():
        if raw.startswith("001"):
            parsed.append(_parse_001(raw, header.rounds))
    if not parsed:
        raise ValueError("в TRF нет строк игроков (001)")
    if header.rounds == 0:
        header.rounds = max((len(item.results) for item in parsed), default=0)
    players = tuple(
        Player(
            player_id=f"trf-{item.start_number}",
            name=item.name,
            rating=item.rating,
            title=item.title,
            federation=item.federation,
            start_number=item.start_number,
        )
        for item in parsed
    )
    by_tpn = {player.start_number: player for player in players}
    pairings = _pairings_from_results(parsed, by_tpn)
    current_round = max((item.round_index for item in pairings), default=0)
    system = PairingSystem.SWISS
    kind = header.kind.lower()
    if "round" in kind or "berger" in kind or kind in {"rr", "round robin"}:
        system = PairingSystem.ROUND_ROBIN
    return TournamentState(
        settings=TournamentSettings(
            name=header.name or "Tournament",
            system=system,
            declared_rounds=max(header.rounds, current_round, 1),
            site=header.site,
            arbiter=header.arbiter,
            time_control=header.time_control,
        ),
        players=players,
        pairings=tuple(pairings),
        current_round=current_round,
        audit=(AuditEntry("import", "TRF16", detail=header.name),),
    )


def pairings_from_trf26(text: str, players: tuple[Player, ...], *, round_index: int) -> tuple[Pairing, ...]:
    """Read one round of pairs from a TRF-like dump produced by a dummy engine."""
    by_tpn = {player.start_number: player for player in players}
    xxp: list[Pairing] = []
    for line in text.splitlines():
        if not line.startswith("XXP "):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            rnd, board, white_tpn, black_tpn = (int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))
        except ValueError:
            continue
        if rnd != round_index:
            continue
        white = by_tpn.get(white_tpn)
        black = by_tpn.get(black_tpn)
        if white is None and black is None:
            continue
        result = "bye" if white is None or black is None else None
        xxp.append(
            Pairing(
                round_index,
                board,
                None if white is None else white.player_id,
                None if black is None else black.player_id,
                result,
            )
        )
    if xxp:
        return tuple(sorted(xxp, key=lambda item: item.board))
    return _pairings_from_player_lines(text, by_tpn, round_index)


def _result_block(
    player: Player,
    found: Pairing | None,
    players: tuple[Player, ...],
    *,
    missing_code: str = "0",
) -> str:
    if found is None:
        return _game_field(0, "-", missing_code)
    if found.is_bye:
        code = "F"
        if found.result == "zpb":
            code = "Z"
        elif found.result == "hpb":
            code = "H"
        elif found.result == "bye":
            code = "F"
        return _game_field(0, "-", code)
    opponent = found.black_id if player.player_id == found.white_id else found.white_id
    opp = next((item for item in players if item.player_id == opponent), None)
    opp_tpn = opp.start_number if opp is not None else 0
    colour = "w" if player.player_id == found.white_id else "b"
    if found.result:
        white_code, black_code = TRF_CODES.get(found.result, ("*", "*"))
        code = white_code if colour == "w" else black_code
    else:
        code = "*"
    return _game_field(opp_tpn, colour, code)


def _game_field(opponent: int, colour: str, code: str) -> str:
    return f"{opponent:04d} {colour} {code}".ljust(10)


def _format_001(player: Player, points: float, rank: int, results: str) -> str:
    line = [" "] * (91 + len(results))
    tpn = player.start_number or 0
    _write(line, 0, "001")
    _write(line, 4, f"{tpn:4d}")
    _write(line, 10, (player.title or "")[:3].rjust(3))
    _write(line, 14, (player.name or "")[:33].ljust(33))
    _write(line, 48, f"{player.rating:4d}")
    _write(line, 53, (player.federation or "")[:3].rjust(3))
    _write(line, 80, f"{points:4.1f}")
    _write(line, 85, f"{rank:4d}")
    _write(line, 91, results)
    return "".join(line)


def _write(line: list[str], start: int, value: str) -> None:
    for offset, char in enumerate(value):
        index = start + offset
        if index >= len(line):
            line.extend([" "] * (index - len(line) + 1))
        line[index] = char


class _TrfHeader:
    def __init__(self) -> None:
        self.name = ""
        self.site = ""
        self.arbiter = ""
        self.time_control = ""
        self.kind = ""
        self.rounds = 0


class _TrfPlayer:
    def __init__(self, start_number: int, name: str, rating: int, title: str, federation: str) -> None:
        self.start_number = start_number
        self.name = name
        self.rating = rating
        self.title = title
        self.federation = federation
        self.results: list[tuple[int, str, str]] = []


def _parse_header(text: str) -> _TrfHeader:
    header = _TrfHeader()
    for raw in text.splitlines():
        code = raw[:3]
        value = raw[4:].strip() if len(raw) > 4 else ""
        if code == "012":
            header.name = value
        elif code == "022":
            header.site = value
        elif code == "092":
            header.kind = value
        elif code == "102":
            header.arbiter = value
        elif code == "122":
            header.time_control = value
        elif code in {"XXR", "093"}:
            try:
                header.rounds = int(value.split()[0])
            except (ValueError, IndexError):
                continue
    return header


def _parse_001(line: str, declared_rounds: int) -> _TrfPlayer:
    padded = line.ljust(91)
    try:
        start_number = int(padded[4:8].strip() or "0")
    except ValueError:
        start_number = 0
    name = padded[14:47].strip()
    title = padded[10:13].strip()
    try:
        rating = int(padded[48:52].strip() or "0")
    except ValueError:
        rating = 0
    federation = padded[53:56].strip()
    if not name:
        parts = line.split()
        start_number = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else start_number
        name = " ".join(parts[2:5]) or f"Player {start_number}"
    player = _TrfPlayer(start_number, name, rating, title, federation)
    player.results = _parse_result_fields(line, declared_rounds)
    return player


def _parse_result_fields(line: str, declared_rounds: int) -> list[tuple[int, str, str]]:
    rest = line[91:] if len(line) > 91 else ""
    results: list[tuple[int, str, str]] = []
    if rest.strip():
        chunks = [rest[index : index + 10] for index in range(0, len(rest), 10)]
        if declared_rounds:
            chunks = chunks[:declared_rounds]
        for chunk in chunks:
            field = chunk.ljust(10)
            try:
                opponent = int(field[0:4].replace(" ", "") or "0")
            except ValueError:
                opponent = 0
            colour = field[5:6].strip() or "-"
            code = field[7:8].strip() or "0"
            results.append((opponent, colour, code))
        return results
    return _parse_results_whitespace(line, declared_rounds)


def _parse_results_whitespace(line: str, declared_rounds: int) -> list[tuple[int, str, str]]:
    parts = line.split()
    start = 0
    for index, token in enumerate(parts):
        if token.isdigit() or token.startswith("000"):
            if index >= 5:
                start = index
                break
    tokens = parts[start:]
    results: list[tuple[int, str, str]] = []
    index = 0
    while index + 2 < len(tokens):
        if declared_rounds and len(results) >= declared_rounds:
            break
        try:
            opponent = int(tokens[index])
        except ValueError:
            index += 1
            continue
        colour = tokens[index + 1]
        code = tokens[index + 2]
        results.append((opponent, colour, code))
        index += 3
    return results


def _pairings_from_results(parsed: list[_TrfPlayer], by_tpn: dict[int, Player]) -> list[Pairing]:
    seen: set[tuple[int, frozenset[str]]] = set()
    boards: dict[int, int] = {}
    pairings: list[Pairing] = []
    for player in parsed:
        source = by_tpn.get(player.start_number)
        if source is None:
            continue
        for round_index, (opponent, colour, code) in enumerate(player.results, start=1):
            if opponent == 0 and colour in {"-", ""} and code in {"0", "*", ""}:
                continue
            if opponent == 0:
                key = (round_index, frozenset({source.player_id}))
                if key in seen:
                    continue
                seen.add(key)
                result = _BYE_CODES.get(code.upper(), RESULT_ZPB)
                boards[round_index] = boards.get(round_index, 0) + 1
                pairings.append(
                    Pairing(
                        round_index,
                        boards[round_index],
                        source.player_id,
                        None,
                        result,
                        result_kind=result_kind_for(result),
                    )
                )
                continue
            if colour.lower().startswith("b"):
                continue
            other = by_tpn.get(opponent)
            if other is None:
                continue
            key = (round_index, frozenset({source.player_id, other.player_id}))
            if key in seen:
                continue
            seen.add(key)
            if colour.lower().startswith("w") or colour == "-":
                white_id, black_id = source.player_id, other.player_id
            else:
                white_id, black_id = other.player_id, source.player_id
            result = _CODE_FROM_WHITE.get(code.upper() if code != "=" else "=", None)
            if code == "*":
                result = None
            boards[round_index] = boards.get(round_index, 0) + 1
            pairings.append(
                Pairing(
                    round_index,
                    boards[round_index],
                    white_id,
                    black_id,
                    result,
                    result_kind=result_kind_for(result) if result else None,
                )
            )
    pairings.sort(key=lambda item: (item.round_index, item.board))
    return pairings


def _pairings_from_player_lines(text: str, by_tpn: dict[int, Player], round_index: int) -> tuple[Pairing, ...]:
    seen: set[frozenset[str]] = set()
    boards: list[Pairing] = []
    board = 1
    for line in text.splitlines():
        if not line.startswith("001"):
            continue
        parsed = _parse_001(line, 0)
        player = by_tpn.get(parsed.start_number)
        if player is None:
            continue
        if round_index > len(parsed.results):
            continue
        opp_raw, colour, _code = parsed.results[round_index - 1]
        if opp_raw == 0:
            key = frozenset({player.player_id})
            if key in seen:
                continue
            seen.add(key)
            boards.append(Pairing(round_index, board, player.player_id, None, "bye"))
            board += 1
            continue
        opponent = by_tpn.get(opp_raw)
        if opponent is None:
            continue
        key = frozenset({player.player_id, opponent.player_id})
        if key in seen:
            continue
        seen.add(key)
        if colour.lower().startswith("w"):
            white_id, black_id = player.player_id, opponent.player_id
        else:
            white_id, black_id = opponent.player_id, player.player_id
        boards.append(Pairing(round_index, board, white_id, black_id))
        board += 1
    return tuple(boards)

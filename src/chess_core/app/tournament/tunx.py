"""Best-effort reader for Swiss-Manager TUNX/TURX files.

The format is proprietary (license hash in the header). This module only
parses the community-documented layout used by Swiss-Manager 9+ ``.TUNx`` /
``.TURx`` files. It does not write a file Swiss-Manager will treat as native.
"""

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
    result_kind_for,
)
from chess_core.app.tournament.state import TournamentSettings, TournamentState

TUNX_MAGIC = bytes((0x93, 0xFF, 0x89, 0x44))
_CONFIG_MARKER = bytes((0x95, 0xFF, 0x89, 0x44))
_PLAYER_MARKER = bytes((0xA5, 0xFF, 0x89, 0x44))
_PAIRINGS_MARKER = bytes((0xB3, 0xFF, 0x89, 0x44))
_HEADER_SIZE = 0x6C
_PLAYER_STRING_COUNT = 30
_PLAYER_NUMERIC_BLOCK = 110
_PAIRING_RECORD_SIZE = 21
_BYE_PLAYER = 0xFFFE
_UNPAIRED_PLAYER = 0xFFFF
_SECTION_END_MARKERS = (
    bytes((0xD3, 0xFF, 0x89, 0x44)),
    bytes((0xE3, 0xFF, 0x89, 0x44)),
)

_RESULT_WHITE_WINS = 1
_RESULT_DRAW = 2
_RESULT_BLACK_WINS = 3
_RESULT_WHITE_FORFEIT = 4
_RESULT_BLACK_FORFEIT = 5
_RESULT_UNPLAYED = 9

_STR_SURNAME = 0
_STR_FIRST_NAME = 1
_STR_TITLE = 4
_STR_CLUB = 9
_STR_FEDERATION = 10

_META_NAME = 0
_META_ARBITER = 3
_META_VENUE = 5
_META_CITY = 10
_META_TIME_CONTROL = 14


def is_tunx(data: bytes) -> bool:
    return len(data) >= _HEADER_SIZE and data[:4] == TUNX_MAGIC


def state_from_tunx(data: bytes) -> TournamentState:
    if not is_tunx(data):
        raise ValueError(
            "это не файл Swiss-Manager TUNX/TURX. "
            "Старый .TUN без сигнатуры не читается — сохраните турнир как .TUNX "
            "или экспортируйте TRF16 в Swiss-Manager."
        )
    config_at = _find_marker(data, _CONFIG_MARKER)
    player_at = _find_marker(data, _PLAYER_MARKER)
    pairings_at = _find_marker(data, _PAIRINGS_MARKER)
    if min(config_at, player_at, pairings_at) < 0 or not (config_at < player_at < pairings_at):
        raise ValueError("файл Swiss-Manager повреждён или это командный/неподдерживаемый вариант")

    metadata = _read_strings(data[_HEADER_SIZE:config_at])
    config = data[config_at + 4 : player_at]
    if len(config) < 0x15:
        raise ValueError("в файле Swiss-Manager нет блока настроек")

    total_rounds = int.from_bytes(config[0x00:0x02], "little")
    tournament_type = config[0x0B] if len(config) > 0x0B else 0
    current_round = config[0x11] if len(config) > 0x11 else 0
    player_count = int.from_bytes(config[0x13:0x15], "little")
    if tournament_type == 2:
        raise ValueError("командные турниры Swiss-Manager (.TUMx/.TUTx) пока не поддерживаются")
    if player_count == 0:
        raise ValueError("в файле Swiss-Manager нет игроков")

    players, start_ids = _read_players(data[player_at + 4 : pairings_at], player_count)
    pairing_end = _section_end(data, pairings_at + 4)
    pairings = _read_pairings(
        data[pairings_at + 4 : pairing_end],
        start_ids,
        total_rounds=max(total_rounds, 1),
    )
    paired_rounds = {item.round_index for item in pairings}
    resolved_round = max(paired_rounds) if paired_rounds else 0
    if current_round:
        resolved_round = max(resolved_round, int(current_round))

    name = _meta(metadata, _META_NAME) or "Tournament"
    site = _meta(metadata, _META_CITY) or _meta(metadata, _META_VENUE)
    system = PairingSystem.ROUND_ROBIN if tournament_type == 1 else PairingSystem.SWISS
    return TournamentState(
        settings=TournamentSettings(
            name=name,
            system=system,
            declared_rounds=max(total_rounds, resolved_round, 1),
            site=site,
            arbiter=_meta(metadata, _META_ARBITER),
            time_control=_meta(metadata, _META_TIME_CONTROL),
        ),
        players=tuple(players),
        pairings=tuple(pairings),
        current_round=resolved_round,
        audit=(AuditEntry("import", "Swiss-Manager TUNX", detail=name),),
    )


def _read_players(section: bytes, player_count: int) -> tuple[list[Player], dict[int, str]]:
    reader = _BinaryReader(section)
    players: list[Player] = []
    start_ids: dict[int, str] = {}
    for index in range(player_count):
        strings = [reader.read_string() for _ in range(_PLAYER_STRING_COUNT)]
        numeric = reader.read_bytes(_PLAYER_NUMERIC_BLOCK)
        start_number = index + 1
        player_id = f"tun-{start_number}"
        surname = strings[_STR_SURNAME].strip() if len(strings) > _STR_SURNAME else ""
        first = strings[_STR_FIRST_NAME].strip() if len(strings) > _STR_FIRST_NAME else ""
        name = f"{surname}, {first}" if surname and first else (surname or first or f"Player {start_number}")
        title = strings[_STR_TITLE].strip() if len(strings) > _STR_TITLE else ""
        club = strings[_STR_CLUB].strip() if len(strings) > _STR_CLUB else ""
        federation = strings[_STR_FEDERATION].strip() if len(strings) > _STR_FEDERATION else ""
        fide_rating = int.from_bytes(numeric[0x08:0x0A], "little") if len(numeric) >= 0x0A else 0
        national = int.from_bytes(numeric[0x0A:0x0C], "little") if len(numeric) >= 0x0C else 0
        rating = fide_rating or national
        players.append(
            Player(
                player_id=player_id,
                name=name,
                rating=rating,
                team=club or None,
                title=title,
                federation=federation,
                start_number=start_number,
            )
        )
        start_ids[start_number] = player_id
    return players, start_ids


def _section_end(data: bytes, start: int) -> int:
    end = len(data)
    for marker in _SECTION_END_MARKERS:
        at = data.find(marker, start)
        if at >= 0:
            end = min(end, at)
    return end


def _read_pairings(
    section: bytes,
    start_ids: dict[int, str],
    *,
    total_rounds: int,
) -> list[Pairing]:
    parsed: list[tuple[str, str | None, str | None]] = []
    record_count = len(section) // _PAIRING_RECORD_SIZE
    for record_index in range(record_count):
        offset = record_index * _PAIRING_RECORD_SIZE
        white_no = int.from_bytes(section[offset : offset + 2], "little")
        black_no = int.from_bytes(section[offset + 2 : offset + 4], "little")
        code = int.from_bytes(section[offset + 4 : offset + 6], "little")
        if white_no == 0:
            continue
        white_id = start_ids.get(white_no)
        if white_id is None:
            continue
        is_bye = black_no in {0, _BYE_PLAYER, _UNPAIRED_PLAYER}
        black_id = None if is_bye else start_ids.get(black_no)
        if not is_bye and black_id is None:
            continue
        parsed.append((white_id, black_id, _result_from_code(code, bye=is_bye)))
    return _assign_rounds(parsed, total_rounds=total_rounds)


def _assign_rounds(
    parsed: list[tuple[str, str | None, str | None]],
    *,
    total_rounds: int,
) -> list[Pairing]:
    """Swiss-Manager stores every board plus unpaired/bye extras; rounds are not padded."""
    boards: list[Pairing] = []
    round_index = 1
    seen: set[str] = set()
    board = 1
    for white_id, black_id, result in parsed:
        involved = {white_id}
        if black_id is not None:
            involved.add(black_id)
        if seen and involved & seen:
            round_index += 1
            if round_index > total_rounds:
                break
            seen = set()
            board = 1
        seen.update(involved)
        boards.append(
            Pairing(
                round_index,
                board,
                white_id,
                black_id,
                result,
                result_kind=result_kind_for(result) if result else None,
            )
        )
        board += 1
    return boards


def _result_from_code(code: int, *, bye: bool) -> str | None:
    if bye:
        if code in {_RESULT_WHITE_WINS, _RESULT_WHITE_FORFEIT}:
            return RESULT_BYE
        if code == _RESULT_DRAW:
            return RESULT_HPB
        if code in {0, _RESULT_BLACK_WINS, _RESULT_BLACK_FORFEIT, _RESULT_UNPLAYED}:
            return RESULT_ZPB
        return RESULT_BYE
    if code == _RESULT_WHITE_WINS:
        return RESULT_WHITE
    if code == _RESULT_DRAW:
        return RESULT_DRAW
    if code == _RESULT_BLACK_WINS:
        return RESULT_BLACK
    if code == _RESULT_WHITE_FORFEIT:
        return RESULT_FORFEIT_WHITE
    if code == _RESULT_BLACK_FORFEIT:
        return RESULT_FORFEIT_BLACK
    if code in {0, _RESULT_UNPLAYED}:
        return None
    return None


def _find_marker(data: bytes, marker: bytes) -> int:
    return data.find(marker)


def _read_strings(block: bytes) -> list[str]:
    reader = _BinaryReader(block)
    values: list[str] = []
    while reader.remaining >= 2:
        values.append(reader.read_string())
    return values


def _meta(values: list[str], index: int) -> str:
    if index >= len(values):
        return ""
    return values[index].strip()


class _BinaryReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.offset

    def read_bytes(self, length: int) -> bytes:
        take = min(max(length, 0), max(self.remaining, 0))
        chunk = self.data[self.offset : self.offset + take]
        self.offset += take
        if take < length:
            chunk = chunk + bytes(length - take)
        return chunk

    def read_string(self) -> str:
        if self.remaining < 2:
            return ""
        count = int.from_bytes(self.data[self.offset : self.offset + 2], "little")
        self.offset += 2
        count = min(max(count, 0), self.remaining // 2)
        raw = self.read_bytes(count * 2)
        return raw.decode("utf-16le", errors="replace").rstrip("\x00")

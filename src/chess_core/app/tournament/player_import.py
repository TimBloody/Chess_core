"""Player list import from CSV text and published Google Sheets URLs."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from chess_core.app.tournament.models import Player, parse_player_list

HEADER_ALIASES = {
    "name": "name",
    "player": "name",
    "имя": "name",
    "фио": "name",
    "фамилия": "name",
    "игрок": "name",
    "участник": "name",
    "rating": "rating",
    "elo": "rating",
    "рейтинг": "rating",
    "team": "team",
    "club": "team",
    "команда": "team",
    "клуб": "team",
    "title": "title",
    "звание": "title",
    "fed": "federation",
    "federation": "federation",
    "федерация": "federation",
    "id": "player_id",
    "fide": "player_id",
}

GOOGLE_HOSTS = {"docs.google.com", "sheets.google.com"}
MAX_DOWNLOAD_BYTES = 2_000_000


@dataclass(frozen=True, slots=True)
class ImportReport:
    players: tuple[Player, ...]
    errors: tuple[str, ...]
    duplicates: tuple[str, ...]


def parse_players_csv(text: str) -> ImportReport:
    sample = text.lstrip("\ufeff")
    if not sample.strip():
        return ImportReport((), ("empty player list",), ())
    try:
        dialect = csv.Sniffer().sniff(sample[:1024], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    stream = io.StringIO(sample)
    reader = csv.reader(stream, dialect)
    rows = list(reader)
    if not rows:
        return ImportReport((), ("empty player list",), ())
    return parse_player_rows(rows)


def parse_player_rows(rows: list[list[str]], *, id_prefix: str = "csv") -> ImportReport:
    if not rows:
        return ImportReport((), ("empty player list",), ())
    header = [normalize_header(cell) for cell in rows[0]]
    mapped = [HEADER_ALIASES.get(cell, "") for cell in header]
    if "name" not in mapped:
        sample = "\n".join("|".join(cell.strip() for cell in row if cell.strip()) for row in rows)
        return _dedupe(parse_player_list(sample), ())
    name_idx = mapped.index("name")
    rating_idx = mapped.index("rating") if "rating" in mapped else None
    team_idx = mapped.index("team") if "team" in mapped else None
    title_idx = mapped.index("title") if "title" in mapped else None
    fed_idx = mapped.index("federation") if "federation" in mapped else None
    id_idx = mapped.index("player_id") if "player_id" in mapped else None
    players: list[Player] = []
    errors: list[str] = []
    for line_no, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        try:
            name = row[name_idx].strip() if name_idx < len(row) else ""
            if not name:
                raise ValueError("name is required")
            rating_raw = row[rating_idx].strip() if rating_idx is not None and rating_idx < len(row) else ""
            rating = int(float(rating_raw)) if rating_raw else 0
            team = row[team_idx].strip() if team_idx is not None and team_idx < len(row) and row[team_idx].strip() else None
            title = row[title_idx].strip() if title_idx is not None and title_idx < len(row) else ""
            federation = row[fed_idx].strip() if fed_idx is not None and fed_idx < len(row) else ""
            player_id = (
                row[id_idx].strip()
                if id_idx is not None and id_idx < len(row) and row[id_idx].strip()
                else f"{id_prefix}{line_no}"
            )
            players.append(
                Player(
                    player_id=player_id,
                    name=name,
                    rating=rating,
                    team=team,
                    title=title,
                    federation=federation,
                )
            )
        except (ValueError, IndexError) as exc:
            errors.append(f"line {line_no}: {exc}")
    return _dedupe(tuple(players), tuple(errors))


def import_players_from_xlsx(path: str) -> ImportReport:
    return import_players_from_excel(path)


def import_players_from_excel(path: str) -> ImportReport:
    suffix = Path(path).suffix.lower()
    if suffix == ".xls":
        sheets = _xls_sheets(path)
        prefix = "xls"
    elif suffix in {".xlsx", ".xlsm"}:
        sheets = _xlsx_sheets(path)
        prefix = "xlsx"
    else:
        try:
            sheets = _xlsx_sheets(path)
            prefix = "xlsx"
        except Exception:
            sheets = _xls_sheets(path)
            prefix = "xls"
    return _report_from_sheets(sheets, prefix)


def _report_from_sheets(sheets: list[list[list[str]]], prefix: str) -> ImportReport:
    ranked = sorted(sheets, key=_sheet_name_score, reverse=True)
    last_empty = ImportReport((), ("empty player list",), ())
    for rows in ranked:
        if not rows:
            continue
        report = parse_player_rows(rows, id_prefix=prefix)
        if report.players:
            return report
        last_empty = report
    return last_empty


def _xlsx_sheets(path: str) -> list[list[list[str]]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("Для импорта Excel установите пакет openpyxl.") from exc
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        return [_sheet_rows(sheet) for sheet in workbook.worksheets]
    finally:
        workbook.close()


def _xls_sheets(path: str) -> list[list[list[str]]]:
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("Для импорта .xls установите пакет xlrd.") from exc
    try:
        book = xlrd.open_workbook(path)
    except Exception as exc:
        raise ValueError(f"не удалось прочитать .xls: {exc}") from exc
    sheets: list[list[list[str]]] = []
    for sheet in book.sheets():
        rows: list[list[str]] = []
        for row_index in range(sheet.nrows):
            cells = [_cell_text(sheet.cell_value(row_index, column)) for column in range(sheet.ncols)]
            if any(cells):
                rows.append(cells)
        sheets.append(rows)
    return sheets


def _sheet_rows(sheet) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in sheet.iter_rows(values_only=True):
        cells = [_cell_text(value) for value in row]
        if any(cells):
            rows.append(cells)
    return rows


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _sheet_name_score(rows: list[list[str]]) -> int:
    if not rows:
        return 0
    mapped = [HEADER_ALIASES.get(normalize_header(cell), "") for cell in rows[0]]
    score = 0
    if "name" in mapped:
        score += 8
    if "rating" in mapped:
        score += 2
    if "team" in mapped:
        score += 1
    return score


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-zа-яё0-9]+", "", (value or "").strip().casefold())


def google_sheet_csv_url(url: str) -> str:
    raw = url.strip()
    if not raw:
        raise ValueError("Google Sheets URL is empty")
    parsed = urlparse(raw)
    if "export" in parsed.path and "format=csv" in raw:
        return raw
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", raw)
    if parsed.hostname not in GOOGLE_HOSTS or match is None:
        raise ValueError("not a public Google Sheets URL")
    sheet_id = match.group(1)
    gid = "0"
    query = parse_qs(parsed.query)
    if "gid" in query:
        gid = query["gid"][0]
    fragment = parsed.fragment or ""
    frag_match = re.search(r"gid=([0-9]+)", fragment)
    if frag_match:
        gid = frag_match.group(1)
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def fetch_published_sheet_csv(
    url: str,
    *,
    opener=None,
    timeout: float = 10.0,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> str:
    csv_url = google_sheet_csv_url(url)
    request = Request(csv_url, headers={"User-Agent": "chess-core-tournament/1.0"})
    fetch = opener or urlopen
    with fetch(request, timeout=timeout) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Google Sheet CSV is larger than the allowed download limit")
    return data.decode("utf-8-sig")


def import_players_from_google_sheet(url: str, *, opener=None) -> ImportReport:
    return parse_players_csv(fetch_published_sheet_csv(url, opener=opener))


def _dedupe(players: tuple[Player, ...], errors: tuple[str, ...]) -> ImportReport:
    seen: set[str] = set()
    unique: list[Player] = []
    duplicates: list[str] = []
    for player in players:
        key = player.name.casefold()
        if key in seen:
            duplicates.append(player.name)
            continue
        seen.add(key)
        unique.append(player)
    return ImportReport(tuple(unique), errors, tuple(duplicates))

"""Excel export of pairings, standings and the alphabetical player list."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from chess_core.app.tournament.models import Pairing, PairingSystem, Player, Standing, points_for
from chess_core.app.tournament.state import TournamentState

_XLSX: SimpleNamespace | None = None


def _xlsx() -> SimpleNamespace:
    """Import openpyxl only when an .xlsx file is actually written."""

    global _XLSX
    if _XLSX is not None:
        return _XLSX
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise RuntimeError("Для экспорта Excel установите пакет openpyxl.") from exc
    styles = SimpleNamespace(
        Workbook=Workbook,
        Alignment=Alignment,
        get_column_letter=get_column_letter,
        header_fill=PatternFill("solid", fgColor="C9A227"),
        header_font=Font(bold=True, color="1E1E1E"),
        thin=Border(
            left=Side(style="thin", color="B8B0A4"),
            right=Side(style="thin", color="B8B0A4"),
            top=Side(style="thin", color="B8B0A4"),
            bottom=Side(style="thin", color="B8B0A4"),
        ),
    )
    _XLSX = styles
    return styles


def export_tournament_xlsx(state: TournamentState, path: str | Path) -> Path:
    names = {player.player_id: player.name for player in state.players}
    table = _standings(state)
    xlsx = _xlsx()
    workbook = xlsx.Workbook()
    _write_pairings(workbook.active, state, names)
    _write_starting_list(workbook.create_sheet("Стартовый список"), state)
    _write_standings(workbook.create_sheet("Положение"), table)
    _write_crosstable(workbook.create_sheet("Кросс-таблица"), state, table)
    _write_alphabetical(workbook.create_sheet("По алфавиту"), state, names, table)
    target = Path(path)
    workbook.save(target)
    return target


def _standings(state: TournamentState) -> tuple[Standing, ...]:
    from chess_core.app.tournament.pairings import standings

    return standings(state.players, state.pairings)


def _write_pairings(sheet, state: TournamentState, names: dict[str, str]) -> None:
    sheet.title = "Пары"
    no_color = state.settings.system is PairingSystem.SWISS_NO_COLOR
    headers = (
        ("Тур", "Доска", "Игрок 1", "Игрок 2", "Результат", "Примечание")
        if no_color
        else ("Тур", "Доска", "Белые", "Чёрные", "Результат", "Примечание")
    )
    _header_row(sheet, headers)
    row = 2
    for pairing in sorted(state.pairings, key=lambda item: (item.round_index, item.board)):
        note = "вручную" if pairing.manual else ("bye" if pairing.is_bye else "")
        values = (
            pairing.round_index,
            pairing.board,
            names.get(pairing.white_id or "", "BYE"),
            names.get(pairing.black_id or "", "BYE"),
            pairing.result or "",
            note,
        )
        _write_row(sheet, row, values)
        row += 1
    _autosize(sheet, len(headers))


def _write_starting_list(sheet, state: TournamentState) -> None:
    headers = ("Ст. №", "Звание", "Игрок", "Федерация", "Рейтинг", "Клуб")
    _header_row(sheet, headers)
    ordered = tuple(sorted(state.players, key=lambda player: player.start_number or 10_000))
    if not all(player.start_number for player in state.players):
        from chess_core.app.tournament.models import assign_pairing_numbers

        ordered = assign_pairing_numbers(state.players)
    for row, player in enumerate(ordered, start=2):
        _write_row(
            sheet,
            row,
            (
                player.start_number,
                player.title,
                player.name,
                player.federation,
                player.rating,
                player.team or "",
            ),
        )
    _autosize(sheet, len(headers))


def _write_standings(sheet, table: tuple[Standing, ...]) -> None:
    headers = ("Место", "Ст. №", "Игрок", "Рейтинг", "Очки", "Партии", "+/=/−", "Бухгольц", "Бергер")
    _header_row(sheet, headers)
    for row, standing in enumerate(table, start=2):
        _write_row(
            sheet,
            row,
            (
                standing.place or row - 1,
                standing.player.start_number,
                standing.player.name,
                standing.player.rating,
                standing.points,
                standing.games,
                f"{standing.wins}/{standing.draws}/{standing.losses}",
                standing.buchholz,
                standing.sonneborn_berger,
            ),
        )
    _autosize(sheet, len(headers))


def _write_crosstable(sheet, state: TournamentState, table: tuple[Standing, ...]) -> None:
    from chess_core.app.tournament.pairings import crosstable

    rows = crosstable(state.players, state.pairings)
    rounds = sorted({pairing.round_index for pairing in state.pairings})
    headers = ["Место", "Ст. №", "Игрок", "Рейтинг"] + [str(round_index) for round_index in rounds] + ["Очки", "BH", "SB"]
    _header_row(sheet, headers)
    del table
    for row_index, (standing, cells) in enumerate(rows, start=2):
        values: list = [
            standing.place or row_index - 1,
            standing.player.start_number,
            standing.player.name,
            standing.player.rating,
        ]
        for cell in cells:
            values.append("" if cell is None else cell.label)
        values.extend([standing.points, standing.buchholz, standing.sonneborn_berger])
        _write_row(sheet, row_index, values)
    _autosize(sheet, len(headers))


def _write_alphabetical(
    sheet,
    state: TournamentState,
    names: dict[str, str],
    table: tuple[Standing, ...],
) -> None:
    del names
    rounds = sorted({pairing.round_index for pairing in state.pairings})
    headers = ["Ст. №", "Игрок", "Рейтинг", "Клуб"] + [f"Тур {round_index}" for round_index in rounds] + ["Очки"]
    _header_row(sheet, headers)
    points = {row.player.player_id: row.points for row in table}
    ordered = sorted(state.players, key=lambda player: (player.name.casefold(), player.start_number))
    for row_index, player in enumerate(ordered, start=2):
        values: list = [player.start_number, player.name, player.rating, player.team or ""]
        for round_index in rounds:
            values.append(
                _round_result_label(
                    state.pairings,
                    player,
                    round_index,
                    show_colour=state.settings.system is not PairingSystem.SWISS_NO_COLOR,
                )
            )
        values.append(points.get(player.player_id, 0.0))
        _write_row(sheet, row_index, values)
    _autosize(sheet, len(headers))


def _round_result_label(
    pairings: tuple[Pairing, ...],
    player: Player,
    round_index: int,
    *,
    show_colour: bool = True,
) -> str:
    for pairing in pairings:
        if pairing.round_index != round_index or player.player_id not in pairing.player_ids():
            continue
        score = points_for(pairing, player.player_id)
        opponent = pairing.black_id if pairing.white_id == player.player_id else pairing.white_id
        if opponent is None:
            return f"BYE {pairing.result or ''}".strip()
        score_text = "" if score is None else str(score).replace(".0", "")
        if not show_colour:
            return score_text
        colour = "б" if pairing.white_id == player.player_id else "ч"
        return f"{colour} {score_text}".strip()
    return ""


def _header_row(sheet, headers: tuple[str, ...] | list[str]) -> None:
    xlsx = _xlsx()
    for column, title in enumerate(headers, start=1):
        cell = sheet.cell(1, column, title)
        cell.fill = xlsx.header_fill
        cell.font = xlsx.header_font
        cell.alignment = xlsx.Alignment(horizontal="center")
        cell.border = xlsx.thin
    sheet.freeze_panes = "A2"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_title_rows = "1:1"


def _write_row(sheet, row: int, values: tuple | list) -> None:
    xlsx = _xlsx()
    for column, value in enumerate(values, start=1):
        cell = sheet.cell(row, column, value)
        cell.border = xlsx.thin
        cell.alignment = xlsx.Alignment(horizontal="center")


def _autosize(sheet, columns: int) -> None:
    letter_of = _xlsx().get_column_letter
    for index in range(1, columns + 1):
        letter = letter_of(index)
        length = 10
        for cell in sheet[letter]:
            length = max(length, min(40, len(str(cell.value or ""))))
        sheet.column_dimensions[letter].width = length + 2

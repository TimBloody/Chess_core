from chess_core.app.tournament.player_import import (
    google_sheet_csv_url,
    import_players_from_excel,
    import_players_from_xlsx,
    parse_players_csv,
)


def test_parse_players_csv_english_and_russian_headers() -> None:
    text = "Name,Rating,Club\nAlice,2100,A\nBob,2000,B\n"
    report = parse_players_csv(text)
    assert [player.name for player in report.players] == ["Alice", "Bob"]
    assert report.players[0].rating == 2100
    russian = "Имя;Рейтинг;Команда\nАнна;1900;Спартак\n"
    report = parse_players_csv(russian)
    assert report.players[0].name == "Анна"
    assert report.players[0].team == "Спартак"


def test_parse_players_csv_dedupes_and_reports_bad_rows() -> None:
    text = "name,rating\nAda,1800\nAda,1700\nBad,not-a-number\n"
    report = parse_players_csv(text)
    assert [player.name for player in report.players] == ["Ada"]
    assert report.duplicates == ("Ada",)
    assert report.errors


def test_google_sheet_url_becomes_public_csv_export() -> None:
    url = "https://docs.google.com/spreadsheets/d/abc123XYZ/edit#gid=42"
    assert google_sheet_csv_url(url) == "https://docs.google.com/spreadsheets/d/abc123XYZ/export?format=csv&gid=42"


def test_google_sheet_already_csv_export_is_kept() -> None:
    url = "https://docs.google.com/spreadsheets/d/abc/export?format=csv&gid=0"
    assert google_sheet_csv_url(url) == url


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self, size: int) -> bytes:
        del size
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        del args


def test_google_fetch_uses_csv_parser() -> None:
    from chess_core.app.tournament.player_import import import_players_from_google_sheet

    def opener(request, timeout: float = 10.0):
        del timeout
        assert "export?format=csv" in request.full_url
        return _FakeResponse(b"name,rating\nNina,1750\n")

    report = import_players_from_google_sheet(
        "https://docs.google.com/spreadsheets/d/abc123/edit#gid=0",
        opener=opener,
    )
    assert report.players[0].name == "Nina"
    assert report.players[0].rating == 1750


def test_import_players_from_xlsx_reads_starting_list(tmp_path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "players.xlsx"
    book = Workbook()
    noise = book.active
    noise.title = "Пары"
    noise.append(("Тур", "Доска", "Белые", "Чёрные"))
    sheet = book.create_sheet("Стартовый список")
    sheet.append(("Ст. №", "Звание", "Игрок", "Федерация", "Рейтинг", "Клуб"))
    sheet.append((1, "FM", "Анна", "RUS", 2100, "Спартак"))
    sheet.append((2, "", "Борис", "FID", 1900, ""))
    book.save(path)
    report = import_players_from_xlsx(str(path))
    assert [player.name for player in report.players] == ["Анна", "Борис"]
    assert report.players[0].rating == 2100
    assert report.players[0].title == "FM"
    assert report.players[0].team == "Спартак"


def test_import_players_from_xls_reads_name_column(tmp_path, monkeypatch) -> None:
    path = tmp_path / "players.xls"
    path.write_bytes(b"placeholder")

    def fake_xls(_path: str):
        return [
            [["Тур", "Доска"], ["1", "1"]],
            [["Игрок", "Рейтинг", "Клуб"], ["Анна", "2100", "Спартак"], ["Борис", "1900", ""]],
        ]

    monkeypatch.setattr("chess_core.app.tournament.player_import._xls_sheets", fake_xls)
    report = import_players_from_excel(str(path))
    assert [player.name for player in report.players] == ["Анна", "Борис"]
    assert report.players[0].rating == 2100
    assert report.players[0].team == "Спартак"

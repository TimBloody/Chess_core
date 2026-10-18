import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PyQt6.QtWidgets import QApplication

from chess_core.core.pgn import parse_pgn
from chess_core.infra.storage.pgn_files import UTF8_BOM, decode_pgn_bytes
from chess_core.ui.pgn_database import PgnDatabaseWidget

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_pgn_database_widget_creates_and_appends(tmp_path: Path) -> None:
    _app()
    folder = tmp_path / "saved"
    folder.mkdir()
    (folder / "g1.txt").write_text(
        """[Event "Chess Core"]
[Site "Local"]
[Date "2026.08.31"]
[Mode "classic_chess"]
[Result "1-0"]

1. e4 e5
2. Qh5 Nc6

1-0
мат
""",
        encoding="utf-8",
    )
    (folder / "g2.pgn").write_text(
        """[Event "Club"]
[Site "?"]
[Date "2026.08.30"]
[Round "1"]
[White "Анна"]
[Black "Борис"]
[Result "0-1"]

1. d4 d5 0-1
""",
        encoding="utf-8",
    )
    widget = PgnDatabaseWidget()
    assert widget.load_folder(folder) == 2
    assert widget.games_table.rowCount() == 2
    database = tmp_path / "club.pgn"
    assert widget.write_new_database(database) == 2
    raw = database.read_bytes()
    assert raw.startswith(UTF8_BOM)
    assert b"\r\n" in raw
    text = decode_pgn_bytes(raw)
    games = parse_pgn(text)
    assert len(games) == 2
    assert any(game.white == "Анна" for game in games)

    extra_folder = tmp_path / "more"
    extra_folder.mkdir()
    (extra_folder / "g3.pgn").write_text(
        """[Event "New"]
[Site "?"]
[Date "2026.09.01"]
[Round "-"]
[White "Виктор"]
[Black "Галина"]
[Result "1-0"]

1. c4 e5 1-0
""",
        encoding="utf-8",
    )
    widget.load_folder(extra_folder)
    assert widget.append_to_database(database) == 1
    assert len(parse_pgn(decode_pgn_bytes(database.read_bytes()))) == 3
    widget.close()

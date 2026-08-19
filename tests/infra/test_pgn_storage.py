"""PGN filesystem and database-tool tests."""

from pathlib import Path

from chess_core.infra.pgn_storage import PgnMetadata, PgnStorage
from chess_core.tools.pgn_database import collect_pgn_files, merge_pgn_files


def test_metadata_uses_chessbase_pgn_tags() -> None:
    metadata = PgnMetadata(
        event="Training",
        white="Alice",
        black="Bob",
        result="1-0",
        white_elo="1800",
        eco="c20",
        annotator="Coach",
    )
    assert metadata.headers()["WhiteElo"] == "1800"
    assert metadata.headers()["ECO"] == "C20"
    assert metadata.headers()["Annotator"] == "Coach"
    assert metadata.suggested_filename().endswith("_Alice_Bob_Training.pgn")


def test_storage_creates_output_and_never_overwrites(tmp_path: Path) -> None:
    storage = PgnStorage(tmp_path / "output")
    first = storage.save('[Event "One"]\n\n*\n', "game.pgn")
    second = storage.save('[Event "Two"]\n\n*\n', "game.pgn")
    assert first.name == "game.pgn"
    assert second.name == "game-2.pgn"
    assert first.read_text(encoding="utf-8").startswith('[Event "One"]')


def test_database_tool_combines_files_and_excludes_target(tmp_path: Path) -> None:
    first = tmp_path / "a.pgn"
    second = tmp_path / "b.pgn"
    target = tmp_path / "database.pgn"
    first.write_text('[Event "A"]\n\n*\n', encoding="utf-8")
    second.write_text('[Event "B"]\n\n*\n', encoding="utf-8")
    target.write_text("old database", encoding="utf-8")

    sources = collect_pgn_files([tmp_path], exclude=target)
    written, game_count = merge_pgn_files(sources, target)

    assert sources == [first.resolve(), second.resolve()]
    assert written == target.resolve()
    assert game_count == 2
    assert target.read_text(encoding="utf-8").count('[Event "') == 2

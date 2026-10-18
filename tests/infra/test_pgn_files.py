"""ChessBase 16 PGN file encoding and folder collection."""

from pathlib import Path

from chess_core.infra.storage.pgn_files import (
    UTF8_BOM,
    decode_pgn_bytes,
    discover_game_files,
    encode_chessbase_pgn,
    load_folder_texts,
    write_chessbase_pgn,
)


def test_chessbase_encoding_is_utf8_bom_and_crlf() -> None:
    text = '[Event "Турнир"]\n[Site "?"]\n\n1. e4 e5 1-0\n'
    data = encode_chessbase_pgn(text)
    assert data.startswith(UTF8_BOM)
    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")
    assert decode_pgn_bytes(data).splitlines()[0] == '[Event "Турнир"]'


def test_decode_legacy_cp1251() -> None:
    raw = '[White "Иванов"]\r\n'.encode("cp1251")
    assert "Иванов" in decode_pgn_bytes(raw)


def test_discover_folder_skips_target_and_reads_txt_and_pgn(tmp_path: Path) -> None:
    folder = tmp_path / "games"
    folder.mkdir()
    (folder / "one.txt").write_text('[Event "A"]\n[Result "*"]\n\n*\n', encoding="utf-8")
    (folder / "two.pgn").write_text('[Event "B"]\n[Result "1-0"]\n\n1. e4 1-0\n', encoding="utf-8")
    (folder / "skip.bin").write_bytes(b"nope")
    target = folder / "all.pgn"
    write_chessbase_pgn(target, '[Event "Old"]\n[Result "*"]\n\n*\n')
    found = discover_game_files(folder, exclude=target)
    names = {path.name for path in found}
    assert names == {"one.txt", "two.pgn"}
    items = load_folder_texts(folder, exclude=target)
    sources = {name for name, _text in items}
    assert sources == {"one.txt", "two.pgn"}
    assert target.read_bytes().startswith(UTF8_BOM)

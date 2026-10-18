"""Tests for engine discovery and mock UCI engine."""

import json
import sys
from pathlib import Path

from chess_core.infra.engines.discovery import EngineDiscovery
from chess_core.infra.engines.process import hidden_popen_kwargs
from chess_core.infra.paths import config_dir


def test_discovery_reads_config(tmp_path: Path, monkeypatch) -> None:
    engine = tmp_path / "stockfish.exe"
    engine.write_text("stub", encoding="utf-8")
    config = tmp_path / "engines.json"
    config.write_text(
        json.dumps(
            {
                "engines": [
                    {
                        "id": "sf",
                        "name": "Stockfish",
                        "path": str(engine),
                        "protocol": "uci",
                        "variants": ["chess"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("chess_core.infra.engines.discovery.config_dir", lambda: tmp_path)
    descriptors = EngineDiscovery().load_config()
    assert descriptors[0].path == engine
    assert descriptors[0].protocol == "uci"


def test_discovery_classifies_fairy_and_ignores_incompatible_scan(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "public"
    fairy = root / "fairystockfish" / "fairy-stockfish.exe"
    fairy_all = root / "fairystockfish-all" / "fairy-stockfish-all.exe"
    scan = root / "scan" / "scan.exe"
    fairy.parent.mkdir(parents=True)
    fairy_all.parent.mkdir(parents=True)
    scan.parent.mkdir(parents=True)
    fairy.write_bytes(b"stub")
    fairy_all.write_bytes(b"stub")
    (fairy.parent / "variants.ini").write_text("[flipello]\n", encoding="utf-8")
    scan.write_bytes(b"stub")
    monkeypatch.setattr(
        "chess_core.infra.engines.discovery.engine_search_roots",
        lambda: (root,),
    )
    found = {item.id: item for item in EngineDiscovery().scan()}
    assert found["fairy-stockfish"].variants >= {
        "crazyhouse",
        "giveaway",
        "minichess",
        "reversi",
    }
    assert found["fairy-stockfish"].options == (
        ("VariantPath", str(fairy.parent / "variants.ini")),
    )
    assert found["fairy-stockfish-all"].variants >= {"duck", "reversi"}
    assert "scan" not in found


def test_hidden_popen_kwargs_hide_windows_console() -> None:
    kwargs = hidden_popen_kwargs()
    assert kwargs["stderr"] is not None
    if sys.platform == "win32":
        import subprocess

        assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW
        startupinfo = kwargs["startupinfo"]
        assert startupinfo.dwFlags & subprocess.STARTF_USESHOWWINDOW
        assert startupinfo.wShowWindow == 0


def test_mock_uci_engine_script_exists() -> None:
    script = Path(__file__).resolve().parents[1] / "fixtures" / "mock_uci_engine.py"
    assert script.is_file()

"""Tests for engine discovery and mock UCI engine."""

import json
import sys
from pathlib import Path

from chess_core.infra.engines.discovery import EngineDiscovery
from chess_core.infra.paths import engines_dir


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


def test_discovery_resolves_config_path_relative_to_config(
    tmp_path: Path, monkeypatch
) -> None:
    config_dir = tmp_path / "config"
    engine = tmp_path / "engines" / "public" / "stockfish" / "stockfish.exe"
    config_dir.mkdir()
    engine.parent.mkdir(parents=True)
    engine.write_text("stub", encoding="utf-8")
    (config_dir / "engines.json").write_text(
        json.dumps(
            {
                "engines": [
                    {
                        "path": "../engines/public/stockfish/stockfish.exe",
                        "protocol": "uci",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "chess_core.infra.engines.discovery.config_dir", lambda: config_dir
    )

    descriptors = EngineDiscovery().load_config()

    assert descriptors[0].path == engine.resolve()


def test_default_engines_dir_is_inside_project_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CHESS_CORE_ENGINES_DIR", raising=False)
    monkeypatch.setattr("chess_core.infra.paths.project_root", lambda: tmp_path)

    assert engines_dir() == tmp_path / "engines"


def test_mock_uci_engine_script_exists() -> None:
    script = Path(__file__).resolve().parents[1] / "fixtures" / "mock_uci_engine.py"
    assert script.is_file()

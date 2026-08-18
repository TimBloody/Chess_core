"""Tests for engine discovery and mock UCI engine."""

import json
import sys
from pathlib import Path

from chess_core.infra.engines.discovery import EngineDiscovery
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


def test_mock_uci_engine_script_exists() -> None:
    script = Path(__file__).resolve().parents[1] / "fixtures" / "mock_uci_engine.py"
    assert script.is_file()

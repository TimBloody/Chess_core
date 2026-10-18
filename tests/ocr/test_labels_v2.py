"""labels.json v2 and irreversible v1 merges."""

from __future__ import annotations

import json
from pathlib import Path

from chess_core.ocr.labels import charset_from_labels, migrate_labels_file
from chess_core.ocr.roles import ROLE_IDS, migrate_v1_charset


def test_v1_c_c_merge_is_a_warning() -> None:
    mapping, warnings = migrate_v1_charset(
        tuple("abcdefghNKBRQxO12345678#")
    )
    assert mapping[0] == "f_a"
    assert "KN" in mapping.values()
    assert any("слиты" in item or "собрана" in item or "C" in item for item in warnings)


def test_migrate_writes_report(tmp_path: Path) -> None:
    path = tmp_path / "labels.json"
    path.write_text(
        json.dumps({"charset": list("abcNKBRQxO12345678#")}),
        encoding="utf-8",
    )
    payload = migrate_labels_file(path)
    assert payload["version"] == 2
    assert charset_from_labels(payload) == ROLE_IDS
    assert (tmp_path / "migration_report.json").is_file()
    assert (tmp_path / "labels_v1.json").is_file()

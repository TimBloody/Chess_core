"""labels.json v2 (roles) and migration from v1 letter classes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chess_core.ocr.roles import ROLE_IDS, labels_v2_payload, migrate_v1_charset


def load_labels_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def charset_from_labels(payload: dict[str, Any]) -> tuple[str, ...]:
    if int(payload.get("version") or 1) >= 2:
        roles = payload.get("roles") or labels_v2_payload()["roles"]
        ordered = sorted(roles, key=lambda row: int(row["index"]))
        return tuple(str(row["id"]) for row in ordered)
    return tuple(str(item) for item in payload["charset"])


def migrate_labels_file(path: Path, *, report_path: Path | None = None) -> dict[str, Any]:
    payload = load_labels_payload(path)
    if int(payload.get("version") or 1) >= 2:
        return payload
    charset = tuple(str(item) for item in payload.get("charset") or ())
    mapping, warnings = migrate_v1_charset(charset)
    report = {
        "from_version": 1,
        "to_version": 2,
        "old_charset": list(charset),
        "old_index_to_role": {str(key): value for key, value in mapping.items()},
        "warnings": warnings,
    }
    target = report_path or (path.parent / "migration_report.json")
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    backup = path.with_name("labels_v1.json")
    if not backup.is_file():
        backup.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    merged = labels_v2_payload()
    merged.update(
        {
            "migrated_from": str(backup),
            "migration_report": str(target),
            "legacy": {key: payload[key] for key in payload if key != "charset"},
        }
    )
    return merged

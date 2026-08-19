"""External chess engine discovery."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from chess_core.infra.paths import config_dir, engines_dir


@dataclass(frozen=True, slots=True)
class EngineDescriptor:
    id: str
    name: str
    path: Path
    protocol: Literal["uci", "usi", "hub"]
    variants: frozenset[str]


class EngineDiscovery:
    def scan(self) -> list[EngineDescriptor]:
        found: dict[str, EngineDescriptor] = {}
        for root in self._search_roots():
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*.exe")):
                descriptor = self._descriptor_for(path)
                if descriptor is not None:
                    found[descriptor.id] = descriptor
        return list(found.values())

    def _search_roots(self) -> list[Path]:
        roots = [engines_dir()]
        config_file = config_dir() / "engines.json"
        if config_file.is_file():
            roots.append(config_dir())
        env_path = os.environ.get("CHESS_CORE_ENGINE_PATH")
        if env_path:
            roots.append(Path(env_path).parent)
        return roots

    def _descriptor_for(self, path: Path) -> EngineDescriptor | None:
        name = path.stem.lower()
        if "yaneura" in name or "usi" in name or "fukaura" in name:
            protocol: Literal["uci", "usi", "hub"] = "usi"
            variants = frozenset({"shogi"})
        elif "scan" in name or "hub" in name:
            protocol = "hub"
            variants = frozenset({"draughts", "checkers"})
        else:
            protocol = "uci"
            variants = frozenset({"chess"})
        return EngineDescriptor(
            id=path.stem,
            name=path.stem,
            path=path,
            protocol=protocol,
            variants=variants,
        )

    def load_config(self) -> list[EngineDescriptor]:
        config_file = config_dir() / "engines.json"
        if not config_file.is_file():
            return []
        data = json.loads(config_file.read_text(encoding="utf-8"))
        descriptors: list[EngineDescriptor] = []
        for entry in data.get("engines", []):
            path = Path(entry["path"]).expanduser()
            if not path.is_absolute():
                path = (config_file.parent / path).resolve()
            if path.is_file():
                descriptors.append(
                    EngineDescriptor(
                        id=entry.get("id", path.stem),
                        name=entry.get("name", path.stem),
                        path=path,
                        protocol=entry.get("protocol", "uci"),
                        variants=frozenset(entry.get("variants", ["chess"])),
                    )
                )
        return descriptors

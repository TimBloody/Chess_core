"""External chess engine discovery."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from chess_core.infra.paths import config_dir, engine_search_roots


@dataclass(frozen=True, slots=True)
class EngineDescriptor:
    id: str
    name: str
    path: Path
    protocol: Literal["uci", "usi", "internal"]
    variants: frozenset[str]
    options: tuple[tuple[str, str], ...] = ()


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
        roots = list(engine_search_roots())
        config_file = config_dir() / "engines.json"
        if config_file.is_file():
            roots.append(config_dir())
        env_path = os.environ.get("CHESS_CORE_ENGINE_PATH")
        if env_path:
            roots.append(Path(env_path).parent)
        return roots

    def _descriptor_for(self, path: Path) -> EngineDescriptor | None:
        name = path.stem.lower()
        if name in {"scan"} or name.startswith("scan"):
            # Scan speaks Hub protocol and plays 10x10 international draughts;
            # this project currently implements 8x8 Russian draughts.
            return None
        if "yaneura" in name or name.endswith("-usi") or "usi" in name:
            options: tuple[tuple[str, str], ...] = ()
            eval_dir = path.parent / "eval"
            if eval_dir.is_dir():
                options = (("EvalDir", str(eval_dir)),)
            return EngineDescriptor(
                id=path.stem,
                name=path.stem,
                path=path,
                protocol="usi",
                variants=frozenset({"shogi"}),
                options=options,
            )
        if "fairy" in name:
            variants_ini = path.parent / "variants.ini"
            options: tuple[tuple[str, str], ...] = ()
            all_build = "all" in name or "all" in path.parent.name.lower()
            extra_variants: set[str] = {"duck", "reversi"} if all_build else set()
            if variants_ini.is_file():
                options = (("VariantPath", str(variants_ini)),)
                extra_variants.add("reversi")
            return EngineDescriptor(
                id="fairy-stockfish-all" if all_build else "fairy-stockfish",
                name="Fairy-Stockfish ALLVARS" if all_build else "Fairy-Stockfish",
                path=path,
                protocol="uci",
                variants=frozenset(
                    {
                        "chess",
                        "chess960",
                        "crazyhouse",
                        "bughouse",
                        "giveaway",
                        "shogi",
                        "kyoto_shogi",
                        "dobutsu_shogi",
                        "minichess",
                    }
                    | extra_variants
                ),
                options=options,
            )
        variants = frozenset({"chess", "chess960", "hand_and_brain"})
        if "stockfish" in name:
            return EngineDescriptor(
                id="stockfish",
                name="Stockfish",
                path=path,
                protocol="uci",
                variants=variants,
            )
        return EngineDescriptor(
            id=path.stem,
            name=path.stem,
            path=path,
            protocol="uci",
            variants=frozenset({"chess"}),
        )

    def load_config(self) -> list[EngineDescriptor]:
        config_file = config_dir() / "engines.json"
        if not config_file.is_file():
            return []
        data = json.loads(config_file.read_text(encoding="utf-8"))
        descriptors: list[EngineDescriptor] = []
        for entry in data.get("engines", []):
            path = Path(entry["path"])
            if path.is_file():
                protocol = entry.get("protocol", "uci")
                descriptors.append(
                    EngineDescriptor(
                        id=entry.get("id", path.stem),
                        name=entry.get("name", path.stem),
                        path=path,
                        protocol=protocol,
                        variants=frozenset(entry.get("variants", ["chess"])),
                        options=tuple(
                            (str(key), str(value))
                            for key, value in dict(entry.get("options", {})).items()
                        ),
                    )
                )
        return descriptors

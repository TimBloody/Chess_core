"""Headless helpers for the Chess_core MCP server (no MCP SDK import)."""

from __future__ import annotations

import ast
from pathlib import Path

from chess_core.app.engine import BestMove
from chess_core.app.engine_play import resolve_engine_turn
from chess_core.app.game import evaluate_status
from chess_core.app.search import legal_turns
from chess_core.core.gamemode import GameMode
from chess_core.core.move import DropAction, MoveAction
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import (
    NotationStyle,
    format_engine_turn,
    format_turn,
    parse_fen,
    parse_square,
    to_fen,
)
from chess_core.core.registry import default_registry
from chess_core.core.rules import VictoryCondition
from chess_core.core.state import GameState
from chess_core.modes import register_builtin_modes, resolve_mode
from chess_core.modes.mode_docs import (
    all_mode_docs,
    describe_mode_id,
    search_mode_docs,
)
from chess_core.modes.orchestrator import (
    BASE_LABELS,
    LAYERS,
    compatible_layers,
    parse_spec,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]

_DOC_FILES = (
    "for_agent.me",
    "docs/ARCHITECTURE.md",
    "docs/COMMON_GAME_CONTRACTS.md",
    "docs/ENGINES.md",
    "docs/MODES.md",
)

_LAYER_FORBIDDEN: dict[str, tuple[str, ...]] = {
    "core": (
        "chess_core.app",
        "chess_core.ui",
        "chess_core.infra",
        "chess_core.modes",
        "PyQt6",
        "PyQt5",
    ),
    "modes": ("chess_core.app", "chess_core.ui", "PyQt6", "PyQt5"),
    "app": ("chess_core.ui", "PyQt6", "PyQt5"),
    "infra": ("chess_core.ui", "PyQt6", "PyQt5"),
}

_TEST_HINTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("classical", "классик", "scholar"), ("tests/core/test_classical_chess.py",)),
    (("repetition", "повторен"), ("tests/core/test_repetition.py",)),
    (("topology", "цилиндр", "portal"), ("tests/core/test_topology.py",)),
    (("ray", "луч"), ("tests/core/test_rays.py",)),
    (("board", "square", "bitmask"), ("tests/core/test_board_contract.py",)),
    (("giveaway",), ("tests/core/test_giveaway.py",)),
    (("fairy", "fairytale", "сказочн"), ("tests/core/test_fairytale.py", "tests/core/test_orchestrator.py")),
    (("960", "chess960"), ("tests/core/test_chess960.py",)),
    (("bughouse",), ("tests/core/test_bughouse.py", "tests/app/test_match.py")),
    (("hand", "brain"), ("tests/core/test_hand_and_brain.py",)),
    (("gobblet",), ("tests/core/test_gobblet.py", "tests/app/test_gobblet_engine.py")),
    (("orchestr", "layer", "compose"), ("tests/core/test_orchestrator.py",)),
    (("notation", "uci", "fen", "pgn"), ("tests/core/test_move_notation.py", "tests/core/test_pgn.py")),
    (("board_game", "reversi", "draughts", "шашк", "уголк"), ("tests/core/test_board_games.py",)),
    (("clock", "час"), ("tests/app/test_clock.py", "tests/infra/test_clock_sync.py")),
    (("editor", "редактор"), ("tests/app/test_editor.py", "tests/ui/test_editor_widget.py")),
    (("puzzle", "задач"), ("tests/app/test_puzzles.py",)),
    (("maze", "лабиринт"), ("tests/app/test_training_maze.py",)),
    (("memory", "памят"), ("tests/app/test_training_memory.py",)),
    (("tournament", "турнир", "swiss", "dutch"), ("tests/app/test_tournament.py", "tests/app/test_swiss_manager.py")),
    (("engine", "движок", "uci"), ("tests/app/test_engine_play.py", "tests/app/test_search.py", "tests/infra/test_engines.py")),
    (("network", "сет", "lobby", "лобби"), ("tests/infra/test_lobby_seats.py", "tests/infra/test_network_undo.py", "tests/ui/test_network_page.py")),
    (("pgn", "баз"), ("tests/app/test_pgn_database.py", "tests/infra/test_pgn_files.py", "tests/ui/test_pgn_database_page.py")),
    (("hub", "shell", "ветк"), ("tests/ui/test_hub.py",)),
    (("smoke", "ui"), ("tests/test_ui_smoke.py", "tests/test_integration_contracts.py")),
)

_ROUTE_HINTS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (
        ("виджет", "окно", "pyqt", "хаб", "hub", "stylesheet", "svg", "палитр"),
        "ui",
        "Правила не писать в UI. Виджеты только рисуют состояние и шлют команды в app.",
    ),
    (
        ("сеть", "tcp", "лобби", "lobby", "протокол", "uci", "usi", "discovery"),
        "infra",
        "Сеть, движки и файлы живут в infra. Правила партии остаются в core.",
    ),
    (
        ("журнал", "pgn", "турнир", "часы", "задач", "лабиринт", "памят", "elo", "ocr", "движок парт"),
        "app",
        "Сценарии партии, запись, турнир, обучение и выбор движка — application-слой.",
    ),
    (
        ("режим", "ruleset", "слой", "giveaway", "duck", "fairy", "fairytale", "orchestr", "каталог фигур"),
        "modes",
        "Новый режим = GameMode/orchestrator, не ветвления по mode.id в movegen.",
    ),
    (
        ("ход", "movegen", "fen", "тополог", "луч", "шах", "мат", "рокиров", "drop", "побед", "move_resolver"),
        "core",
        "Ядро: доска, лучи, ходы, нотация. Без PyQt, сети и файловой системы.",
    ),
)


def repo_root() -> Path:
    return _REPO_ROOT


def project_brief() -> dict[str, object]:
    return {
        "project": "Chess_core",
        "layers": {
            "ui": "PyQt presentation only",
            "app": "game, editor, puzzles, training, tournament, engines",
            "infra": "files, TCP, UCI/USI, packaging",
            "core": "board, rules, movegen, notation",
            "modes": "GameMode factories + orchestrator overlays",
        },
        "imports": "ui -> app -> core; infra -> app/core; core imports nothing project-specific",
        "new_mode": (
            "Add GameMode fields / orchestrator layer. Do not branch on mode.id in movegen or UI. "
            "Every playable mode must go through GameRecord / LocalGameService."
        ),
        "do_not_touch_unless_asked": [
            "Capablanca 10x8",
            "portal topology beyond the stub",
            "AlphaZero",
        ],
        "commands": {
            "ui": r".\.venv\Scripts\python.exe -m chess_core.ui.app_entry",
            "tests": r".\.venv\Scripts\python.exe -m pytest -q",
            "classic_regressions": r".\.venv\Scripts\python.exe -m pytest tests/core/test_classical_chess.py -q",
        },
        "docs": list(_DOC_FILES),
        "hint": (
            "Use search_docs, list_modes, and mode_details (includes rules text) "
            "before reading for_agent.me in full. Education-branch modes are in "
            "mode_docs even when not registered on master."
        ),
    }


def search_docs(query: str, limit: int = 12) -> dict[str, object]:
    needle = query.strip()
    if not needle:
        return {"error": "query must not be empty"}
    lowered = needle.lower()
    hits: list[dict[str, object]] = []
    hits.extend(search_mode_docs(needle, limit=limit))
    for relative in _DOC_FILES:
        if len(hits) >= limit:
            break
        path = _REPO_ROOT / relative
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines, start=1):
            if lowered not in line.lower():
                continue
            start = max(0, index - 2)
            end = min(len(lines), index + 1)
            hits.append(
                {
                    "file": relative.replace("\\", "/"),
                    "line": index,
                    "text": "\n".join(lines[start:end]).strip(),
                }
            )
            if len(hits) >= limit:
                break
    return {"query": needle, "hits": hits[:limit]}


def list_modes() -> dict[str, object]:
    register_builtin_modes()
    catalog = all_mode_docs()
    return {
        "registry": default_registry.list_modes(),
        "bases": [
            {"id": mode_id, "label": label} for mode_id, label in BASE_LABELS.items()
        ],
        "layers": [
            {
                "id": layer.id,
                "label": layer.label,
                "applies_to": sorted(layer.applies_to),
                "conflicts": sorted(layer.conflicts),
                "summary": (describe_mode_id(layer.id).get("summary")),
            }
            for layer in LAYERS.values()
        ],
        "documented": [
            {
                "id": entry.id,
                "name": entry.name,
                "kind": entry.kind,
                "availability": entry.availability,
                "summary": entry.summary,
            }
            for entry in catalog
        ],
        "education_branch": [
            {
                "id": entry.id,
                "name": entry.name,
                "kind": entry.kind,
                "summary": entry.summary,
            }
            for entry in catalog
            if entry.availability == "education_branch"
        ],
        "compose_example": "chess+cylindrical+giveaway",
        "docs_hint": "Call mode_details(mode_id) or mode_docs(mode_id) for full rules text.",
    }


def mode_docs(mode_id: str | None = None) -> dict[str, object]:
    """Catalog of intended rules. Omit mode_id for the full list."""
    if mode_id is None or not str(mode_id).strip():
        return {
            "count": len(all_mode_docs()),
            "modes": [describe_mode_id(entry.id) for entry in all_mode_docs()],
        }
    return describe_mode_id(mode_id)


def _victory_names(mode: GameMode) -> list[str]:
    conditions = mode.victory if isinstance(mode.victory, tuple) else (mode.victory,)
    names: list[str] = []
    for item in conditions:
        if isinstance(item, VictoryCondition):
            names.append(item.kind.name)
    return names


def mode_details(mode_id: str) -> dict[str, object]:
    docs = describe_mode_id(mode_id)
    try:
        mode = resolve_mode(mode_id)
    except (KeyError, ValueError) as exc:
        return {
            **docs,
            "live": False,
            "error": str(exc),
            "note": (
                "No live GameMode on this branch; rules text above is from the "
                "documentation catalog (often education_branch)."
            ),
        }
    try:
        spec = parse_spec(mode.id)
        base = spec.base
        layers = sorted(spec.layers)
        compatible = sorted(compatible_layers(spec.base, spec.layers))
    except ValueError:
        base = mode.id
        layers = []
        compatible = []
    shape = mode.board.shape
    return {
        "id": mode.id,
        "name": mode.name,
        "live": True,
        "description": docs.get("summary"),
        "rules": docs.get("rules"),
        "doc": docs,
        "files": shape.files,
        "ranks": shape.ranks,
        "topology": type(mode.topology).__name__,
        "royal_type": mode.royal_type,
        "checks_enabled": mode.checks_enabled,
        "asset_family": mode.asset_family,
        "victory": _victory_names(mode),
        "drop_rule": type(mode.drop_rule).__name__ if mode.drop_rule else None,
        "capture_sink": mode.capture_sink.name if mode.capture_sink else None,
        "promotion_rule": type(mode.promotion_rule).__name__ if mode.promotion_rule else None,
        "legality": type(mode.legality).__name__ if mode.legality else None,
        "move_resolver": (
            type(mode.move_resolver).__name__ if mode.move_resolver is not None else None
        ),
        "turn_steps": [step.kind.name for step in mode.turn_scenario.steps],
        "piece_types": [piece.id.name for piece in mode.pieces.all_types()],
        "base": base,
        "layers": layers,
        "compatible_layers": compatible,
        "availability": docs.get("availability", "master"),
    }


def _load_state(mode_id: str, fen: str | None) -> tuple[GameMode, GameState]:
    mode = resolve_mode(mode_id)
    if fen and fen.strip():
        return mode, parse_fen(fen.strip(), mode)
    return mode, mode.initial_state()


def _status_payload(mode: GameMode, state: GameState) -> dict[str, object]:
    generator = MoveGenerator(mode)
    status = evaluate_status(mode, generator, state, is_live=True)
    try:
        fen = to_fen(state)
    except ValueError:
        fen = None
    return {
        "mode_id": mode.id,
        "status": status.name,
        "side_to_move": state.side_to_move.name.lower(),
        "fen": fen,
        "in_check": bool(mode.checks_enabled and generator.is_in_check(state)),
    }


def legal_moves(
    mode_id: str,
    fen: str | None = None,
    square: str | None = None,
    limit: int = 80,
) -> dict[str, object]:
    mode, state = _load_state(mode_id, fen)
    turns = legal_turns(state, duck_limit=8)
    shape = mode.board.shape
    if square and square.strip():
        token = square.strip()
        if token.isdigit():
            origin = int(token)
        else:
            parsed = parse_square(token.lower(), shape.files, shape.ranks)
            origin = parsed.index(shape.files)
        filtered = []
        for turn in turns:
            action = turn.actions[0]
            if isinstance(action, MoveAction) and action.from_square.index(shape.files) == origin:
                filtered.append(turn)
            elif isinstance(action, DropAction) and action.to_square.index(shape.files) == origin:
                filtered.append(turn)
        turns = filtered
    tokens = [format_engine_turn(turn) for turn in turns[: max(1, limit)]]
    payload = _status_payload(mode, state)
    payload["moves"] = tokens
    payload["move_count"] = len(turns)
    payload["truncated"] = len(turns) > len(tokens)
    return payload


def apply_move(mode_id: str, move: str, fen: str | None = None) -> dict[str, object]:
    mode, state = _load_state(mode_id, fen)
    turn = resolve_engine_turn(state, BestMove(move_uci=move, evaluation=None))
    if turn is None:
        return {
            "error": f"move {move!r} is not a legal engine token in this position",
            **_status_payload(mode, state),
        }
    after = state.apply_turn(turn)
    payload = _status_payload(mode, after)
    payload["played"] = format_engine_turn(turn)
    payload["notation"] = format_turn(
        turn, before=state, after=after, style=NotationStyle.PIECE_SQUARE
    )
    return payload


def where_to_change(task: str) -> dict[str, object]:
    text = task.strip().lower()
    if not text:
        return {"error": "task must not be empty"}
    for needles, layer, note in _ROUTE_HINTS:
        if any(needle in text for needle in needles):
            return {"layer": layer, "note": note, "task": task.strip()}
    return {
        "layer": "unclear",
        "note": "If it changes legal moves or victory, it is core/modes. If it only draws, it is ui.",
        "task": task.strip(),
    }


def related_tests(area: str) -> dict[str, object]:
    text = area.strip().lower()
    if not text:
        return {"error": "area must not be empty"}
    files: list[str] = []
    for needles, paths in _TEST_HINTS:
        if any(needle in text for needle in needles):
            files.extend(paths)
    unique = list(dict.fromkeys(files))
    if not unique:
        unique = [
            "tests/core/test_classical_chess.py",
            "tests/test_integration_contracts.py",
        ]
    return {"area": area.strip(), "tests": unique}


def _layer_of(path: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(_REPO_ROOT / "src" / "chess_core")
    except ValueError:
        return None
    parts = relative.parts
    if not parts:
        return None
    if parts[0] in _LAYER_FORBIDDEN or parts[0] in {"ui", "tools"}:
        return parts[0]
    return None


def _imported_modules(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def check_layer_imports(path: str) -> dict[str, object]:
    target = Path(path)
    if not target.is_absolute():
        target = _REPO_ROOT / target
    if not target.is_file():
        return {"error": f"file not found: {path}"}
    layer = _layer_of(target)
    forbidden = _LAYER_FORBIDDEN.get(layer or "", ())
    source = target.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(target))
    violations: list[str] = []
    for imported in _imported_modules(tree):
        if any(imported == item or imported.startswith(f"{item}.") for item in forbidden):
            violations.append(imported)
    relative = str(target.resolve().relative_to(_REPO_ROOT)).replace("\\", "/")
    return {
        "path": relative,
        "layer": layer,
        "ok": not violations,
        "violations": sorted(set(violations)),
        "rule": _LAYER_FORBIDDEN.get(layer) if layer in _LAYER_FORBIDDEN else "no import ban for this layer",
    }

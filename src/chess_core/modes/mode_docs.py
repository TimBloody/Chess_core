"""Human-readable rules catalog for MCP and docs.

Live ``GameMode`` facts come from factories/orchestrator. This module stores
the *intended* rule text so agents do not reverse-engineer tests. Entries with
``availability="education_branch"`` exist on git branch ``education`` and are
documented here even when they are not registered on ``master``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ModeDocEntry:
    """One documented mode, overlay layer, preset, or training activity."""

    id: str
    name: str
    kind: str
    availability: str
    summary: str
    rules: str
    aliases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


def _e(
    mode_id: str,
    name: str,
    kind: str,
    availability: str,
    summary: str,
    rules: str,
    *,
    aliases: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
) -> ModeDocEntry:
    return ModeDocEntry(
        id=mode_id,
        name=name,
        kind=kind,
        availability=availability,
        summary=summary,
        rules=rules,
        aliases=aliases,
        tags=tags,
    )


_ENTRIES: tuple[ModeDocEntry, ...] = (
    # --- master bases ---
    _e(
        "chess",
        "Классика",
        "base",
        "master",
        "Стандартные шахматы 8×8.",
        "Плоская доска 8×8, обычные фигуры, один ход за раз, шахи включены, "
        "победа — мат. Рокировка, взятие на проходе, превращение по правилам ФИДЕ. "
        "Alias id: classic_chess.",
        aliases=("classic_chess",),
        tags=("chess", "fide"),
    ),
    _e(
        "minichess",
        "Мини-шахматы",
        "base",
        "master",
        "Gardner minichess 5×5.",
        "Доска 5×5, фигуры как в классике (урезанный старт). Победа — мат. "
        "Внешний движок: Fairy-Stockfish UCI_Variant=gardner.",
        tags=("chess", "mini"),
    ),
    _e(
        "shogi",
        "Сёги",
        "base",
        "master",
        "Стандартные сёги 9×9.",
        "Доска 9×9, сбросы из руки, зона превращения 3 ряда, шахи/мат. "
        "Нотация SFEN/USI; движок YaneuraOu, иначе Fairy-Stockfish.",
        tags=("shogi",),
    ),
    _e(
        "kyoto_shogi",
        "Киото-сёги",
        "base",
        "master",
        "Киото-сёги: переворот фигуры после каждого хода.",
        "Малая доска сёги с парами лиц (например конь/серебро). После хода "
        "фигура меняет лицо. Сбросы с выбором лица. Fairy-Stockfish kyotoshogi.",
        tags=("shogi",),
    ),
    _e(
        "dobutsu_shogi",
        "Добуцу-сёги",
        "base",
        "master",
        "Добуцу (зверюшки) 3×4.",
        "Лев, жираф, слон, цыплёнок/курица. Победа: взять льва или безопасно "
        "дойти львом до последней линии. Fairy-Stockfish dobutsu.",
        tags=("shogi", "mini"),
    ),
    _e(
        "reversi",
        "Реверси",
        "base",
        "master",
        "Отелло/реверси 8×8.",
        "Ход — сброс фишки на пустую клетку с переворотом зажатых чужих. "
        "Победа по большинству фишек. Fairy-Stockfish flipello.",
        tags=("board_game",),
    ),
    _e(
        "corners",
        "Уголки",
        "base",
        "master",
        "Уголки: довести свои шашки в противоположный угол.",
        "Ходы и прыжки по своим правилам уголкам; победа по размещению. "
        "Встроенный alpha-beta.",
        tags=("board_game",),
    ),
    _e(
        "draughts",
        "Шашки",
        "base",
        "master",
        "Русские шашки 8×8.",
        "Простые и дамки, взятия по диагонали, обязательное взятие через "
        "MustCaptureLegality. Победа по материалу / отсутствию ходов. "
        "Встроенный alpha-beta (не Scan 10×10).",
        aliases=("checkers",),
        tags=("board_game", "draughts"),
    ),
    _e(
        "gobblet",
        "Gobblet Gobblers",
        "base",
        "master",
        "Gobblet 3×3 со стопками.",
        "Три размера фишек, накрывание, линия из трёх своих верхних фишек. "
        "Движок: app/gobblet_engine (книга + tablebase + поиск).",
        tags=("board_game", "gobblet"),
    ),
    _e(
        "hasami_shogi",
        "Хасами сёги",
        "base",
        "master",
        "Хасами сёги 6×6.",
        "Доска 6×6; по одному ряду фигур (пешки сёги) на 1-й и 6-й горизонталях. "
        "Ходят как ладья (ортогональный слайд без прыжков). Взятие custodian: "
        "зажать одну или несколько чужих фигур между двумя своими по горизонтали "
        "или вертикали своим ходом; зажатые снимаются. Войти между двумя чужими "
        "безопасно. Чёрные ходят первыми. Победа, когда у соперника ≤1 фигуры. "
        "Встроенный alpha-beta.",
        tags=("board_game", "shogi"),
    ),
    _e(
        "nanai_checkers",
        "Нанайские шашки",
        "base",
        "master",
        "Нанайские шашки 6×6.",
        "Доска 6×6; белые на 1-й горизонтали, чёрные на 6-й. Ход — на одну клетку "
        "ортогонально. Взятие своим ходом: на линии образуется «своя–своя–чужая» "
        "(без четвёртой своей перед блоком); чужая снимается. Три своих подряд "
        "чужую не берут. Войти напротив двух чужих безопасно. Победа при ≤1 "
        "фигуре у соперника. Встроенный alpha-beta.",
        tags=("board_game", "draughts"),
    ),
    # --- master layers ---
    _e(
        "giveaway",
        "Giveaway",
        "layer",
        "master",
        "Антишахматы: обязательное взятие, выигрывает отдавший все фигуры.",
        "Applies to chess/minichess. MustCaptureLegality, checks_enabled=False, "
        "VictoryKind.MATERIAL (пустая сторона побеждает), превращение может "
        "включать короля. Fairy-Stockfish antichess. Alias preset: giveaway.",
        tags=("chess", "layer"),
    ),
    _e(
        "fairy",
        "Fairytale",
        "layer",
        "master",
        "Сказочные ходы по файлу (FairytaleFileResolver).",
        "Applies to chess/minichess. Пешка, ферзь и король ходят как обычно. "
        "Ладья, слон и конь ходят как фигура стартового ряда текущего файла: "
        "a/h → ладья, b/g → конь, c/f → слон; на d/e сохраняют свой тип. "
        "Шахи обычные. Alias: fairytale. Движок: встроенный alpha-beta. "
        "Исключение: вместе с Duck тот же слой включает fairy_duck_rules "
        "(нет шахов, VictoryKind.KING_CAPTURE, Fairy-Stockfish ALLVARS duck) "
        "и НЕ ставит FairytaleFileResolver.",
        aliases=("fairytale",),
        tags=("chess", "layer", "movement"),
    ),
    _e(
        "cylindrical",
        "Цилиндрические",
        "layer",
        "master",
        "Цилиндр по вертикалям: a и h соседние.",
        "Applies to chess. CylindricalFilesTopology; лучи с масками cylinder_8x8. "
        "Встроенный alpha-beta. Alias: cylindrical_chess.",
        aliases=("cylindrical_chess",),
        tags=("chess", "layer", "topology"),
    ),
    _e(
        "duck",
        "Duck chess",
        "layer",
        "master",
        "После хода поставить нейтральную утку-блокер.",
        "Applies to chess/minichess. TurnScenario + PLACE_BLOCKER. Утка в FEN — `*`. "
        "По умолчанию шахи/мат как в ядре. Conflicts: bughouse, hand_and_brain. "
        "С слоем fairy → правила Fairy Duck (см. fairy).",
        aliases=("duck_chess",),
        tags=("chess", "layer", "turn"),
    ),
    _e(
        "crazyhouse",
        "Crazyhouse",
        "layer",
        "master",
        "Взятые фигуры в руку, сброс вместо хода.",
        "Applies to chess. CaptureSink.MOVER_HAND + CrazyhouseDropRule. "
        "Fairy-Stockfish crazyhouse. Conflicts: bughouse.",
        tags=("chess", "layer", "drops"),
    ),
    _e(
        "chess960",
        "Chess960",
        "layer",
        "master",
        "Фишеровская случайная расстановка.",
        "Applies to chess. Scharnagl 0..959, рокировка «король на ладью». "
        "Stockfish UCI_Chess960.",
        tags=("chess", "layer", "setup"),
    ),
    _e(
        "bughouse",
        "Bughouse",
        "layer",
        "master",
        "Парные шахматы на двух досках с подарками.",
        "Applies to chess. Две доски, карман подарков партнёру. "
        "Fairy-Stockfish bughouse. Conflicts: duck, hand_and_brain, crazyhouse.",
        tags=("chess", "layer", "match"),
    ),
    _e(
        "hand_and_brain",
        "Hand & Brain",
        "layer",
        "master",
        "Один выбирает тип фигуры, второй ходит ею.",
        "Applies to chess. match_kind=hand_and_brain. Conflicts: duck, bughouse. "
        "Движок как у классики (Stockfish).",
        tags=("chess", "layer", "match"),
    ),
    # --- education-branch chess modifiers / presets ---
    _e(
        "three_check",
        "Три шаха",
        "education_mode",
        "education_branch",
        "Доп. победа: три шаха сопернику.",
        "На ветке education: VictoryKind.THREE_CHECK (порог 3) + обычный мат. "
        "Счётчик ThreeCheckCounter. Композируется с другими модификаторами "
        "(например three_check_king_of_the_hill). На master пока не зарегистрирован.",
        tags=("chess", "victory", "education"),
    ),
    _e(
        "king_of_the_hill",
        "Царь горы",
        "education_mode",
        "education_branch",
        "Доп. победа: король на центре.",
        "На ветке education: королевская фигура безопасно занимает одну из "
        "центральных клеток d4/e4/d5/e5 (8×8). Мат остаётся победой. "
        "На master пока не зарегистрирован.",
        tags=("chess", "victory", "education"),
    ),
    _e(
        "three_check_king_of_the_hill",
        "Три шаха + царь горы",
        "education_mode",
        "education_branch",
        "Комбинация three_check и king_of_the_hill.",
        "Preset на education: оба условия победы активны вместе с матом.",
        tags=("chess", "victory", "education"),
    ),
    _e(
        "two_move",
        "Двухходовки",
        "education_mode",
        "education_branch",
        "Обычно два хода подряд за сторону.",
        "На education: белые открывают одним ходом; далее обычно два хода; "
        "если первый даёт шах — ход обрывается; если сторона начинает под шахом — "
        "только один ход. На master пока не зарегистрирован.",
        tags=("chess", "turn", "education"),
    ),
    _e(
        "minishogi",
        "Мини-сёги",
        "education_mode",
        "education_branch",
        "Сёги 5×5.",
        "На education: 5×5, зона превращения один ряд, иначе стандартные сбросы. "
        "На master пока не зарегистрирован.",
        tags=("shogi", "education"),
    ),
    # --- education-branch board games ---
    _e(
        "gomoku",
        "Гомоку",
        "education_mode",
        "education_branch",
        "Фристайл гомоку 15×15.",
        "На education: ход — постановка камня на пустую клетку; пять и более "
        "в ряд (ортогональ/диагональ) побеждают. Чёрные ходят первыми. "
        "На master пока не зарегистрирован.",
        tags=("board_game", "education"),
    ),
    _e(
        "checkers_education",
        "Шашки (education, опции)",
        "education_mode",
        "education_branch",
        "Конфигурируемые шашки с модификаторами.",
        "На education id семейства checkers+…: mandatory_capture, backward_capture, "
        "flying_king. На master аналог — база draughts без этих чекбоксов.",
        aliases=("checkers",),
        tags=("board_game", "education"),
    ),
    # --- education / app training (not GameMode factories) ---
    _e(
        "training_maze",
        "Лабиринт фигуры",
        "training",
        "master",
        "Учебный режим: одна фигура съедает все чёрные.",
        "Ветка education UI + app/training/maze на master: герой (конь/слон/ладья/"
        "ферзь/король) берёт все чёрные фигуры; препятствия блокируют. Hard mode "
        "запрещает стоять под боем оставшихся чёрных (они статичны).",
        tags=("education", "training"),
    ),
    _e(
        "training_memory",
        "Тренировка памяти",
        "training",
        "master",
        "Запоминание формы / последовательности / позиции.",
        "app/training/memory: shape (клетки), sequence, position reconstruction. "
        "UI: ui/training/memory_widget.",
        tags=("education", "training"),
    ),
    _e(
        "training_puzzles",
        "Шахматные задачи",
        "training",
        "master",
        "Каталог Lichess puzzles.",
        "app/puzzles + data/puzzles: FEN до хода соперника, UCI-решение. "
        "Ветка education в UI.",
        tags=("education", "training", "puzzles"),
    ),
)

_BY_ID: dict[str, ModeDocEntry] = {}
for _entry in _ENTRIES:
    _BY_ID[_entry.id] = _entry
    for _alias in _entry.aliases:
        _BY_ID.setdefault(_alias, _entry)


def all_mode_docs() -> tuple[ModeDocEntry, ...]:
    return _ENTRIES


def get_mode_doc(mode_id: str) -> ModeDocEntry | None:
    token = mode_id.strip()
    if not token:
        return None
    direct = _BY_ID.get(token)
    if direct is not None:
        return direct
    if "+" not in token:
        return None
    # Prefer documenting the composed id via layer merge in describe_mode_id.
    return None


def describe_mode_id(mode_id: str) -> dict[str, object]:
    """Resolve docs for a preset, base, layer, or ``base+layer`` id."""
    token = mode_id.strip()
    if not token:
        return {"error": "mode id must not be empty"}

    direct = _BY_ID.get(token)
    if direct is not None and "+" not in token:
        return _entry_payload(direct)

    try:
        from chess_core.modes.orchestrator import parse_spec, spec_display_name

        spec = parse_spec(token)
        display_name = spec_display_name(spec)
    except ValueError:
        if direct is not None:
            return _entry_payload(direct)
        return {
            "id": token,
            "availability": "unknown",
            "error": f"no documentation for mode id: {token}",
        }

    base_doc = _BY_ID.get(spec.base)
    layer_docs = [_BY_ID[layer] for layer in sorted(spec.layers) if layer in _BY_ID]
    missing = sorted(layer for layer in spec.layers if layer not in _BY_ID)
    parts: list[str] = []
    if base_doc is not None:
        parts.append(base_doc.rules)
    for layer_doc in layer_docs:
        parts.append(f"[{layer_doc.name}] {layer_doc.rules}")
    summary_bits = []
    if base_doc is not None:
        summary_bits.append(base_doc.summary)
    summary_bits.extend(doc.summary for doc in layer_docs)
    docs_for_avail = ([base_doc] if base_doc else []) + list(layer_docs)
    if not docs_for_avail:
        availability = "unknown"
    elif all(doc.availability == "master" for doc in docs_for_avail):
        availability = "master"
    elif all(doc.availability != "master" for doc in docs_for_avail):
        availability = "education_branch"
    else:
        availability = "mixed"

    return {
        "id": token,
        "encoded_hint": spec.encoded(),
        "kind": "composed" if spec.layers else "base",
        "availability": availability,
        "name": display_name,
        "summary": " | ".join(summary_bits) if summary_bits else token,
        "rules": "\n\n".join(parts) if parts else "No layer docs found.",
        "base": _entry_payload(base_doc) if base_doc else {"id": spec.base},
        "layers": [_entry_payload(doc) for doc in layer_docs],
        "missing_layer_docs": missing,
        "aliases": (),
        "tags": sorted(
            {
                *(base_doc.tags if base_doc else ()),
                *(tag for doc in layer_docs for tag in doc.tags),
            }
        ),
    }


def search_mode_docs(query: str, *, limit: int = 12) -> list[dict[str, object]]:
    needle = query.strip().lower()
    if not needle:
        return []
    hits: list[dict[str, object]] = []
    for entry in _ENTRIES:
        blob = " ".join(
            (
                entry.id,
                entry.name,
                entry.kind,
                entry.availability,
                entry.summary,
                entry.rules,
                " ".join(entry.aliases),
                " ".join(entry.tags),
            )
        ).lower()
        if needle not in blob:
            continue
        hits.append(
            {
                "file": "modes/mode_docs.py",
                "line": entry.id,
                "text": f"{entry.id} ({entry.availability}): {entry.summary}\n{entry.rules}",
            }
        )
        if len(hits) >= limit:
            break
    return hits


def render_modes_markdown() -> str:
    """Full catalog as markdown for docs/MODES.md."""
    lines = [
        "# Режимы Chess_core",
        "",
        "Источник истины для агентов: `chess_core.modes.mode_docs` и MCP "
        "`mode_details` / `list_modes` / `mode_docs`.",
        "",
        "`availability=master` — есть на текущей ветке. "
        "`education_branch` — задокументировано с ветки `education`, на master "
        "может быть ещё не подключено.",
        "",
    ]
    by_kind: dict[str, list[ModeDocEntry]] = {}
    for entry in _ENTRIES:
        by_kind.setdefault(entry.kind, []).append(entry)
    order = (
        "base",
        "layer",
        "education_mode",
        "training",
    )
    titles = {
        "base": "Базы (master)",
        "layer": "Слои оркестратора (master)",
        "education_mode": "Режимы ветки education",
        "training": "Учебные активности",
    }
    for kind in order:
        entries = by_kind.get(kind, [])
        if not entries:
            continue
        lines.append(f"## {titles.get(kind, kind)}")
        lines.append("")
        for entry in entries:
            alias = f" (aliases: {', '.join(entry.aliases)})" if entry.aliases else ""
            lines.append(f"### `{entry.id}` — {entry.name}{alias}")
            lines.append("")
            lines.append(f"- **availability:** `{entry.availability}`")
            lines.append(f"- **summary:** {entry.summary}")
            lines.append(f"- **rules:** {entry.rules}")
            if entry.tags:
                lines.append(f"- **tags:** {', '.join(entry.tags)}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _entry_payload(entry: ModeDocEntry) -> dict[str, object]:
    payload = asdict(entry)
    payload["aliases"] = list(entry.aliases)
    payload["tags"] = list(entry.tags)
    return payload

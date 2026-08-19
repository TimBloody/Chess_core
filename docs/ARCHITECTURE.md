# Architecture Draft

Проект делим на слои так, чтобы новые варианты игр, режимы обучения, UI и сеть не зависели друг от друга напрямую.

Ключевое решение: строим не реализацию "классики плюс исключения", а гибкий конфигуратор наборов правил. Режим игры должен задаваться конфигурацией доски, фигур, топологии, стартовой позиции, условий победы и специальных правил.

## 1. Core

Нижний слой: правила, состояние партии и проверка ходов. Здесь не должно быть PyQt, файловой системы, сети или AI.

Основные направления:

- `core.board`: координаты, клетки, доски размера `m x n`, зоны, ориентация.
- `core.pieces`: базовые фигуры, типы движения, промоция, взятие, специальные способности.
- `core.rules`: конфигуратор набора правил: размер доски, фигуры, стартовая позиция, условия победы, промоции, сбросы, ограничения ходов.
- `core.topology`: связность клеток через битовые маски: обычная доска, цилиндрическая доска, порталы и будущие сложные топологии.
- `core.rays`: лучи движения на пустой доске с заданной топологией; база для генерации ходов фигур.
- `core.state`: позиция, очередь хода, права рокировки/сброса/промоции, история.
- `core.movegen`: генерация псевдолегальных и легальных ходов.
- `core.notation`: FEN/SFEN/PGN/USI/UCI-подобные форматы. FEN — `notation.py`, SFEN — `sfen.py`, PGN — `pgn.py`.

Главный принцип: новый вариант игры добавляется через конфигурацию/ruleset, а не через ветвления по всему ядру.

Примеры, которые архитектура должна поддерживать без глобальных переписываний:

- классические шахматы на `8 x 8`;
- шахматы Капабланки на `10 x 8`;
- киото-сёги на `5 x 5`;
- цилиндрические шахматы;
- варианты с порталами и другой нестандартной связностью клеток.

## 2. Application

Сценарии поверх ядра. Этот слой знает, что такое партия, редактор, задача, упражнение или тренировка, но не рисует UI напрямую.

Примеры модулей:

- `app.game`: обычная локальная партия.
- `app.editor`: редактор доски и экспорт/импорт позиции.
- `app.puzzles`: загрузка задач из FEN/SFEN и проверка решений.
- `app.training`: детские упражнения, лабиринты, запоминалки клеток и позиций.
- `app.tournament`: жеребьёвки и турнирные сценарии.
- `app.rating`: чистые Elo-формулы, политики K-фактора и воспроизводимые симуляции.

## 3. Infrastructure

Внешний мир: сохранение файлов, локальная сеть, движки, распознавание бланков, упаковка в exe.

Примеры модулей:

- `infra.storage`: профили, настройки, базы задач, сохранённые партии.
- `infra.network`: локальный сервер, клиентские подключения, синхронизация состояния.
- `infra.engines`: UCI/USI-движки и будущие AlphaZero-подобные эксперименты.
- `infra.vision`: распознавание шахматных бланков.
- `infra.packaging`: сборка exe.

## 4. UI

PyQt-слой. UI получает состояние и команды из application-слоя, но не содержит правил игры.

Примеры модулей:

- `ui.widgets.board`: отображение доски, фигур, подсветок.
- `ui.windows`: окна игры, редактора, задач, настроек.
- `ui.assets`: загрузка изображений из `assets`.
- `ui.experiments`: интерактивные исследовательские дашборды на PyQtGraph.

## 5. Dependency Rule

Зависимости должны идти только сверху вниз:

`ui -> application -> core`

`infrastructure -> application/core`

`core` ни от кого не зависит.

Это позволит менять интерфейс, сеть, форматы задач и AI без поломки правил, а изменения в низком уровне отслеживать через тесты ядра.

## 6. Testing Strategy

Минимальный набор тестов для защиты от поломок:

- unit-тесты для правил движения каждой фигуры;
- тесты генерации легальных ходов из контрольных позиций;
- тесты FEN/SFEN round-trip;
- тесты особых правил: шах/мат/пат, рокировка, en passant, промоция, сбросы в сёги;
- contract-тесты для каждого ruleset;
- интеграционные тесты application-сценариев без UI.

## 7. Package Layout (scaffold)

Исходники лежат в `src/chess_core/`:

| Путь | Назначение |
|------|------------|
| `core/board.py` | `Square`, `BoardShape`, `Board` (`m x n`) |
| `core/bitboard.py` | `BitMask`, `BitboardSet` |
| `core/topology.py` | `FlatTopology`, `CylindricalFilesTopology`, `PortalTopology` |
| `core/rays.py` | `Ray`, `RayTable`, `RayBuilder` |
| `core/piece.py` | `Piece`, `PieceType`, `PieceCatalog`, `PieceTransform`, `MovePatternResolver` |
| `core/move.py` | `MoveAction`, `DropAction`, `Turn`, duck `PlaceBlockerAction` |
| `core/turn.py` | `TurnScenario`, `TurnStep`, `TurnPolicy`, `StaticTurnPolicy` |
| `core/rules.py` | `VictoryCondition` (`threshold`, `target_zone_mask`), `DropRule`, `PromotionRule`, `LegalityRule`, `CastlingRule`/`CastlingPath` |
| `core/gamemode.py` | `GameMode`, `GameModeBuilder` (`turn_policy`, `move_resolver`, `is_dummy`, `modifier_ids`) |
| `core/registry.py` | `GameModeRegistry`; `get("chess+fairytale+three_check")` собирает compose |
| `core/movegen.py` | leap/slide/pawn; patterns через `move_resolver` если задан; фильтр шаха при `CHECKMATE`/`KING_REACHES_ZONE`/`THREE_CHECK` |
| `modes/chess.py` | classic, chess960, crazyhouse, giveaway*, minichess*, cylindrical, duck, two_move, fairytale, three_check, king_of_the_hill, three_check_king_of_the_hill |
| `modes/variant_composition.py` | `compose_chess_mode`, оси SETUP/TOPOLOGY/DROPS/TURN/MOVEMENT/VICTORY |
| `modes/three_check_rules.py` | `ThreeCheckCounter` |
| `modes/koth_rules.py` | `center_zone_mask` (d4/e4/d5/e5) |
| `modes/fairytale_rules.py` | `FairytaleFileResolver` |
| `modes/two_move_rules.py` | `DoubleMoveTurnPolicy` |
| `modes/chess_rules.py` | `ChessPromotionRule` (пешка на последней горизонтали) |
| `modes/crazyhouse_rules.py` | `CrazyhouseDropRule` (пешки не на 1-й/8-й) |
| `modes/shogi_rules.py` | `ShogiDropRule`, `ShogiPromotionRule`, `KyotoFlipTransform`, `KyotoDropRule`, `facing_start_cells` |
| `modes/shogi.py` | shogi, minishogi, kyoto_shogi, dobutsu_shogi |
| `app/editor.py`, `puzzles.py`, `memory.py` | сценарии без UI |
| `app/training/` | запоминание (фигура/последовательность/позиция) и лабиринт фигуры |
| `ui/training/` | страница «Обучение» |
| `infra/network.py` | `GameServer` / `GameClient` протоколы |
| `infra/pgn_storage.py` | запись ChessBase-compatible PGN с metadata tags в `output/` |
| `ui/pgn_viewer.py` | вставка и пошаговый просмотр PGN, временные analysis-ветки |
| `ui/theme.py` | оболочка, подписи режимов, иконка окна |
| `tools/mask_builder.py` | сборщик масок и ray-таблиц |
| `tools/pgn_database.py` | объединение отдельных PGN в multi-game PGN-базу |
| `data/masks/` | `flat_8x8.json`, `cylinder_8x8.json` |

Расширение нового режима: собрать `GameMode` через `GameModeBuilder`, зарегистрировать в `registry`, не добавлять `if mode.id == ...` в `movegen`.

Рабочие шахматные варианты v1 (не заглушки):

- **Chess960** — `chess960(position_id)`; `None` = случайный id 0..959; 518 = классика. Рокировка FIDE: король/ладья на c/d или g/f.
- **Crazyhouse** — `MOVE_OR_DROP` + рука; пешку нельзя сбросить на 1-ю/8-ю; превращённая фигура при взятии идёт в руку как пешка (`state["promoted_from"]`).
- **Duck Chess** — ход + `PLACE_BLOCKER`; `KING_CAPTURE` (шаха нет); `lose_on_no_legal_moves=False` — сторона без ходов побеждает. Утка стартует вне доски.

- **Two-move** — белые открывают одним ходом; далее обычно два хода; шах первым ходом обрывает очередь; старт под шахом — один ход (`DoubleMoveTurnPolicy`).
- **Fairytale** — слон/ладья/конь ходят как фигура начальной вертикали (a/h ладья, b/g конь, c/f слон; d/e свой тип); ферзь, король, пешка без смены.
- **Three-check** — доп. победа после трёх шахов (`ThreeCheckCounter`, `VictoryKind.THREE_CHECK`).
- **King of the Hill** — доп. победа королём на d4/e4/d5/e5 (`target_zone_mask`).

Композиция chess-family: `compose_chess_mode(("cylindrical", "three_check"))` или `registry.get("chess+cylindrical+three_check")`. Оси exclusive кроме аддитивных victory. Запрещены duck+two_move и duck+three_check. UI: чекбоксы модификаторов в ModePicker поверх базового режима.

Рабочие сёги v1:

- **Shogi** — 9×9, сбросы (nifu, мёртвые клетки, учифудзумэ), зона промоции 3 ранга, мат короля.
- **Minishogi** — 5×5, те же сбросы, зона промоции 1 ранг.
- **Kyoto shogi** — 5×5, flip-after-move, дроп любой стороной фишки, без nifu/учифу.
- **Dobutsu shogi** — 3×4, льва можно взять; безопасный try на последней горизонтали; цыплёнок → курица.

Во всех сёги-режимах sente = `PieceSide.BLACK` (фигуры на последней горизонтали, ход чёрных, вид от чёрных, SVG Lishogi `0*`/`1*`).

`*` — фабрика есть, полный ruleset ещё dummy (giveaway, minichess).

**TurnScenario / TurnPolicy** — фиксированная или динамическая длина хода (duck: ход + утка; двухходовки: 1 или 2 `MoveAction`).

**PieceTransform** — смена эффективного типа/стороны фигуры после хода (киото-сёги: обязательный flip пары, кроме короля).

**VictoryCondition** — мат, взятие короля, «царь горы» (зона), и т.д.

**Маски**: топология → `RayBuilder` → таблицы в `data/masks/` или `GameMode.mask_tables`.

Установка пакета для разработки: `pip install -e .` из корня (`pyproject.toml`).

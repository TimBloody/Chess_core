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
- `core.notation`: FEN/SFEN/PGN/USI/UCI-подобные форматы.

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

## 7. Package Layout

Исходники лежат в `src/chess_core/`. `MoveGenerator` рабочий, не заглушка.

| Путь | Назначение |
|------|------------|
| `core/board.py` | `Square`, `BoardShape`, `Board` (`m x n`) |
| `core/bitboard.py` | `BitMask`, `BitboardSet` |
| `core/topology.py` | `FlatTopology`, `CylindricalFilesTopology`, `PortalTopology` |
| `core/rays.py` | `Ray`, `RayTable`, `RayBuilder` |
| `core/piece.py` | `Piece`, `PieceType`, `PieceCatalog`, `PieceTransform` |
| `core/move.py` | `MoveAction`, `DropAction`, `Turn`, duck `PlaceBlockerAction` |
| `core/turn.py` | `TurnScenario`, `TurnStep` — несколько действий в одном ходе |
| `core/rules.py` | `VictoryCondition`, `DropRule`, `PromotionRule`, `LegalityRule`, `CaptureSink` |
| `core/gamemode.py` | `GameMode`, `GameModeBuilder` |
| `core/state.py` | `GameState`, `HandsState`; ходы коммитятся через `GameState.apply_turn` |
| `core/notation.py` | FEN, UCI (`parse_uci` / `format_uci`), текстовая нотация хода |
| `core/chess960.py` | стартовые позиции 960 и рокировка «король на ладью» |
| `core/registry.py` | `GameModeRegistry` |
| `core/movegen.py` | `MoveGenerator` |
| `modes/chess.py` | classic, 960, crazyhouse, giveaway, minichess, cylindrical, duck |
| `modes/shogi.py` | shogi, kyoto_shogi, dobutsu_shogi |
| `modes/bughouse.py`, `hand_and_brain.py` | парные сетевые режимы |
| `app/game.py` | `LocalGameService`, статусы партии |
| `app/editor.py` | редактор позиции |
| `app/puzzles.py` | Lichess FEN/UCI-каталог и `PuzzleSession` |
| `app/training/memory.py` | запоминалки: клетки / последовательность / позиция |
| `app/tournament/` | жеребьёвки |
| `app/match.py`, `seats.py`, `network_game.py` | матч, лобби, сетевая партия |
| `infra/network.py`, `tcp_*.py`, `lan.py` | LAN-сервер и клиент |
| `infra/engines/` | UCI/USI discovery и процесс |
| `infra/storage/lichess_puzzles.py` | загрузка CSV/JSON каталога задач |
| `infra/paths.py` | assets / masks / puzzles / engines для dev и frozen exe |
| `ui/app_entry.py`, `main_window.py` | оболочка: локальная игра, сеть, редактор, жеребьёвка, задачи, память |
| `ui/widgets/` | доска, карман, часы, eval-bar, лобби, SVG-палитра редактора |
| `tools/mask_builder.py` | сборщик масок и ray-таблиц |
| `data/masks/` | сгенерированные таблицы |
| `data/puzzles/lichess_mini.csv` | офлайн-набор задач Lichess (CC0) |

Расширение нового режима: собрать `GameMode` через `GameModeBuilder`, зарегистрировать в `registry`, не добавлять `if mode == ...` в `movegen`.

**TurnScenario** — порядок и число действий за ход (duck: ход + утка; двухходовки: два `MoveAction`).

**PieceTransform** — смена эффективного типа/стороны фигуры после хода (киото-сёги: обязательный flip пары, кроме короля).

**VictoryCondition** — мат, взятие короля, «царь горы» (зона), материал (giveaway).

**Маски**: топология → `RayBuilder` → таблицы в `data/masks/` или `GameMode.mask_tables`.

Не реализовано и не трогать без запроса: Капабланка 10×8, портальная топология, лабиринты, распознавание бланков, AlphaZero.

Установка пакета для разработки: `pip install -e .` из корня (`pyproject.toml`). Точка входа UI: `python -m chess_core.ui.app_entry`. Бинарники движков не входят в репозиторий и не пакуются в exe; см. `docs/ENGINES.md`.

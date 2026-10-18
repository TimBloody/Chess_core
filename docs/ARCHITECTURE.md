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

- `app.game`: обычная локальная партия, журнал ходов и экспорт записи (`export_transcript`) для любого режима — PGN, совместимый с ChessBase 16.
- `app.pgn_database`: сбор партий из папки в `.pgn` базу и дописывание в существующую базу.
- `app.editor`: редактор доски и экспорт/импорт позиции.
- `app.puzzles`: загрузка задач из FEN/SFEN и проверка решений.
- `app.training`: детские упражнения, лабиринты для отработки ходов фигур, запоминалки клеток и позиций.
- `app.experiments`: модель Эло и OCR шахматного бланка. Сетка — stage12 соседнего OCR; символы — свой MSER на холсте MNIST 28×28. Чтение глифов CNN ещё не подключено. Идея OCR: лёгкая CNN с точностью большой модели за счёт языка шахматной нотации (какие ходы в позиции возможны) и сверки двух бланков — записи белых и записи чёрных.
- `app.tournament`: менеджер турнира (Swiss Dutch 2026 / Berger), без правил конкретной игры.
- `app.engine.py` - `EngineAnalysisService.for_mode`
- `app.search.py` - встроенный alpha-beta dummy
- `app.engine_catalog.py` - привязка режима к Stockfish / Fairy-Stockfish / YaneuraOu / minimax

## 3. Infrastructure

Внешний мир: сохранение файлов, локальная сеть, движки, упаковка в exe.

Примеры модулей:

- `infra.storage`: профили, настройки, базы задач, сохранённые партии и PGN-базы (UTF-8 BOM + CRLF для ChessBase 16).
- `infra.network`: локальный сервер, клиентские подключения, синхронизация состояния.
- `infra.engines`: UCI/USI-движки и будущие AlphaZero-подобные эксперименты.
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
| `core/state.py` | `GameState`, `HandsState`; ходы коммитятся через `GameState.apply_turn`; `repetition_log` |
| `core/repetition.py` | ключ позиции и троекратное повторение (сторона, доска/стопки, карманы, рокировка, EP) |
| `core/notation.py` | FEN, UCI (`parse_uci` / `format_uci`), текстовая нотация хода |
| `core/pgn.py` | разбор/запись PGN партий и баз (Seven Tag Roster, ChessBase 16) |
| `core/chess960.py` | стартовые позиции 960 и рокировка «король на ладью» |
| `core/registry.py` | `GameModeRegistry` |
| `core/movegen.py` | `MoveGenerator` (через `mode.move_resolver`, если задан) |
| `modes/orchestrator.py` | композиция базы и слоёв (`chess+fairy+giveaway`); совместимость чекбоксов |
| `modes/mode_docs.py` | каталог правил для MCP / `docs/MODES.md` (master + education) |
| `modes/fairytale_rules.py` | `FairytaleFileResolver` — ходы ладьи/слона/коня по файлу |
| `modes/chess.py` | classic, 960, crazyhouse, giveaway, minichess, cylindrical, duck |
| `modes/shogi.py` | shogi, kyoto_shogi, dobutsu_shogi |
| `modes/board_games.py` | reversi, corners, draughts |
| `modes/gobblet.py` | Gobblet Gobblers 3×3 |
| `modes/bughouse.py`, `hand_and_brain.py` | парные сетевые режимы |
| `app/game.py` | `LocalGameService`, статусы партии, `export_transcript` для любого режима |
| `app/game_record.py` | журнал `Turn`, навигация по revision, `format_transcript` (PGN) |
| `app/pgn_database.py` | объединение партий в `.pgn` базу и append |
| `app/editor.py` | редактор позиции |
| `app/puzzles.py` | Lichess FEN/UCI-каталог и `PuzzleSession` |
| `app/training/memory.py` | запоминалки: клетки / последовательность / позиция |
| `app/training/maze.py` | лабиринт: цепочка взятий с приманками; порядок важен из‑за боя |
| `app/experiments/elo.py` | модель рейтинга Эло для ветки экспериментов |
| `app/experiments/ocr.py` | OCR бланка: сетка stage12 соседнего проекта, свой MSER, глифы 28×28 |
| `app/experiments/ocr_glyphs.py` | классы глифов и инверсия EMNIST; `Кр` не класс |
| `tools/train_glyph_cnn.py` | CUDA CNN по EMNIST + кириллица; зачёркивания и толщина штриха |
| `app/tournament/` | Swiss Manager-аналог: Dutch 2026, Berger, ½ bye, кросс-таблица, TRF/Excel |
| `app/match.py`, `seats.py`, `network_game.py` | матч, лобби, сетевая партия |
| `infra/network.py`, `tcp_*.py`, `lan.py` | LAN-сервер и клиент |
| `infra/engines/` | UCI/USI discovery и процесс; встроенный поиск — `app/search.py` |
| `infra/storage/lichess_puzzles.py` | загрузка CSV/JSON каталога задач |
| `infra/storage/pgn_files.py` | чтение/запись PGN: UTF-8 BOM, CRLF, папки `.pgn`/`.txt` |
| `infra/storage/tournament_files.py` | JSON-снимки турнира (`version`, атомарная запись) |
| `infra/paths.py` | assets / masks / puzzles / engines для dev и frozen exe |
| `ui/app_entry.py`, `ui/hub.py` | ярлык/exe: общее меню; ветки открываются отдельными окнами |
| `ui/shell.py`, `ui/branches/` | ленивые окна: local_play, server_play, education, tournament, experiments |
| `ui/pgn_database.py` | обучение → «Базы»: папка партий → новая/существующая `.pgn` база |
| `ui/tournament.py` | турнир: вкладки игроки/пары/таблица/кросс-таблица/журнал |
| `ui/training/maze_widget.py` | лабиринт в ветке обучения |
| `ui/widgets/` | доска, карман, часы, eval-bar, лобби, SVG-палитра, диалоги турнира |
| `tools/mask_builder.py` | сборщик масок и ray-таблиц |
| `data/masks/` | сгенерированные таблицы |
| `tools/fetch_lichess_puzzles.py` | семпл официального дампа Lichess в `lichess_catalog.csv` |
| `data/puzzles/lichess_catalog.csv` | офлайн-каталог задач Lichess по темам (CC0) |
| `data/puzzles/lichess_mini.csv` | крошечный запасной набор, если каталога нет |

Расширение нового режима: собрать `GameMode` через `GameModeBuilder` или слой в `modes/orchestrator.py`, зарегистрировать базу в registry. Не добавлять `if mode == ...` в `movegen`.

**TurnScenario** — порядок и число действий за ход (duck: ход + утка; двухходовки: два `MoveAction`).

**PieceTransform** — смена эффективного типа/стороны фигуры после хода (киото-сёги: обязательный flip пары, кроме короля).

**VictoryCondition** — мат, взятие короля, «царь горы» (зона), материал (giveaway).

**Маски**: топология → `RayBuilder` → таблицы в `data/masks/` или `GameMode.mask_tables`.

Не реализовано и не трогать без запроса: Капабланка 10×8, портальная топология, AlphaZero.

Установка пакета для разработки: `pip install -e .` из корня (`pyproject.toml`). Точка входа UI: `python -m chess_core.ui.app_entry`. Бинарники движков не входят в репозиторий и не пакуются в exe; см. `docs/ENGINES.md`.

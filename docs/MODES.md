# Режимы Chess_core

Источник истины для агентов: `chess_core.modes.mode_docs` и MCP `mode_details` / `list_modes` / `mode_docs`.

`availability=master` — есть на текущей ветке. `education_branch` — задокументировано с ветки `education`, на master может быть ещё не подключено.

## Базы (master)

### `chess` — Классика (aliases: classic_chess)

- **availability:** `master`
- **summary:** Стандартные шахматы 8×8.
- **rules:** Плоская доска 8×8, обычные фигуры, один ход за раз, шахи включены, победа — мат. Рокировка, взятие на проходе, превращение по правилам ФИДЕ. Alias id: classic_chess.
- **tags:** chess, fide

### `minichess` — Мини-шахматы

- **availability:** `master`
- **summary:** Gardner minichess 5×5.
- **rules:** Доска 5×5, фигуры как в классике (урезанный старт). Победа — мат. Внешний движок: Fairy-Stockfish UCI_Variant=gardner.
- **tags:** chess, mini

### `shogi` — Сёги

- **availability:** `master`
- **summary:** Стандартные сёги 9×9.
- **rules:** Доска 9×9, сбросы из руки, зона превращения 3 ряда, шахи/мат. Нотация SFEN/USI; движок YaneuraOu, иначе Fairy-Stockfish.
- **tags:** shogi

### `kyoto_shogi` — Киото-сёги

- **availability:** `master`
- **summary:** Киото-сёги: переворот фигуры после каждого хода.
- **rules:** Малая доска сёги с парами лиц (например конь/серебро). После хода фигура меняет лицо. Сбросы с выбором лица. Fairy-Stockfish kyotoshogi.
- **tags:** shogi

### `dobutsu_shogi` — Добуцу-сёги

- **availability:** `master`
- **summary:** Добуцу (зверюшки) 3×4.
- **rules:** Лев, жираф, слон, цыплёнок/курица. Победа: взять льва или безопасно дойти львом до последней линии. Fairy-Stockfish dobutsu.
- **tags:** shogi, mini

### `reversi` — Реверси

- **availability:** `master`
- **summary:** Отелло/реверси 8×8.
- **rules:** Ход — сброс фишки на пустую клетку с переворотом зажатых чужих. Победа по большинству фишек. Fairy-Stockfish flipello.
- **tags:** board_game

### `corners` — Уголки

- **availability:** `master`
- **summary:** Уголки: довести свои шашки в противоположный угол.
- **rules:** Ходы и прыжки по своим правилам уголкам; победа по размещению. Встроенный alpha-beta.
- **tags:** board_game

### `draughts` — Шашки (aliases: checkers)

- **availability:** `master`
- **summary:** Русские шашки 8×8.
- **rules:** Простые и дамки, взятия по диагонали, обязательное взятие через MustCaptureLegality. Победа по материалу / отсутствию ходов. Встроенный alpha-beta (не Scan 10×10).
- **tags:** board_game, draughts

### `gobblet` — Gobblet Gobblers

- **availability:** `master`
- **summary:** Gobblet 3×3 со стопками.
- **rules:** Три размера фишек, накрывание, линия из трёх своих верхних фишек. Движок: app/gobblet_engine (книга + tablebase + поиск).
- **tags:** board_game, gobblet

### `hasami_shogi` — Хасами сёги

- **availability:** `master`
- **summary:** Хасами сёги 6×6.
- **rules:** Доска 6×6; по одному ряду фигур (пешки сёги) на 1-й и 6-й горизонталях. Ходят как ладья (ортогональный слайд без прыжков). Взятие custodian: зажать одну или несколько чужих фигур между двумя своими по горизонтали или вертикали своим ходом; зажатые снимаются. Войти между двумя чужими безопасно. Чёрные ходят первыми. Победа, когда у соперника ≤1 фигуры. Встроенный alpha-beta.
- **tags:** board_game, shogi

### `nanai_checkers` — Нанайские шашки

- **availability:** `master`
- **summary:** Нанайские шашки 6×6.
- **rules:** Доска 6×6; белые на 1-й горизонтали, чёрные на 6-й. Ход — на одну клетку ортогонально. Взятие своим ходом: на линии образуется «своя–своя–чужая» (без четвёртой своей перед блоком); чужая снимается. Три своих подряд чужую не берут. Войти напротив двух чужих безопасно. Победа при ≤1 фигуре у соперника. Встроенный alpha-beta.
- **tags:** board_game, draughts

## Слои оркестратора (master)

### `giveaway` — Giveaway

- **availability:** `master`
- **summary:** Антишахматы: обязательное взятие, выигрывает отдавший все фигуры.
- **rules:** Applies to chess/minichess. MustCaptureLegality, checks_enabled=False, VictoryKind.MATERIAL (пустая сторона побеждает), превращение может включать короля. Fairy-Stockfish antichess. Alias preset: giveaway.
- **tags:** chess, layer

### `fairy` — Fairytale (aliases: fairytale)

- **availability:** `master`
- **summary:** Сказочные ходы по файлу (FairytaleFileResolver).
- **rules:** Applies to chess/minichess. Пешка, ферзь и король ходят как обычно. Ладья, слон и конь ходят как фигура стартового ряда текущего файла: a/h → ладья, b/g → конь, c/f → слон; на d/e сохраняют свой тип. Шахи обычные. Alias: fairytale. Движок: встроенный alpha-beta. Исключение: вместе с Duck тот же слой включает fairy_duck_rules (нет шахов, VictoryKind.KING_CAPTURE, Fairy-Stockfish ALLVARS duck) и НЕ ставит FairytaleFileResolver.
- **tags:** chess, layer, movement

### `cylindrical` — Цилиндрические (aliases: cylindrical_chess)

- **availability:** `master`
- **summary:** Цилиндр по вертикалям: a и h соседние.
- **rules:** Applies to chess. CylindricalFilesTopology; лучи с масками cylinder_8x8. Встроенный alpha-beta. Alias: cylindrical_chess.
- **tags:** chess, layer, topology

### `duck` — Duck chess (aliases: duck_chess)

- **availability:** `master`
- **summary:** После хода поставить нейтральную утку-блокер.
- **rules:** Applies to chess/minichess. TurnScenario + PLACE_BLOCKER. Утка в FEN — `*`. По умолчанию шахи/мат как в ядре. Conflicts: bughouse, hand_and_brain. С слоем fairy → правила Fairy Duck (см. fairy).
- **tags:** chess, layer, turn

### `crazyhouse` — Crazyhouse

- **availability:** `master`
- **summary:** Взятые фигуры в руку, сброс вместо хода.
- **rules:** Applies to chess. CaptureSink.MOVER_HAND + CrazyhouseDropRule. Fairy-Stockfish crazyhouse. Conflicts: bughouse.
- **tags:** chess, layer, drops

### `chess960` — Chess960

- **availability:** `master`
- **summary:** Фишеровская случайная расстановка.
- **rules:** Applies to chess. Scharnagl 0..959, рокировка «король на ладью». Stockfish UCI_Chess960.
- **tags:** chess, layer, setup

### `bughouse` — Bughouse

- **availability:** `master`
- **summary:** Парные шахматы на двух досках с подарками.
- **rules:** Applies to chess. Две доски, карман подарков партнёру. Fairy-Stockfish bughouse. Conflicts: duck, hand_and_brain, crazyhouse.
- **tags:** chess, layer, match

### `hand_and_brain` — Hand & Brain

- **availability:** `master`
- **summary:** Один выбирает тип фигуры, второй ходит ею.
- **rules:** Applies to chess. match_kind=hand_and_brain. Conflicts: duck, bughouse. Движок как у классики (Stockfish).
- **tags:** chess, layer, match

## Режимы ветки education

### `three_check` — Три шаха

- **availability:** `education_branch`
- **summary:** Доп. победа: три шаха сопернику.
- **rules:** На ветке education: VictoryKind.THREE_CHECK (порог 3) + обычный мат. Счётчик ThreeCheckCounter. Композируется с другими модификаторами (например three_check_king_of_the_hill). На master пока не зарегистрирован.
- **tags:** chess, victory, education

### `king_of_the_hill` — Царь горы

- **availability:** `education_branch`
- **summary:** Доп. победа: король на центре.
- **rules:** На ветке education: королевская фигура безопасно занимает одну из центральных клеток d4/e4/d5/e5 (8×8). Мат остаётся победой. На master пока не зарегистрирован.
- **tags:** chess, victory, education

### `three_check_king_of_the_hill` — Три шаха + царь горы

- **availability:** `education_branch`
- **summary:** Комбинация three_check и king_of_the_hill.
- **rules:** Preset на education: оба условия победы активны вместе с матом.
- **tags:** chess, victory, education

### `two_move` — Двухходовки

- **availability:** `education_branch`
- **summary:** Обычно два хода подряд за сторону.
- **rules:** На education: белые открывают одним ходом; далее обычно два хода; если первый даёт шах — ход обрывается; если сторона начинает под шахом — только один ход. На master пока не зарегистрирован.
- **tags:** chess, turn, education

### `minishogi` — Мини-сёги

- **availability:** `education_branch`
- **summary:** Сёги 5×5.
- **rules:** На education: 5×5, зона превращения один ряд, иначе стандартные сбросы. На master пока не зарегистрирован.
- **tags:** shogi, education

### `gomoku` — Гомоку

- **availability:** `education_branch`
- **summary:** Фристайл гомоку 15×15.
- **rules:** На education: ход — постановка камня на пустую клетку; пять и более в ряд (ортогональ/диагональ) побеждают. Чёрные ходят первыми. На master пока не зарегистрирован.
- **tags:** board_game, education

### `checkers_education` — Шашки (education, опции) (aliases: checkers)

- **availability:** `education_branch`
- **summary:** Конфигурируемые шашки с модификаторами.
- **rules:** На education id семейства checkers+…: mandatory_capture, backward_capture, flying_king. На master аналог — база draughts без этих чекбоксов.
- **tags:** board_game, education

## Учебные активности

### `training_maze` — Лабиринт фигуры

- **availability:** `master`
- **summary:** Учебный режим: одна фигура съедает все чёрные.
- **rules:** Ветка education UI + app/training/maze на master: герой (конь/слон/ладья/ферзь/король) берёт все чёрные фигуры; препятствия блокируют. Hard mode запрещает стоять под боем оставшихся чёрных (они статичны).
- **tags:** education, training

### `training_memory` — Тренировка памяти

- **availability:** `master`
- **summary:** Запоминание формы / последовательности / позиции.
- **rules:** app/training/memory: shape (клетки), sequence, position reconstruction. UI: ui/training/memory_widget.
- **tags:** education, training

### `training_puzzles` — Шахматные задачи

- **availability:** `master`
- **summary:** Каталог Lichess puzzles.
- **rules:** app/puzzles + data/puzzles: FEN до хода соперника, UCI-решение. Ветка education в UI.
- **tags:** education, training, puzzles

# Scan 3.1

Открытый движок **международных шашек** (international draughts, доска 10×10, 20 шашек с каждой стороны).

- Исходники: [github.com/rhalbersma/scan](https://github.com/rhalbersma/scan) (зеркало Fabien Letouzey)
- Windows-пакет: [scan_31.zip](https://hjetten.home.xs4all.nl/scan/scan_31.zip) с хостинга, указанного в README репозитория
- Локальный файл: `scan.exe`
- Лицензия: GPLv3
- Протокол: **Hub 2** (не UCI). Для GUI-режима процесс запускают как `scan.exe hub`

Это не английские/русские шашки 8×8. Сильного открытого UCI-подобного движка именно для English checkers с готовым exe на GitHub нет: Cake/KingsRow живут как CheckerBoard DLL. Scan — стандартный открытый движок шашек с текстовым протоколом.

В комплекте есть opening book и eval-веса (`data/`). 6-фигурные bitbase-таблицы (~700 МБ) **не скачаны**: в `scan.ini` стоит `bb-size = 0`. Движок играет и без них, эндшпиль слабее. Таблицы: <https://hjetten.home.xs4all.nl/scan/scan.html>.

## Запуск

Рабочий каталог **обязан** быть папкой Scan: оттуда читаются `scan.ini` и `data/`.

```text
scan.exe hub
```

Без аргумента `hub` открывается интерактивная консоль, а не протокол для программы.

## Протокол Hub 2

Полное описание — в `protocol.txt`. Краткий сеанс анализа:

```text
hub
→ id name=Scan version=3.1 ...
→ param name=variant value=normal ...
→ wait
init
→ ready
pos pos=Wbbbbbbbbbbbbbbbbbbbbeeeeeeeeeewwwwwwwwwwwwwwwwwwww
level move-time=1
go think
→ info ...
→ done move=32-28
quit
```

Позиция: 1 символ стороны (`W`/`B`) + 50 символов клеток в стандартной нумерации шашек:

- `w` / `b` — простая белая / чёрная
- `W` / `B` — дамка
- `e` — пусто

Тихие ходы: `32-28`. Взятия: `28x19x23` (все взятые шашки, без пробелов).

Варианты `scan.ini` / `set-param name=variant`:

- `normal` — международные шашки
- `killer`, `bt`, `frisian`, `losing`

В проекте ещё нет клиента Hub. Пока вызывайте Scan через `subprocess`, как ниже.

## Запрос из Python

```python
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[3] / "engines" / "public" / "scan"
proc = subprocess.Popen(
    [str(root / "scan.exe"), "hub"],
    cwd=root,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    bufsize=1,
)
assert proc.stdin and proc.stdout

def send(line: str) -> None:
    proc.stdin.write(line + "\n")
    proc.stdin.flush()

def wait_token(token: str) -> list[str]:
    lines: list[str] = []
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("Scan closed stdout")
        line = line.strip()
        lines.append(line)
        if line == token or line.startswith(token + " "):
            return lines

send("hub")
wait_token("wait")
send("init")
wait_token("ready")

start = "Wbbbbbbbbbbbbbbbbbbbbeeeeeeeeeewwwwwwwwwwwwwwwwwwww"
send(f"pos pos={start}")
send("level move-time=1")
send("go think")
for line in wait_token("done"):
    print(line)

send("quit")
proc.wait(timeout=2)
```

Ответ `done move=32-28` — ход, который нужно сыграть. Строки `info` во время поиска можно игнорировать или разбирать как оценку.

Другой режим — DamExchange (`scan.exe dxp`, TCP). Для встраивания в Python удобнее Hub.

Клиент `pydraughts` умеет Hub из коробки (`HubEngine(["scan.exe", "hub"])`), но это внешняя библиотека, не часть `chess_core`.

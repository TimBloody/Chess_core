# Stockfish 18

Официальный UCI-движок для классических шахмат (и Chess960).

- Релиз: [sf_18](https://github.com/official-stockfish/Stockfish/releases/tag/sf_18)
- Архив: `stockfish-windows-x86-64-avx2.zip`
- Локальный файл: `stockfish.exe` (это `stockfish-windows-x86-64-avx2.exe`)
- Лицензия: GPLv3
- Сеть NNUE встроена в бинарник, отдельных eval-файлов не нужно

Нужен CPU с AVX2. Если процесс сразу падает, возьмите более совместимую сборку `stockfish-windows-x86-64.zip` с той же страницы релиза.

## Протокол

Stockfish говорит по **UCI** через stdin/stdout. Типичный сеанс:

```text
uci
→ id name Stockfish 18
→ uciok
isready
→ readyok
position startpos moves e2e4 e7e5
go movetime 500
→ info depth ... score cp ... pv ...
→ bestmove e1e2
quit
```

Позицию можно задать FEN:

```text
position fen rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1
go depth 12
```

Полезные команды: `setoption name Threads value 4`, `setoption name Hash value 128`, `stop`, `quit`.

## Запрос из Python через проект

```python
from chess_core.infra.engines.uci import UciClient
from chess_core.infra.paths import engines_dir

exe = engines_dir() / "public" / "stockfish" / "stockfish.exe"
client = UciClient(str(exe), movetime_ms=500)
client.handshake()
bestmove, info = client.analyze_fen(
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
)
client.shutdown()
print(bestmove, info)
```

Через application-слой:

```python
from chess_core.app.engine import EngineAnalysisService, EngineRequest, SearchLimit
from chess_core.infra.engines.discovery import EngineDescriptor
from chess_core.infra.paths import engines_dir
from chess_core.modes.chess import classic_chess

exe = engines_dir() / "public" / "stockfish" / "stockfish.exe"
service = EngineAnalysisService(
    EngineDescriptor(
        id="stockfish",
        name="Stockfish 18",
        path=exe,
        protocol="uci",
        variants=frozenset({"chess"}),
    )
)
result = service.analyze(
    EngineRequest(classic_chess().initial_state(), SearchLimit(movetime_ms=300))
)
print(result.move_uci, result.evaluation)
```

## Сырой subprocess

```python
import subprocess
from pathlib import Path

exe = Path(__file__).resolve().parents[3] / "engines" / "public" / "stockfish" / "stockfish.exe"
proc = subprocess.Popen(
    [str(exe)],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    bufsize=1,
)
assert proc.stdin and proc.stdout

def send(line: str) -> None:
    proc.stdin.write(line + "\n")
    proc.stdin.flush()

send("uci")
while "uciok" not in proc.stdout.readline():
    pass
send("isready")
while "readyok" not in proc.stdout.readline():
    pass
send("position startpos")
send("go movetime 200")
while True:
    line = proc.stdout.readline().strip()
    print(line)
    if line.startswith("bestmove"):
        break
send("quit")
proc.wait(timeout=2)
```

Ходы в ответе — UCI (`e2e4`, `e7e8q`). Их нужно переводить в `MoveAction` ядра отдельно: движок не знает `GameMode`.

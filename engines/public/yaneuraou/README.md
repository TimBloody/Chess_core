# YaneuraOu V9.00 + Suisho5

USI-движок для стандартных сёги 9×9.

- Движок: [YaneuraOu V9.00 GitHub](https://github.com/yaneurao/YaneuraOu/releases/tag/V9.00)
- Локальный файл: `yaneuraou.exe`  
  это `YaneuraOu_NNUE_halfkp_256x2_32_32-V900Git_AVX2.exe`
- Оценка: [Suisho5 / 水匠5](https://github.com/yaneurao/YaneuraOu/releases/tag/suisho5) → `eval/nn.bin`
- Архитектура сети: NNUE `halfkp_256x2_32_32`
- Лицензия движка: GPLv3. Suisho5 распространяется автором оценки для использования с YaneuraOu.

Это **не** глубокая сеть ふかうら王 (dlshogi/TensorRT). Последний Windows-пакет Fukaurou V9.40 весит гигабайты и требует GPU/ORT. Для USI-интеграции достаточно NNUE.

Рекомендуемый USI-параметр для Suisho5: `FV_SCALE = 24`.

## Протокол

YaneuraOu говорит по **USI** (почти UCI, но для сёги):

```text
usi
→ id name YaneuraOu ...
→ usiok
setoption name FV_SCALE value 24
isready
→ readyok          # загрузка nn.bin может занять несколько секунд
position startpos
go btime 1000 wtime 1000
→ info ...
→ bestmove 2g2f
quit
```

Позиция в SFEN:

```text
position sfen lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1
go byoyomi 1000
```

Ходы USI: `7g7f`, сброс `P*5e`, превращение суффиксом `+`, например `8h2b+`.

`UsiClient` проекта шлёт `go byoyomi {ms}`. Для короткого анализа это надёжнее, чем шахматный `movetime`.

## Запрос из Python через проект

```python
from chess_core.infra.engines.usi import UsiClient
from chess_core.infra.paths import engines_dir

exe = engines_dir() / "public" / "yaneuraou" / "yaneuraou.exe"
client = UsiClient(str(exe), movetime_ms=1000)
client.handshake()  # ждёт usiok / readyok
bestmove, info = client.analyze_sfen(
    "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"
)
client.shutdown()
print(bestmove, info)
```

Рабочий каталог процесса должен позволять найти `eval/nn.bin` рядом с exe. Если `isready` зависает, запускайте процесс с `cwd=exe.parent`.

## Сырой subprocess

```python
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[3] / "engines" / "public" / "yaneuraou"
proc = subprocess.Popen(
    [str(root / "yaneuraou.exe")],
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

send("usi")
while "usiok" not in proc.stdout.readline():
    pass
send("setoption name FV_SCALE value 24")
send("isready")
while "readyok" not in proc.stdout.readline():
    pass
send("position startpos")
send("go byoyomi 1000")
while True:
    line = proc.stdout.readline().strip()
    print(line)
    if line.startswith("bestmove"):
        break
send("quit")
proc.wait(timeout=2)
```

Ходы USI нужно отдельно отображать на `DropAction` / `MoveAction` режима `shogi`. Движок не понимает киото-сёги, dobutsu и minishogi без отдельной сборки.

# Engines

Локальный каталог внешних движков. Он **не входит в Git** (кроме `*.md`) и **не упаковывается в exe**.

```text
engines/
├── public/                 # скачанные общедоступные движки
│   ├── stockfish/          # шахматы, UCI
│   ├── yaneuraou/          # сёги, USI
│   └── scan/               # международные шашки 10x10, Hub
└── custom/                 # собственные движки, которых нет в открытом доступе
```

Искать бинарники приложение будет так:

1. переменная `CHESS_CORE_ENGINES_DIR`
2. `config/engines.json`
3. эта папка `engines/`

Код протоколов живёт в `src/chess_core/infra/engines/`. Сюда кладутся только exe, модели и книги.

| Движок | Игра | Протокол | Запуск из Python |
|--------|------|----------|------------------|
| Stockfish 18 | классические шахматы | UCI | `UciClient(".../stockfish.exe")` |
| YaneuraOu V9.00 + Suisho5 | сёги | USI | `UsiClient(".../yaneuraou.exe")` |
| Scan 3.1 | международные шашки | Hub | `Popen([scan.exe, "hub"], cwd=...)` |

Подробности и готовые сниппеты — в README каждой папки.

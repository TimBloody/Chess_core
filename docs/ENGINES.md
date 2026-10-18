# External chess engines

Engines are **not** bundled inside the application executable and are **not** committed (`engines/public/` is gitignored). Fetch locally with `engines/_fetch_public.py` if needed.

```powershell
.\.venv\Scripts\python.exe engines/_fetch_public.py
# or a single engine:
.\.venv\Scripts\python.exe engines/_fetch_public.py fairystockfish
```

## Discovery order

1. `CHESS_CORE_ENGINES_DIR` environment variable
2. `Chess_core/engines/public/` (output of `_fetch_public.py`)
3. `Chess_core/engines/`
4. Sibling directory `../engines/` relative to the project folder
5. `config/engines.json` next to the executable

## Mode backends

| Mode | Preferred public engine | Fallback |
|------|-------------------------|----------|
| Classic, Chess960, Hand & Brain | Stockfish (`UCI_Chess960` when needed) | built-in minimax |
| Crazyhouse, Giveaway, Bughouse | Fairy-Stockfish (`UCI_Variant` crazyhouse / antichess / bughouse). Bughouse FEN is `board[pocket] … \| partner`. | built-in minimax |
| Standard shogi | YaneuraOu (USI / SFEN) | Fairy-Stockfish, then minimax |
| Kyoto, Dobutsu | Fairy-Stockfish (`UCI_Variant` kyotoshogi / dobutsu) | built-in alpha-beta |
| Gardner Mini Chess | Fairy-Stockfish (`UCI_Variant=gardner`) | built-in alpha-beta |
| Reversi | Fairy-Stockfish (`UCI_Variant=flipello`, official `variants.ini`) | built-in alpha-beta |
| Duck (checkbox «Правила Fairy Duck») | Fairy-Stockfish ALLVARS (`UCI_Variant=duck`, FEN `*`, moves `e2e4,e4e6`) | built-in alpha-beta |
| Cylindrical, Duck without the checkbox, corners | — | built-in alpha-beta |
| Gobblet | native C++ alpha-beta | built-in Python alpha-beta |
| Russian draughts (8x8) | — | built-in alpha-beta |
| Future Capablanca / portals | — | the same built-in search |

The dummy searcher is a negamax alpha-beta over `MoveGenerator` / `GameState`. It does not live in `core`. Any new `GameMode` (reversi, corners, …) gets a working engine automatically.

Duck chess uses the PyChess/fishnet `ALLVARS` build (`engines/_fetch_public.py fairystockfish-all`).
Official Fairy-Stockfish 14 omits Duck. The Fairy-Stockfish fetch also installs the release's `variants.ini`; discovery passes it
as `VariantPath`, which enables the `flipello` backend used by Reversi.

## Example layout

```text
Chess_core/
└── engines/public/
    ├── stockfish/stockfish.exe
    ├── fairystockfish/fairy-stockfish.exe
    ├── fairystockfish/variants.ini
    ├── fairystockfish-all/fairy-stockfish-all.exe
    ├── yaneuraou/yaneuraou.exe
```

Scan is intentionally not discovered: Scan 3.1 uses Hub protocol and implements
10x10 international draughts, while this project currently has 8x8 Russian draughts.

## Example config

```json
{
  "engines": [
    {
      "id": "stockfish",
      "name": "Stockfish",
      "path": "engines/public/stockfish/stockfish.exe",
      "protocol": "uci",
      "variants": ["chess", "chess960"]
    },
    {
      "id": "fairy-stockfish",
      "name": "Fairy-Stockfish",
      "path": "engines/public/fairystockfish/fairy-stockfish.exe",
      "protocol": "uci",
      "variants": ["crazyhouse", "giveaway", "shogi"]
    }
  ]
}
```

## API

- Application: `chess_core.app.engine.EngineAnalysisService.for_mode(mode)`
- Catalog: `chess_core.app.engine_catalog.resolve_engine`
- Search: `chess_core.app.search.MinimaxEngine`
- Infrastructure: `chess_core.infra.engines.UciClient` / `UsiClient`
- UI: `EngineBridge` on the local-game eval bar. Two-player starts without engine UI: **H** toggles move highlights, **G** / checkbox **Оценка** toggles the eval thermometer. Engine PV/notation is not shown.
- Checkbox **Одиночная игра** plays the engine as the opponent (one side only; no hints on the human turn). Flip the board before checking it to sit as Black. Duck chess uses a second click to place the duck.
- External engines stay as one hidden process (`CREATE_NO_WINDOW` on Windows). Search does not spawn a new console per move.

Tests use `tests/fixtures/mock_uci_engine.py` instead of a real binary. Do not commit engine executables.

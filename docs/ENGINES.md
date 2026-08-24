# External chess engines

Engines are **not** bundled inside the application executable and are **not** committed (`engines/public/` is gitignored). Fetch locally with `engines/_fetch_public.py` if needed.

## Discovery order

1. `CHESS_CORE_ENGINES_DIR` environment variable
2. `config/engines.json` next to the executable
3. Sibling directory `../engines/` relative to the Chess_core project folder (`infra.paths.engines_dir`)

## Example layout

```text
Documents/
├── Chess_core/
│   ├── dist/ChessCore.exe
│   └── config/engines.example.json
└── engines/
    └── stockfish/
        └── stockfish.exe
```

## Example config

```json
{
  "engines": [
    {
      "id": "stockfish",
      "name": "Stockfish",
      "path": "../engines/stockfish/stockfish.exe",
      "protocol": "uci",
      "variants": ["chess"]
    }
  ]
}
```

## API

- Application: `chess_core.app.engine.EngineAnalysisService`
- Infrastructure: `chess_core.infra.engines.UciClient`
- UI bridge: `chess_core.ui.engine_bridge.EngineBridge` (non-blocking via `QThread`)

Tests use `tests/fixtures/mock_uci_engine.py` instead of a real binary.

# External game engines

Engines are **not** bundled inside the application executable.
The local `engines/` directory is ignored by Git because engine binaries,
models, opening books, and training artifacts can be very large.

## Discovery order

1. `CHESS_CORE_ENGINES_DIR` environment variable
2. `config/engines.json` next to the executable
3. `engines/` inside the project root (development) or next to the executable
   (packaged application)

## Local layout

```text
Chess_core/
├── engines/                 # ignored by Git and PyInstaller
│   ├── public/              # downloaded open-source engines
│   │   └── stockfish/
│   │       └── stockfish.exe
│   └── custom/              # engines developed for unsupported variants
│       └── two_move/
├── config/
│   └── engines.example.json
└── src/
```

Keep each engine in its own subdirectory together with its model files,
books, and upstream license. Source code for a handwritten engine belongs in
the normal tracked Python package; only its runtime binary and large data
belong in `engines/custom/`.

## Example config

```json
{
  "engines": [
    {
      "id": "stockfish",
      "name": "Stockfish",
      "path": "../engines/public/stockfish/stockfish.exe",
      "protocol": "uci",
      "variants": ["chess"]
    }
  ]
}
```

Paths in `config/engines.json` should be relative to the `config/` directory.
Use `CHESS_CORE_ENGINES_DIR` when engines are stored elsewhere.

## Packaging rule

Build commands may bundle `assets/` and `src/chess_core/data/masks/`, but must
never add `engines/` as PyInstaller data. Distribute engines separately and
place them in the `engines/` directory after installing the application.

## API

- Application: `chess_core.app.engine.EngineAnalysisService`
- Infrastructure: `chess_core.infra.engines.UciClient`
- UI bridge: `chess_core.ui.engine_bridge.EngineBridge` (non-blocking via `QThread`)

Tests use `tests/fixtures/mock_uci_engine.py` instead of a real binary.

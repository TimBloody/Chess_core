# Lichess puzzles

Bundled catalogs for the in-app puzzle page. The official dump is about 1.5GB uncompressed; we ship a stratified CC0 sample so the UI can run offline.

- Source: [Lichess open database](https://database.lichess.org/#puzzles)
- License: [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)
- Format: official CSV (`PuzzleId,FEN,Moves,...`)
- `FEN` is the position *before* the opponent's last move; the first UCI token in `Moves` is that setup move; the rest is the solution
- `lichess_catalog.csv` — a few thousand puzzles across mate-in-N, forks, pins, skewers, and other Lichess themes (preferred)
- `lichess_mini.csv` — tiny fallback extract

Refresh the catalog (needs `zstandard`)::

    python -m pip install zstandard
    python -m chess_core.tools.fetch_lichess_puzzles

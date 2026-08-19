# Lichess puzzles (mini)

Bundled catalog for the in-app puzzle page. The official dump is about 1.5GB uncompressed; this file is a tiny CC0 extract so the UI can run offline.

- Source: [Lichess open database](https://database.lichess.org/#puzzles) / Hugging Face `Lichess/chess-puzzles`
- License: [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)
- Format: official CSV (`PuzzleId,FEN,Moves,...`)
- `FEN` is the position *before* the opponent's last move; the first UCI token in `Moves` is that setup move; the rest is the solution

Regenerate without downloading the full dump:

```powershell
.\.venv\Scripts\python.exe -m chess_core.tools.fetch_lichess_puzzles --limit 60
```

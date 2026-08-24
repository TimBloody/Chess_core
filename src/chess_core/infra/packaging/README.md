# Packaging notes

Use PyInstaller with bundled assets, mask data, puzzle catalog, and the white-knight icon:

```powershell
pyinstaller --noconfirm `
  --icon "assets/ui/app.ico" `
  --add-data "assets;assets" `
  --add-data "src/chess_core/data/masks;chess_core/data/masks" `
  --add-data "src/chess_core/data/puzzles;chess_core/data/puzzles" `
  play_classic.py
```

`--icon` is what Windows shows on the `.exe` and on a desktop shortcut that points at it. The same file is `assets/ui/app.ico` (Cburnett white knight on a dark square).

External engine binaries must remain outside the bundle in `../engines/`.
See `docs/ENGINES.md`.

# Packaging notes

Use PyInstaller with bundled assets, mask data, puzzle catalog, and the white-knight icon. The product entry is the hub (`app_entry`), not classic-only play:

```powershell
pyinstaller --noconfirm --name chess-core `
  --paths src `
  --icon "assets/ui/app.ico" `
  --add-data "assets;assets" `
  --add-data "src/chess_core/data/masks;chess_core/data/masks" `
  --add-data "src/chess_core/data/puzzles;chess_core/data/puzzles" `
  src/chess_core/ui/app_entry.py
```

`--icon` is what Windows shows on the `.exe` and on a desktop shortcut that points at it. The same file is `assets/ui/app.ico` (Cburnett white knight on a dark square).

External engine binaries must remain outside the bundle in `../engines/`.
See `docs/ENGINES.md`.

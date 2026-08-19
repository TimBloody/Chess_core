# Packaging notes

Use PyInstaller with bundled assets and mask data:

```powershell
pyinstaller --noconfirm `
  --add-data "assets;assets" `
  --add-data "src/chess_core/data/masks;chess_core/data/masks" `
  play_classic.py
```

External engine binaries must remain outside the bundle in the root
`engines/` directory. Never add that directory through `--add-data`; it is
Git-ignored and deployed separately.
See `docs/ENGINES.md`.

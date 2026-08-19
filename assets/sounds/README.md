# Sounds

Put short game-event clips here. The player looks up `assets/sounds/{event}.wav` and **silently skips missing files**, so the UI runs before any clips are added.

## Format

Use **WAV PCM 16-bit, 44100 Hz, mono**. This is what `QSoundEffect` plays reliably in PyQt6.

- Container: `.wav` (not mp3/ogg/aiff)
- Encoding: PCM (uncompressed), **not** IEEE float, **not** ADPCM
- Bit depth: 16-bit
- Sample rate: 44100 Hz (48000 Hz also works)
- Channels: **mono**
- Peak: about −3 dBTP; leave 50–80 ms of silence at the end so clips do not click
- Length: 80–400 ms for moves/captures; up to ~1.2 s for mate/start

## Expected filenames

| File | When it plays |
|------|----------------|
| `game_start.wav` | New game / mode load |
| `move.wav` | Quiet piece move |
| `capture.wav` | Capture (including en passant) |
| `castle.wav` | Castling |
| `drop.wav` | Crazyhouse / drop from hand |
| `promote.wav` | Pawn promotion |
| `duck.wav` | Duck placement |
| `check.wav` | Check (accent on top of the move) |
| `checkmate.wav` | Checkmate / king captured |
| `stalemate.wav` | Stalemate draw |
| `variant_win.wav` | Duck “fowl” / stalemate-win |
| `illegal.wav` | Rejected click |
| `undo.wav` | Undo |

Do not put binaries in git until you are happy with the set. Keep sources (Reaper projects) outside this folder if they are large.

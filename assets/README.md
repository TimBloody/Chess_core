# Assets

Downloaded/created asset sources:

- `lichess/pieces/cburnett/*.svg`: Lichess `cburnett` chess pieces from `lichess-org/lila`, `public/piece/cburnett`.
- `lichess/board/light_square.svg` and `dark_square.svg`: standalone SVG square tiles using the common Lichess brown board colors.
- `lishogi/pieces/standard/kanji_brown/*`: default Lishogi wooden brown kanji pieces from `WandererXII/lishogi`, `ui/@build/pieces/assets/standard/kanji_brown`. Both sides use `0*` wedges; gote is rotated 180°.
- `lishogi/pieces/standard/shogi_bnw/*`: optional stylized black/white Lishogi set from the same repo. Selectable in the UI as «Стилизованные».
- `lishogi/pieces/dobutsu/dobutsu/*`: official Lishogi Dobutsu animal pieces from `WandererXII/lishogi`, `ui/@build/pieces/assets/dobutsu/dobutsu` (`0FU` chick, `0HI` giraffe, `0KA` elephant, `0OU`/`0GY` lion, `0TO` hen).
- `variants/duck.svg`: original simple rubber-duck marker for Duck Chess (not from Lichess).
- `ui/move.svg` and `ui/eraser.svg`: original tool icons for the board editor (move / erase).
- `sounds/`: optional WAV cues; see `sounds/README.md`. Missing files are skipped at runtime.

Check upstream licenses before distributing a packaged executable with these assets.

"""Fairytale chess: file-dependent movement for rook, bishop, and knight."""

from __future__ import annotations

from chess_core.core.board import Square
from chess_core.core.piece import MovePattern, Piece, PieceCatalog, PieceTypeId
from chess_core.modes.catalog import chess_piece_catalog

_FILE_MOVEMENT_TYPE: dict[int, str] = {
    0: "rook",
    7: "rook",
    1: "knight",
    6: "knight",
    2: "bishop",
    5: "bishop",
}

_UNCHANGED_TYPES = frozenset({"pawn", "queen", "king"})


class FairytaleFileResolver:
    """Resolve rook/bishop/knight patterns from the piece's current file."""

    def __init__(self, catalog: PieceCatalog | None = None) -> None:
        self._catalog = catalog or chess_piece_catalog()

    def patterns(
        self, piece: Piece, square: Square, state: object
    ) -> tuple[MovePattern, ...]:
        del state
        resolved = self._resolved_type_name(piece, square.file)
        return self._catalog.get(PieceTypeId(resolved)).patterns

    def _resolved_type_name(self, piece: Piece, file: int) -> str:
        piece_name = piece.piece_type.name
        if piece_name in _UNCHANGED_TYPES or file in (3, 4):
            return piece_name
        return _FILE_MOVEMENT_TYPE[file]

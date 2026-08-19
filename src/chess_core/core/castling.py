"""Configurable castling paths; classic encoding is king two files toward a rook."""

from __future__ import annotations

from chess_core.core.board import Square
from chess_core.core.move import MoveAction
from chess_core.core.piece import PieceSide
from chess_core.core.rules import CastlingPath


class StandardCastlingRule:
    """Orthodox chess: king e-file to g/c, rook h/a to f/d."""

    def paths(self, state: object, side: object) -> tuple[CastlingPath, ...]:
        del state
        if side is PieceSide.WHITE:
            rank = 0
            rights = ("K", "Q")
        elif side is PieceSide.BLACK:
            rank = 7
            rights = ("k", "q")
        else:
            return ()
        return (
            CastlingPath(
                right=rights[0],
                king_from=Square(4, rank),
                king_to=Square(6, rank),
                rook_from=Square(7, rank),
                rook_to=Square(5, rank),
                vacant_files=(5, 6),
                king_path_files=(5, 6),
            ),
            CastlingPath(
                right=rights[1],
                king_from=Square(4, rank),
                king_to=Square(2, rank),
                rook_from=Square(0, rank),
                rook_to=Square(3, rank),
                vacant_files=(1, 2, 3),
                king_path_files=(3, 2),
            ),
        )

    def decode(self, action: MoveAction, state: object) -> CastlingPath | None:
        piece = state.board_state.piece_at(
            action.from_square.index(state.board_state.board.shape.files)
        )
        if piece is None or piece.piece_type.name != "king":
            return None
        for path in self.paths(state, piece.side):
            if encode_castling(path) == action:
                return path
        return None


def encode_castling(path: CastlingPath) -> MoveAction:
    """Encode a castling path as a single king MoveAction."""
    if path.king_from == path.king_to:
        return MoveAction(path.king_from, path.rook_from)
    return MoveAction(path.king_from, path.king_to)


def files_spanned(start: int, end: int) -> tuple[int, ...]:
    lo, hi = (start, end) if start <= end else (end, start)
    return tuple(range(lo, hi + 1))


def vacant_files_for(path_king_from: int, path_king_to: int, rook_from: int, rook_to: int) -> tuple[int, ...]:
    occupied = {path_king_from, rook_from}
    spanned = set(files_spanned(path_king_from, path_king_to)) | set(
        files_spanned(rook_from, rook_to)
    )
    return tuple(sorted(file for file in spanned if file not in occupied))


def king_path_files(king_from: int, king_to: int) -> tuple[int, ...]:
    if king_from == king_to:
        return ()
    step = 1 if king_to > king_from else -1
    return tuple(range(king_from + step, king_to + step, step))

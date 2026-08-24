"""Fischer Random / Chess960 start positions (Scharnagl numbering 0–959)."""

from __future__ import annotations

from chess_core.core.piece import Piece, PieceSide, PieceTypeId

_KNIGHT_PAIRS = (
    (0, 1),
    (0, 2),
    (0, 3),
    (0, 4),
    (1, 2),
    (1, 3),
    (1, 4),
    (2, 3),
    (2, 4),
    (3, 4),
)

CLASSIC_ARRAY_ID = 518


def decode_chess960_back_rank(position_id: int) -> tuple[str, ...]:
    """Return eight piece type names for Chess960 position ``position_id``."""
    if not 0 <= position_id <= 959:
        raise ValueError("Chess960 position id must be in 0..959")

    rest, light_bishop = divmod(position_id, 4)
    rest, dark_bishop = divmod(rest, 4)
    knight_id, queen_index = divmod(rest, 6)

    rank = [""] * 8
    rank[light_bishop * 2 + 1] = "bishop"
    rank[dark_bishop * 2] = "bishop"
    empty = [index for index, name in enumerate(rank) if not name]
    rank[empty[queen_index]] = "queen"
    empty = [index for index, name in enumerate(rank) if not name]
    first, second = _KNIGHT_PAIRS[knight_id]
    rank[empty[first]] = "knight"
    rank[empty[second]] = "knight"
    empty = [index for index, name in enumerate(rank) if not name]
    rank[empty[0]] = "rook"
    rank[empty[1]] = "king"
    rank[empty[2]] = "rook"
    return tuple(rank)


def chess960_rook_files(back_rank: tuple[str, ...]) -> dict[str, int]:
    """Map FIDE castling letters to the starting rook files of ``back_rank``."""
    rook_files = [index for index, name in enumerate(back_rank) if name == "rook"]
    if len(rook_files) != 2:
        raise ValueError("Chess960 back rank must contain two rooks")
    queenside, kingside = rook_files
    return {
        "Q": queenside,
        "K": kingside,
        "q": queenside,
        "k": kingside,
    }


def chess960_start_cells(position_id: int) -> dict[int, Piece]:
    """Standard 8x8 array for Chess960 position ``position_id`` (pawns on 2/7)."""
    back_rank = decode_chess960_back_rank(position_id)
    cells: dict[int, Piece] = {}
    for file, name in enumerate(back_rank):
        cells[file] = Piece(PieceTypeId(name), PieceSide.WHITE)
        cells[56 + file] = Piece(PieceTypeId(name), PieceSide.BLACK)
        cells[8 + file] = Piece(PieceTypeId("pawn"), PieceSide.WHITE)
        cells[48 + file] = Piece(PieceTypeId("pawn"), PieceSide.BLACK)
    return cells

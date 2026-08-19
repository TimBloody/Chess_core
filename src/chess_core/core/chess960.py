"""Fischer Random (Chess960) starting arrays and FIDE castling paths."""

from __future__ import annotations

from collections import Counter

from chess_core.core.board import Square
from chess_core.core.castling import (
    encode_castling,
    king_path_files,
    vacant_files_for,
)
from chess_core.core.move import MoveAction
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import CastlingPath

_LIGHT_BISHOP_FILES = (1, 3, 5, 7)
_DARK_BISHOP_FILES = (0, 2, 4, 6)
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
_VALID_BACK_RANK_COUNTS = Counter(
    {"rook": 2, "knight": 2, "bishop": 2, "queen": 1, "king": 1}
)


def scharnagl_back_rank(position_id: int) -> tuple[str, ...]:
    """8 piece type names left-to-right for White's first rank. Raises ValueError if not in 0..959."""
    if not 0 <= position_id <= 959:
        raise ValueError(f"Chess960 position id must be in 0..959, got {position_id}")

    n0 = position_id
    light_bishop = n0 % 4
    n1 = n0 // 4
    dark_bishop = n1 % 4
    n2 = n1 // 4
    queen_index = n2 % 6
    knight_index = n2 // 6

    rank: list[str | None] = [None] * 8
    rank[_LIGHT_BISHOP_FILES[light_bishop]] = "bishop"
    rank[_DARK_BISHOP_FILES[dark_bishop]] = "bishop"

    empty = [file for file, name in enumerate(rank) if name is None]
    rank[empty[queen_index]] = "queen"

    empty = [file for file, name in enumerate(rank) if name is None]
    first, second = _KNIGHT_PAIRS[knight_index]
    rank[empty[first]] = "knight"
    rank[empty[second]] = "knight"

    empty = [file for file, name in enumerate(rank) if name is None]
    rank[empty[0]] = "rook"
    rank[empty[1]] = "king"
    rank[empty[2]] = "rook"

    return tuple(name for name in rank if name is not None)


def chess960_start_cells(position_id: int) -> dict[int, Piece]:
    """Row-major 8x8 cells: back ranks + pawns. Index = rank * 8 + file."""
    back_rank = scharnagl_back_rank(position_id)
    cells: dict[int, Piece] = {}
    for file, name in enumerate(back_rank):
        cells[file] = Piece(PieceTypeId(name), PieceSide.WHITE)
        cells[56 + file] = Piece(PieceTypeId(name), PieceSide.BLACK)
        cells[8 + file] = Piece(PieceTypeId("pawn"), PieceSide.WHITE)
        cells[48 + file] = Piece(PieceTypeId("pawn"), PieceSide.BLACK)
    return cells


def chess960_rook_files(back_rank: tuple[str, ...]) -> tuple[int, int]:
    """(queenside_rook_file, kingside_rook_file)."""
    files = tuple(file for file, name in enumerate(back_rank) if name == "rook")
    if len(files) != 2:
        raise ValueError("back rank must contain exactly two rooks")
    return files[0], files[1]


def is_valid_chess960_back_rank(back_rank: tuple[str, ...]) -> bool:
    """Opposite-color bishops, king strictly between two rooks, one Q/K and two N/B/R."""
    if len(back_rank) != 8:
        return False
    if Counter(back_rank) != _VALID_BACK_RANK_COUNTS:
        return False
    bishop_files = [file for file, name in enumerate(back_rank) if name == "bishop"]
    if bishop_files[0] % 2 == bishop_files[1] % 2:
        return False
    rook_files = [file for file, name in enumerate(back_rank) if name == "rook"]
    king_file = back_rank.index("king")
    return rook_files[0] < king_file < rook_files[1]


class Chess960CastlingRule:
    """Duck-typed CastlingRule. Store rook files from the starting array."""

    def __init__(
        self,
        white_rook_files: tuple[int, int],
        black_rook_files: tuple[int, int] | None = None,
    ) -> None:
        self.white_rook_files = white_rook_files
        self.black_rook_files = (
            white_rook_files if black_rook_files is None else black_rook_files
        )

    def paths(self, state: object, side: object) -> tuple[CastlingPath, ...]:
        if side is PieceSide.WHITE:
            rank = 0
            rights = ("K", "Q")
            rook_files = self.white_rook_files
        elif side is PieceSide.BLACK:
            rank = 7
            rights = ("k", "q")
            rook_files = self.black_rook_files
        else:
            return ()

        king_from = _king_on_rank(state, side, rank)
        if king_from is None:
            return ()

        queenside_file, kingside_file = rook_files
        built: list[CastlingPath] = []
        for right, rook_file, king_to_file, rook_to_file in (
            (rights[0], kingside_file, 6, 5),
            (rights[1], queenside_file, 2, 3),
        ):
            path = _path_if_rook_present(
                state,
                side,
                right=right,
                king_from=king_from,
                king_to=Square(king_to_file, rank),
                rook_from=Square(rook_file, rank),
                rook_to=Square(rook_to_file, rank),
            )
            if path is not None:
                built.append(path)
        return tuple(built)

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


def _piece_at(state: object, square: Square) -> Piece | None:
    files = state.board_state.board.shape.files
    return state.board_state.piece_at(square.index(files))


def _king_on_rank(state: object, side: object, rank: int) -> Square | None:
    files = state.board_state.board.shape.files
    for file in range(files):
        square = Square(file, rank)
        piece = _piece_at(state, square)
        if (
            piece is not None
            and piece.piece_type.name == "king"
            and piece.side is side
        ):
            return square
    return None


def _path_if_rook_present(
    state: object,
    side: object,
    *,
    right: str,
    king_from: Square,
    king_to: Square,
    rook_from: Square,
    rook_to: Square,
) -> CastlingPath | None:
    piece = _piece_at(state, rook_from)
    if piece is None or piece.piece_type.name != "rook" or piece.side is not side:
        return None
    return CastlingPath(
        right=right,
        king_from=king_from,
        king_to=king_to,
        rook_from=rook_from,
        rook_to=rook_to,
        vacant_files=vacant_files_for(
            king_from.file, king_to.file, rook_from.file, rook_to.file
        ),
        king_path_files=king_path_files(king_from.file, king_to.file),
    )

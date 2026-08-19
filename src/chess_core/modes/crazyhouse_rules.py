"""Crazyhouse drop restrictions and capture demotion helpers.

Wired by GameMode.drop_rule / capture handling — not by ``if mode.id == ...``.
"""

from __future__ import annotations

from copy import deepcopy

from chess_core.core.piece import Piece, PieceTypeId
from chess_core.core.rules import DropRule, drop_square_is_empty

_PAWN = "pawn"
_PROMOTION_STATE_KEYS = frozenset({"promoted_from", "promoted"})


class CrazyhouseDropRule(DropRule):
    """Orthodox chess drops: empty square; pawns forbidden on first/last rank.

    Crazyhouse is orthodox chess plus drops from the capturer's hand. Encoded here:

    - A drop is legal only onto an empty on-board square (occupied and
      out-of-range indices are rejected without raising).
    - Pawns may not be dropped on rank 0 or the last rank (``ranks - 1``).
    - Other pieces may be dropped on any empty square, including the last rank.
    - There is no shogi-style nifu or uchifuzume ban: drops may give check
      or checkmate.
    - A pawn dropped on its start rank (rank 1 for white, rank ``ranks - 2``
      for black on an 8x8 board) may still use the two-square first move;
      a pawn dropped elsewhere may not. Existing pawn movegen already keys
      off ``start_rank``, so this class does not special-case that.

    ``allowed_faces`` is always ``None``: chess pieces have a single face.
    """

    def can_drop(self, piece_type: PieceTypeId, square_index: int, state: object) -> bool:
        """False if occupied, out of board, or pawn on rank 0 / last rank."""
        if not drop_square_is_empty(state, square_index):
            return False
        if piece_type.name == _PAWN:
            shape = state.board_state.board.shape
            rank = square_index // shape.files
            if rank == 0 or rank == shape.ranks - 1:
                return False
        return True

    def allowed_faces(self, piece_type: PieceTypeId) -> tuple[str, ...] | None:
        """Always None — chess pieces have a single face."""
        del piece_type
        return None


def demote_captured_piece(piece: Piece) -> Piece:
    """Return a new Piece for the hand: if piece.state has promoted_from
    (str piece type name) OR piece.state.get("promoted") is truthy, type becomes pawn.
    Keep the incoming side (HandsState.add already recolors). Clear state after demotion.
    If not promoted, deepcopy-like copy of type+side with state None or copied without promotion flags.
    """
    state = piece.state
    promoted = False
    if state:
        promoted_from = state.get("promoted_from")
        if isinstance(promoted_from, str) or state.get("promoted"):
            promoted = True
    if promoted:
        return Piece(PieceTypeId(_PAWN), piece.side, state=None)
    copied_state = None
    if state:
        copied_state = {
            key: deepcopy(value)
            for key, value in state.items()
            if key not in _PROMOTION_STATE_KEYS
        }
        if not copied_state:
            copied_state = None
    return Piece(PieceTypeId(piece.piece_type.name), piece.side, state=copied_state)


def mark_promoted(piece: Piece, original_type_name: str = "pawn") -> Piece:
    """Return a copy with state['promoted_from']=original_type_name. Used after a promotion move."""
    new_state = {} if piece.state is None else deepcopy(piece.state)
    new_state["promoted_from"] = original_type_name
    return Piece(PieceTypeId(piece.piece_type.name), piece.side, state=new_state)

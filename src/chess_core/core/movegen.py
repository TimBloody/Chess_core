"""Move generation (pseudo-legal and legal)."""

from __future__ import annotations

from collections.abc import Iterator

from chess_core.core.board import Square
from chess_core.core.castling import encode_castling
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Action, DropAction, MoveAction, Turn
from chess_core.core.piece import MovePatternKind, Piece, PieceSide
from chess_core.core.state import GameState


class MoveGenerator:
    def __init__(self, mode: GameMode) -> None:
        self._mode = mode
        self._uchifu_depth = 0
        self._protects = mode.protects_royal()
        self._allows_royal_capture = mode.allows_royal_capture()
        self._catalog_names = {piece_type.id.name for piece_type in mode.pieces.all_types()}

    def _patterns_for(self, piece: Piece, square: Square, state: GameState):
        resolver = self._mode.move_resolver
        if resolver is not None:
            return resolver.patterns(piece, square, state)
        return self._mode.pieces.get(piece.piece_type).patterns

    def generate_pseudo_legal(self, state: GameState) -> list[Action]:
        self._validate_state_shape(state)
        moves: list[Action] = []
        shape = self._mode.board.shape
        for origin_index in range(shape.cell_count):
            moves.extend(self._pseudo_for_index(state, origin_index))
        moves.extend(self._drop_moves(state))
        return moves

    def generate_legal(self, state: GameState) -> list[Action]:
        return self._filter_legal(state, self.generate_pseudo_legal(state))

    def generate_legal_drops(self, state: GameState) -> list[DropAction]:
        """Legal drops only; skips board-move generation."""
        self._validate_state_shape(state)
        return [
            action
            for action in self._filter_legal(state, self._drop_moves(state))
            if isinstance(action, DropAction)
        ]

    def generate_legal_for_square(
        self, state: GameState, square: Square | int
    ) -> list[Action]:
        """Generate legal actions originating only from ``square``.

        King safety is checked exactly as in :meth:`generate_legal`, so pinned
        pieces and mandatory check evasions remain correctly filtered.
        Empty squares also yield legal drops that land on that square.
        """
        self._validate_state_shape(state)
        index = self._square_index(square)
        piece = state.board_state.piece_at(index)
        if piece is None:
            pseudo: list[Action] = list(self._drop_moves_to(state, index))
        else:
            pseudo = self._pseudo_for_index(state, index)
        return self._filter_legal(state, pseudo)

    def has_any_legal(self, state: GameState) -> bool:
        """Return early when the position has at least one legal action."""
        self._validate_state_shape(state)
        if self._mode.legality is not None:
            return bool(self.generate_legal(state))
        shape = self._mode.board.shape
        for index in range(shape.cell_count):
            for action in self._pseudo_for_index(state, index):
                if self._action_is_legal(state, action):
                    return True
        for action in self._drop_moves(state):
            if self._action_is_legal(state, action):
                return True
        return False

    def _filter_legal(
        self, state: GameState, pseudo: list[Action]
    ) -> list[Action]:
        legal = [action for action in pseudo if self._action_is_legal(state, action)]
        if self._mode.legality is not None:
            return self._mode.legality.filter_legal(legal, state)
        return legal

    def _action_is_legal(self, state: GameState, action: Action) -> bool:
        try:
            result = state.apply_turn(
                Turn(state.side_to_move, [action]),
                record_history=False,
                validate_scenario=False,
            )
        except ValueError:
            return False
        if self._protects and self._royal_is_attacked(result, state.side_to_move):
            return False
        return not self._is_illegal_pawn_drop_mate(state, action, result)

    def _pseudo_for_index(self, state: GameState, origin_index: int) -> list[Action]:
        shape = self._mode.board.shape
        piece = state.board_state.piece_at(origin_index)
        if piece is None or piece.side is not state.side_to_move:
            return []
        origin = Square.from_index(origin_index, shape.files, shape.ranks)
        moves: list[Action] = []
        for pattern in self._patterns_for(piece, origin, state):
            if pattern.kind is MovePatternKind.LEAP:
                raw = self._leap_moves(state, piece, origin, pattern.directions)
            elif pattern.kind is MovePatternKind.SLIDE:
                raw = self._slide_moves(state, piece, origin, pattern.directions)
            elif pattern.pattern_key == "pawn":
                raw = self._pawn_moves(state, piece, origin)
            else:
                continue
            moves.extend(self._with_promotion_choices(state, piece, origin, raw))
        if self._mode.piece_is_royal(piece):
            moves.extend(self._castling_moves(state))
        return moves

    def _drop_moves(self, state: GameState) -> list[DropAction]:
        return list(self._iter_drop_moves(state, target_index=None))

    def _drop_moves_to(self, state: GameState, target_index: int) -> list[DropAction]:
        return list(self._iter_drop_moves(state, target_index=target_index))

    def _iter_drop_moves(
        self, state: GameState, *, target_index: int | None
    ) -> Iterator[DropAction]:
        if self._mode.drop_rule is None or state.hands is None:
            return
        shape = self._mode.board.shape
        hand = state.hands.by_side.get(state.side_to_move, ())
        seen: set[str] = set()
        indices: tuple[int, ...]
        if target_index is not None:
            if state.board_state.piece_at(target_index) is not None:
                return
            indices = (target_index,)
        else:
            indices = tuple(
                index
                for index in range(shape.cell_count)
                if state.board_state.piece_at(index) is None
            )
        for piece in hand:
            name = piece.piece_type.name
            if name in seen:
                continue
            seen.add(name)
            faces = self._mode.drop_rule.allowed_faces(piece.piece_type)
            for index in indices:
                if not self._mode.drop_rule.can_drop(piece.piece_type, index, state):
                    continue
                target = Square.from_index(index, shape.files, shape.ranks)
                if faces is None:
                    yield DropAction(piece.piece_type, target)
                    continue
                for face in faces:
                    yield DropAction(piece.piece_type, target, face)

    def _square_index(self, square: Square | int) -> int:
        shape = self._mode.board.shape
        if isinstance(square, Square):
            index = square.index(shape.files)
            if Square.from_index(index, shape.files, shape.ranks) != square:
                raise ValueError("square is outside the game board")
            return index
        if not isinstance(square, int):
            raise TypeError("square must be a Square or integer index")
        Square.from_index(square, shape.files, shape.ranks)
        return square

    def is_in_check(
        self, state: GameState, side: PieceSide | None = None
    ) -> bool:
        """Return whether ``side`` (the side to move by default) is in check."""
        self._validate_state_shape(state)
        return self._royal_is_attacked(state, side or state.side_to_move)

    def is_square_attacked(
        self, state: GameState, square: Square, by_side: PieceSide
    ) -> bool:
        """Public attack-map query used by game status and clients."""
        self._validate_state_shape(state)
        return self._square_attacked(state, square, by_side)

    def is_checkmate(self, state: GameState) -> bool:
        return self.is_in_check(state) and not self.has_any_legal(state)

    def is_stalemate(self, state: GameState) -> bool:
        return not self.is_in_check(state) and not self.has_any_legal(state)

    def _with_promotion_choices(
        self,
        state: GameState,
        piece: Piece,
        origin: Square,
        moves: list[MoveAction],
    ) -> list[MoveAction]:
        rule = self._mode.promotion_rule
        if rule is None:
            return moves
        expanded: list[MoveAction] = []
        files = self._mode.board.shape.files
        from_index = origin.index(files)
        available = self._catalog_names
        for move in moves:
            to_index = move.to_square.index(files)
            may = rule.may_promote(
                piece.piece_type, from_index, to_index, piece.side, state
            )
            must = rule.must_promote(piece.piece_type, to_index, piece.side, state)
            choices = tuple(
                choice
                for choice in (rule.choices(piece.piece_type) if may or must else ())
                if choice.name in available
            )
            if must and choices:
                expanded.extend(
                    MoveAction(move.from_square, move.to_square, choice)
                    for choice in choices
                )
                continue
            expanded.append(MoveAction(move.from_square, move.to_square))
            if may:
                expanded.extend(
                    MoveAction(move.from_square, move.to_square, choice)
                    for choice in choices
                )
        return expanded

    def _is_illegal_pawn_drop_mate(
        self, state: GameState, action: Action, result: GameState
    ) -> bool:
        rule = self._mode.drop_rule
        if rule is None or not getattr(rule, "forbid_pawn_drop_mate", False):
            return False
        if not isinstance(action, DropAction):
            return False
        pawn_types = getattr(rule, "pawn_types", frozenset({"pawn"}))
        if action.piece_type.name not in pawn_types:
            return False
        if self._uchifu_depth:
            return False
        self._uchifu_depth += 1
        try:
            return self.is_checkmate(result)
        finally:
            self._uchifu_depth -= 1

    def _facing(
        self, offset: tuple[int, int], side: PieceSide
    ) -> tuple[int, int]:
        if side is PieceSide.BLACK:
            return (offset[0], -offset[1])
        return offset

    def _leap_moves(
        self,
        state: GameState,
        piece: Piece,
        origin: Square,
        offsets: tuple[tuple[int, int], ...],
    ) -> list[MoveAction]:
        moves: list[MoveAction] = []
        for offset in offsets:
            target = self._mode.topology.step(origin, self._facing(offset, piece.side))
            if target is not None and self._can_land(state, piece, target):
                moves.append(MoveAction(origin, target))
        return moves

    def _slide_moves(
        self,
        state: GameState,
        piece: Piece,
        origin: Square,
        directions: tuple[tuple[int, int], ...],
    ) -> list[MoveAction]:
        moves: list[MoveAction] = []
        for direction in directions:
            for target, occupant in self._walk_ray(state, origin, direction, piece.side):
                if occupant is None:
                    moves.append(MoveAction(origin, target))
                    continue
                if self._can_capture(piece, occupant):
                    moves.append(MoveAction(origin, target))
                break
        return moves

    def _walk_ray(
        self,
        state: GameState,
        origin: Square,
        direction: tuple[int, int],
        side: PieceSide,
    ) -> Iterator[tuple[Square, Piece | None]]:
        files = self._mode.board.shape.files
        step = self._facing(direction, side)
        current = origin
        visited = {origin.index(files)}
        while True:
            target = self._mode.topology.step(current, step)
            if target is None:
                return
            target_index = target.index(files)
            if target_index in visited:
                return
            visited.add(target_index)
            occupant = state.board_state.piece_at(target_index)
            yield target, occupant
            if occupant is not None:
                return
            current = target

    def _pawn_moves(
        self,
        state: GameState,
        piece: Piece,
        origin: Square,
    ) -> list[MoveAction]:
        direction = piece.side.forward_delta()
        start_rank = 1 if piece.side is PieceSide.WHITE else self._mode.board.shape.ranks - 2
        moves: list[MoveAction] = []
        one_step = self._mode.topology.step(origin, (0, direction))
        if one_step is not None and self._is_empty(state, one_step):
            moves.append(MoveAction(origin, one_step))
            two_step = self._mode.topology.step(one_step, (0, direction))
            if (
                origin.rank == start_rank
                and two_step is not None
                and self._is_empty(state, two_step)
            ):
                moves.append(MoveAction(origin, two_step))

        en_passant = state.extras.get("en_passant")
        for file_delta in (-1, 1):
            target = self._mode.topology.step(origin, (file_delta, direction))
            if target is None:
                continue
            occupant = state.board_state.piece_at(
                target.index(self._mode.board.shape.files)
            )
            if (
                occupant is not None and self._can_capture(piece, occupant)
            ) or (
                target == en_passant
                and self._valid_en_passant_victim(state, piece, target)
            ):
                moves.append(MoveAction(origin, target))
        return moves

    def _castling_moves(self, state: GameState) -> list[MoveAction]:
        rule = self._mode.castling_rule
        if rule is None:
            return []
        side = state.side_to_move
        rights = set(state.extras.get("castling_rights", ()))
        if not rights:
            return []
        enemy = side.opponent()
        files = self._mode.board.shape.files
        candidates: list[MoveAction] = []
        for path in rule.paths(state, side):
            if path.right not in rights:
                continue
            king = state.board_state.piece_at(path.king_from.index(files))
            rook = state.board_state.piece_at(path.rook_from.index(files))
            if (
                king is None
                or not self._mode.piece_is_royal(king)
                or king.side is not side
                or rook is None
                or rook.piece_type.name != "rook"
                or rook.side is not side
            ):
                continue
            if self._square_attacked(state, path.king_from, enemy):
                continue
            occupied_ok = True
            for file in path.vacant_files:
                occupant = state.board_state.piece_at(path.king_from.rank * files + file)
                if occupant is None:
                    continue
                occupant_square = Square(file, path.king_from.rank)
                if occupant_square in {path.king_from, path.rook_from}:
                    continue
                occupied_ok = False
                break
            if not occupied_ok:
                continue
            if any(
                self._square_attacked(state, Square(file, path.king_from.rank), enemy)
                for file in path.king_path_files
            ):
                continue
            candidates.append(encode_castling(path))
        return candidates

    def _royal_is_attacked(self, state: GameState, side: PieceSide) -> bool:
        shape = self._mode.board.shape
        enemy = side.opponent()
        for index, piece in state.board_state.iter_occupied():
            if piece.side is not side or not self._mode.piece_is_royal(piece):
                continue
            square = Square.from_index(index, shape.files, shape.ranks)
            if self._square_attacked(state, square, enemy):
                return True
        return False

    def _square_attacked(
        self,
        state: GameState,
        square: Square,
        by_side: PieceSide,
    ) -> bool:
        shape = self._mode.board.shape
        for index, piece in state.board_state.iter_occupied():
            if piece.side is not by_side:
                continue
            origin = Square.from_index(index, shape.files, shape.ranks)
            for pattern in self._patterns_for(piece, origin, state):
                if pattern.pattern_key == "pawn":
                    direction = by_side.forward_delta()
                    if any(
                        self._mode.topology.step(origin, (df, direction)) == square
                        for df in (-1, 1)
                    ):
                        return True
                elif pattern.kind is MovePatternKind.LEAP:
                    if any(
                        self._mode.topology.step(
                            origin, self._facing(offset, piece.side)
                        )
                        == square
                        for offset in pattern.directions
                    ):
                        return True
                elif pattern.kind is MovePatternKind.SLIDE:
                    if self._slider_attacks(
                        state, origin, pattern.directions, piece.side, square
                    ):
                        return True
        return False

    def _slider_attacks(
        self,
        state: GameState,
        origin: Square,
        directions: tuple[tuple[int, int], ...],
        side: PieceSide,
        square: Square,
    ) -> bool:
        for direction in directions:
            for target, _occupant in self._walk_ray(state, origin, direction, side):
                if target == square:
                    return True
        return False

    def _can_land(self, state: GameState, piece: Piece, target: Square) -> bool:
        occupant = state.board_state.piece_at(
            target.index(self._mode.board.shape.files)
        )
        return occupant is None or self._can_capture(piece, occupant)

    def _can_capture(self, piece: Piece, occupant: Piece) -> bool:
        if occupant.side is piece.side or occupant.side is PieceSide.NEUTRAL:
            return False
        if (
            self._mode.piece_is_royal(occupant)
            and self._protects
            and not self._allows_royal_capture
        ):
            return False
        return True

    def _valid_en_passant_victim(
        self, state: GameState, piece: Piece, target: Square
    ) -> bool:
        files = self._mode.board.shape.files
        victim_index = target.index(files) - files * piece.side.forward_delta()
        victim = state.board_state.piece_at(victim_index)
        return (
            victim is not None
            and victim.piece_type.name == "pawn"
            and victim.side is not piece.side
            and victim.side is not PieceSide.NEUTRAL
        )

    def _is_empty(self, state: GameState, square: Square) -> bool:
        return (
            state.board_state.piece_at(square.index(self._mode.board.shape.files))
            is None
        )

    def _validate_state_shape(self, state: GameState) -> None:
        if state.board_state.board.shape != self._mode.board.shape:
            raise ValueError("state board shape does not match game mode")

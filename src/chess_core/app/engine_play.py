"""Apply an engine bestmove as a legal Turn for the current GameMode."""

from __future__ import annotations

from itertools import product

from chess_core.app.engine import BestMove
from chess_core.app.search import legal_turns
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Action, DropAction, MoveAction, PlaceBlockerAction, Turn
from chess_core.core.notation import engine_token_aliases, normalize_engine_token
from chess_core.core.state import GameState
from chess_core.core.turn import StepKind


def resolve_engine_turn(state: GameState, best: BestMove) -> Turn | None:
    """Map an engine result onto a legal ``Turn``, or ``None`` if nothing matches."""
    turns = legal_turns(state, duck_limit=None)
    if not turns:
        return None
    if best.turn is not None:
        matched = _match_stored_turn(best.turn, turns)
        if matched is not None:
            return _ensure_blocker(state, matched)
    tokens = _normalize_tokens(best.move_uci)
    if not tokens:
        return None
    tokens = _normalize_duck_tokens(state, tokens)
    exact = _match_tokens(state, turns, tokens)
    if exact is not None:
        return _ensure_blocker(state, exact)
    if len(tokens) == 1:
        prefix = _match_prefix(state, turns, tokens[0])
        if prefix is not None:
            return _ensure_blocker(state, prefix)
    return None


def _match_stored_turn(stored: Turn, turns: list[Turn]) -> Turn | None:
    for turn in turns:
        if _same_turn(stored, turn):
            return turn
    return None


def _same_turn(left: Turn, right: Turn) -> bool:
    if left.side is not right.side or len(left.actions) != len(right.actions):
        return False
    return all(_same_action(a, b) for a, b in zip(left.actions, right.actions, strict=True))


def _same_action(left: Action, right: Action) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, MoveAction) and isinstance(right, MoveAction):
        return (
            left.from_square == right.from_square
            and left.to_square == right.to_square
            and left.jumped == right.jumped
            and (
                left.promotion_choice == right.promotion_choice
                or left.promotion_choice is None
                or right.promotion_choice is None
            )
        )
    if isinstance(left, DropAction) and isinstance(right, DropAction):
        return (
            left.piece_type == right.piece_type
            and left.to_square == right.to_square
            and (left.face == right.face or left.face is None or right.face is None)
        )
    if isinstance(left, PlaceBlockerAction) and isinstance(right, PlaceBlockerAction):
        return left.square == right.square
    return left == right


def _normalize_tokens(move_uci: str | None) -> tuple[str, ...]:
    if not move_uci:
        return ()
    raw = move_uci.strip().replace(" ", "").replace("·", ",")
    if raw in {"(none)", "none"}:
        return ()
    parts: list[str] = []
    for part in raw.split(","):
        if "@" in part and not part.startswith("@"):
            left, right = part.split("@", 1)
            if len(left) >= 4 and left[0].isalpha() and left[1].isdigit():
                parts.append(left)
                parts.append(f"@{right}")
            else:
                parts.append(part)
        else:
            parts.append(part)
    return tuple(part for part in parts if part)


def _normalize_duck_tokens(
    state: GameState, tokens: tuple[str, ...]
) -> tuple[str, ...]:
    """Map Fairy's ``pieceMove,duckFromDuckTo`` to local move + placement."""
    mode = state.extras.get("mode")
    if not isinstance(mode, GameMode) or mode.id not in {"duck", "duck_chess"}:
        return tokens
    if len(tokens) != 2:
        return tokens
    wall = normalize_engine_token(tokens[1])
    if (
        len(wall) == 4
        and wall[0].isalpha()
        and wall[1].isdigit()
        and wall[2].isalpha()
        and wall[3].isdigit()
    ):
        return tokens[0], f"@{wall[2:4]}"
    return tokens


def _match_tokens(state: GameState, turns: list[Turn], tokens: tuple[str, ...]) -> Turn | None:
    wanted_exact = tuple(token.strip().lower() for token in tokens)
    wanted_norm = tuple(normalize_engine_token(token) for token in tokens)
    exact = _first_unique_hit(turns, state, wanted_exact, normalize=False)
    if exact is not None:
        return exact
    if wanted_norm == wanted_exact:
        return None
    return _first_unique_hit(turns, state, wanted_norm, normalize=True)


def _match_prefix(state: GameState, turns: list[Turn], token: str) -> Turn | None:
    exact = token.strip().lower()
    hit = _unique_prefix_hit(turns, state, exact, normalize=False)
    if hit is not None:
        return hit
    stripped = normalize_engine_token(token)
    if stripped == exact:
        return None
    return _unique_prefix_hit(turns, state, stripped, normalize=True)


def _first_unique_hit(
    turns: list[Turn],
    state: GameState,
    wanted: tuple[str, ...],
    *,
    normalize: bool,
) -> Turn | None:
    hits: list[Turn] = []
    for turn in turns:
        for variant in _turn_labels(state, turn):
            labeled = tuple(
                normalize_engine_token(item) if normalize else item.strip().lower()
                for item in variant
            )
            if labeled == wanted:
                hits.append(turn)
                break
    return hits[0] if len(hits) == 1 else None


def _unique_prefix_hit(
    turns: list[Turn],
    state: GameState,
    needle: str,
    *,
    normalize: bool,
) -> Turn | None:
    hits = []
    for turn in turns:
        for variant in _turn_labels(state, turn):
            if not variant:
                continue
            head = normalize_engine_token(variant[0]) if normalize else variant[0].strip().lower()
            if head == needle:
                hits.append(turn)
                break
    return hits[0] if len(hits) == 1 else None


def _turn_labels(state: GameState, turn: Turn) -> tuple[tuple[str, ...], ...]:
    mode = state.extras.get("mode")
    mode_id = mode.id if isinstance(mode, GameMode) else ""
    shape = state.board_state.board.shape
    variants: list[tuple[str, ...]] = []
    per_action = [
        engine_token_aliases(action, mode_id=mode_id, files=shape.files, ranks=shape.ranks)
        for action in turn.actions
    ]
    if not per_action:
        return ()
    for combo in product(*per_action):
        variants.append(combo)
    return tuple(variants)


def requires_blocker(state: GameState) -> bool:
    mode = state.extras.get("mode")
    if not isinstance(mode, GameMode):
        return False
    return any(step.kind is StepKind.PLACE_BLOCKER for step in mode.turn_scenario.steps)


def _ensure_blocker(state: GameState, turn: Turn) -> Turn:
    if not requires_blocker(state):
        return turn
    if any(isinstance(action, PlaceBlockerAction) for action in turn.actions):
        return turn
    move = next((action for action in turn.actions if isinstance(action, MoveAction)), None)
    if move is None:
        return turn
    return Turn(turn.side, [*turn.actions, PlaceBlockerAction(move.from_square)])

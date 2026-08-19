# Common Game Contracts

Transport-neutral DTOs shared across local play, network sync, clocks, and engines.

## Revision semantics

- `revision: int` — monotonic server/game counter; increases on every committed event (move, undo accept, flag).
- `live_revision` — revision of the current playable position.
- `view_revision` — revision being displayed when browsing history; equals `live_revision` in live play.
- Clients reject stale operations when `base_revision != live_revision`.

## Turn as atomic unit

- One `Turn` = one side's complete action sequence per `TurnScenario`.
- Undo always reverts exactly one completed `Turn`.
- History journal stores `list[Turn]`, not flat actions.

## StateEnvelope

```python
@dataclass(frozen=True)
class StateEnvelope:
    game_id: str
    revision: int
    state: GameState
    clock: ClockSnapshot | None = None
```

## Undo protocol

```python
@dataclass(frozen=True)
class UndoRequest:
    game_id: str
    request_id: str
    session_id: str
    base_revision: int
    plies: int = 1

@dataclass(frozen=True)
class UndoDecision:
    game_id: str
    request_id: str
    session_id: str
    accept: bool

@dataclass(frozen=True)
class UndoResolved:
    game_id: str
    request_id: str
    revision: int
    accepted: bool
    state: GameState | None  # set when accepted
```

Rules:
- Only one pending undo request per game.
- Opponent must confirm; clocks keep running during pending undo.
- On accept: restore previous turn, revision still increases monotonically.

## ClockSnapshot

```python
@dataclass(frozen=True)
class ClockSnapshot:
    revision: int
    running_side: PieceSide | None
    white_remaining_ms: int
    black_remaining_ms: int
    white_byoyomi_left: int
    black_byoyomi_left: int
    server_mono_ms: int
    next_deadline_ms: int | None
    time_control: TimeControlConfig
```

Sync events: connect, start, turn, pause, resume, undo, end.
Heartbeat: every 10–15 s. No per-tick server polling.
The clock is idle (`running_side is None`) until the first committed turn; after that the opponent’s clock runs.

## Engine result

```python
@dataclass(frozen=True)
class EngineEvaluation:
    score_cp: int | None
    mate_in: int | None
    pv: tuple[str, ...]
    depth: int | None = None

@dataclass(frozen=True)
class BestMove:
    move_uci: str | None
    evaluation: EngineEvaluation | None
    error: str | None = None
```

## Notation styles

- `FROM_TO`: `e2-e4`, `g8-f6`
- `PIECE_SQUARE`: `e4`, `Nc6`
- Composite actions within one turn joined by `·`
- Drop: `N@e4`; duck placement: `@e4`
- Duck Chess turn is always `MoveAction` then `PlaceBlockerAction`; undo reverts both together
- Crazyhouse drop is a full `Turn` of one `DropAction` (`MOVE_OR_DROP`)

## Engine discovery

Search order:
1. `CHESS_CORE_ENGINES_DIR` env
2. `config/engines.json` next to executable
3. root `engines/` directory (or `engines/` next to the packaged executable)

Engine binaries and large model files are Git-ignored and never bundled in exe.

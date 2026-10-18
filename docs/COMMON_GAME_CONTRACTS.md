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

## Game transcript (required for every playable mode)

Every finished or in-progress local game must be exportable as plain text. This is a `GameRecord` contract, not a per-mode feature.

- Source of truth: the turn journal (`list[TurnRecord]`), never a UI-only log.
- `LocalGameService.export_transcript()` formats tags + numbered moves + result.
- Tags always include `Mode`, `ModeName`, `Date`, `Result`, `PlyCount`.
- Result uses `1-0` / `0-1` / `1/2-1/2` / `*` plus a termination comment.
- UI offers copy-to-clipboard and save-to-`.txt` for all modes, including Gobblet, draughts, shogi, and reversi.
- New modes must keep using `LocalGameService` / `GameRecord.append_turn` with `format_turn`. Do not invent a parallel history.

## Engine discovery

Search order:
1. `CHESS_CORE_ENGINES_DIR` env
2. `config/engines.json` next to executable
3. `../engines/` sibling directory

Engine binaries never bundled in exe.

## Tournament manager

Application-layer only: no game rules, no PyQt inside `app/tournament`.

- Snapshot JSON version `1` via `infra.storage.tournament_files` (atomic replace).
- Swiss uses native FIDE Dutch 2026 (`NativeDutch2026Engine`). It is **not FIDE-endorsed**.
- `ExternalOfficialEngineAdapter` is a dummy boundary (TRF26 in/out). If an official executable is missing, generation continues with the native engine and writes a diagnostic report; it never silently replaces pairings.
- Round robin is Berger, 1 or 2 cycles; the second cycle reverses colours.
- Manual pair edits require a reason and are stored in the audit log with FIDE-violation warnings.
- Player import: typed list, CSV (UTF-8 BOM, RU/EN headers), public Google Sheets CSV URL only (no OAuth).
- Excel export: sheets «Пары», «Положение», «Кросс-таблица», «По алфавиту». TRF export for rating reports.
- Scheduled ½-point / zero-point byes apply to the next generated round.

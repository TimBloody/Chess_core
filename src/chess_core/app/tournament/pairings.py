"""Pairing algorithms for tournament draws."""

from __future__ import annotations

import random
from collections import defaultdict

from chess_core.app.tournament.dutch2026 import NativeDutch2026Engine
from chess_core.app.tournament.models import (
    RESULT_BYE,
    CrosstableCell,
    Pairing,
    PairingSystem,
    Player,
    Standing,
    is_played_game,
    points_for,
)


def pair_round(
    system: PairingSystem,
    players: tuple[Player, ...],
    history: tuple[Pairing, ...],
    *,
    round_index: int,
    rng: random.Random | None = None,
    declared_rounds: int = 0,
    initial_color: str = "white",
    rr_cycles: int = 1,
    pairing_engine: NativeDutch2026Engine | None = None,
) -> tuple[Pairing, ...]:
    if len(players) < 2 and system is not PairingSystem.KNOCKOUT:
        raise ValueError("at least two players are required")
    rng = rng or random.Random()
    if system is PairingSystem.COLOR_DRAW:
        return _color_draw(players, round_index, rng)
    if system is PairingSystem.ROUND_ROBIN:
        return _round_robin_round(players, round_index, cycles=rr_cycles)
    if system is PairingSystem.SWISS or system is PairingSystem.SWISS_NO_COLOR:
        engine = pairing_engine or NativeDutch2026Engine()
        rounds = declared_rounds or max(1, len(players).bit_length())
        return engine.pair_round(
            players,
            history,
            round_index=round_index,
            declared_rounds=rounds,
            initial_color=initial_color,
            ignore_colours=system is PairingSystem.SWISS_NO_COLOR,
        )
    if system is PairingSystem.KNOCKOUT:
        return _knockout_round(players, history, round_index)
    if system is PairingSystem.SCHEVENINGEN:
        return _scheveningen_round(players, round_index)
    raise ValueError(f"unknown pairing system: {system}")


def all_round_robin_rounds(
    players: tuple[Player, ...],
    *,
    cycles: int = 1,
) -> tuple[tuple[Pairing, ...], ...]:
    if cycles not in {1, 2}:
        raise ValueError("round robin supports 1 or 2 cycles")
    first = _berger_cycle(players)
    if cycles == 1:
        return first
    shift = len(first)
    second: list[tuple[Pairing, ...]] = []
    for round_games in first:
        flipped: list[Pairing] = []
        for pairing in round_games:
            if pairing.is_bye:
                white = pairing.white_id or pairing.black_id
                flipped.append(
                    Pairing(
                        round_index=pairing.round_index + shift,
                        board=pairing.board,
                        white_id=white,
                        black_id=None,
                        result=RESULT_BYE,
                    )
                )
            else:
                flipped.append(
                    Pairing(
                        round_index=pairing.round_index + shift,
                        board=pairing.board,
                        white_id=pairing.black_id,
                        black_id=pairing.white_id,
                    )
                )
        second.append(tuple(flipped))
    return first + tuple(second)


def standings(players: tuple[Player, ...], history: tuple[Pairing, ...]) -> tuple[Standing, ...]:
    points: dict[str, float] = defaultdict(float)
    games: dict[str, int] = defaultdict(int)
    wins: dict[str, int] = defaultdict(int)
    draws: dict[str, int] = defaultdict(int)
    losses: dict[str, int] = defaultdict(int)
    white_games: dict[str, int] = defaultdict(int)
    black_games: dict[str, int] = defaultdict(int)
    opponents: dict[str, list[str]] = defaultdict(list)
    sb_parts: dict[str, float] = defaultdict(float)

    for pairing in history:
        if pairing.result is None:
            continue
        for player_id in pairing.player_ids():
            score = points_for(pairing, player_id)
            if score is None:
                continue
            points[player_id] += score
            if pairing.result in {"zpb", "hpb"}:
                continue
            if pairing.is_bye:
                continue
            if is_played_game(pairing) or pairing.result in {"1-0F", "0-1F", "0-0"}:
                games[player_id] += 1
            if score == 1.0:
                wins[player_id] += 1
            elif score == 0.5:
                draws[player_id] += 1
            else:
                losses[player_id] += 1
            if is_played_game(pairing):
                if pairing.white_id == player_id:
                    white_games[player_id] += 1
                if pairing.black_id == player_id:
                    black_games[player_id] += 1
            other = pairing.black_id if player_id == pairing.white_id else pairing.white_id
            if other is not None:
                opponents[player_id].append(other)

    for pairing in history:
        if pairing.result is None or pairing.is_bye:
            continue
        for player_id in pairing.player_ids():
            score = points_for(pairing, player_id) or 0.0
            other = pairing.black_id if player_id == pairing.white_id else pairing.white_id
            if other is None:
                continue
            if score == 1.0:
                sb_parts[player_id] += points[other]
            elif score == 0.5:
                sb_parts[player_id] += points[other] / 2.0

    rows: list[Standing] = []
    for player in players:
        buchholz = sum(points[opponent] for opponent in opponents[player.player_id])
        rows.append(
            Standing(
                player=player,
                points=points[player.player_id],
                games=games[player.player_id],
                wins=wins[player.player_id],
                draws=draws[player.player_id],
                losses=losses[player.player_id],
                buchholz=buchholz,
                sonneborn_berger=sb_parts[player.player_id],
                white_games=white_games[player.player_id],
                black_games=black_games[player.player_id],
            )
        )
    rows.sort(key=lambda row: (-row.points, -row.buchholz, -row.sonneborn_berger, -row.player.rating, row.player.name))
    placed: list[Standing] = []
    for index, row in enumerate(rows, start=1):
        placed.append(
            Standing(
                player=row.player,
                points=row.points,
                games=row.games,
                wins=row.wins,
                draws=row.draws,
                losses=row.losses,
                buchholz=row.buchholz,
                sonneborn_berger=row.sonneborn_berger,
                white_games=row.white_games,
                black_games=row.black_games,
                place=index,
            )
        )
    return tuple(placed)


def crosstable(
    players: tuple[Player, ...], history: tuple[Pairing, ...]
) -> tuple[tuple[Standing, tuple[CrosstableCell | None, ...]], ...]:
    """Ranking table plus one cell per played round (colour, opponent start number, score)."""

    table = standings(players, history)
    rounds = sorted({pairing.round_index for pairing in history})
    start_of = {player.player_id: player.start_number for player in players}
    rows: list[tuple[Standing, tuple[CrosstableCell | None, ...]]] = []
    for standing in table:
        cells: list[CrosstableCell | None] = []
        for round_index in rounds:
            cell: CrosstableCell | None = None
            for pairing in history:
                if pairing.round_index != round_index:
                    continue
                if standing.player.player_id not in pairing.player_ids():
                    continue
                score = points_for(pairing, standing.player.player_id)
                if pairing.is_bye:
                    bye_label = {"bye": "BYE 1", "hpb": "BYE ½", "zpb": "BYE 0"}.get(
                        pairing.result or "", f"BYE {pairing.result or ''}".strip()
                    )
                    cell = CrosstableCell(round_index, None, "-", score, bye_label)
                    break
                opponent_id = (
                    pairing.black_id
                    if pairing.white_id == standing.player.player_id
                    else pairing.white_id
                )
                color = "w" if pairing.white_id == standing.player.player_id else "b"
                mark = "б" if color == "w" else "ч"
                opp_start = start_of.get(opponent_id or "", 0)
                if score is None:
                    score_text = "…"
                elif score == int(score):
                    score_text = str(int(score))
                else:
                    score_text = str(score)
                cell = CrosstableCell(
                    round_index,
                    opp_start or None,
                    color,
                    score,
                    f"{mark}{opp_start} {score_text}",
                )
                break
            cells.append(cell)
        rows.append((standing, tuple(cells)))
    return tuple(rows)


def _berger_cycle(players: tuple[Player, ...]) -> tuple[tuple[Pairing, ...], ...]:
    n = len(players)
    if n < 2:
        raise ValueError("at least two players are required")
    slots = list(range(n))
    if n % 2:
        slots.append(-1)
    size = len(slots)
    rotation = slots[:-1]
    fixed = slots[-1]
    rounds: list[tuple[Pairing, ...]] = []
    for round_index in range(1, size):
        ordered = rotation + [fixed]
        boards: list[Pairing] = []
        board = 1
        for index in range(size // 2):
            left = ordered[index]
            right = ordered[size - 1 - index]
            if round_index % 2 == 0:
                left, right = right, left
            white = None if left < 0 else players[left].player_id
            black = None if right < 0 else players[right].player_id
            result = RESULT_BYE if white is None or black is None else None
            if white is None and black is None:
                continue
            if white is None:
                white, black = black, None
            boards.append(
                Pairing(
                    round_index=round_index,
                    board=board,
                    white_id=white,
                    black_id=black,
                    result=result,
                )
            )
            board += 1
        rounds.append(tuple(boards))
        rotation = [rotation[-1], *rotation[:-1]]
    return tuple(rounds)


def _color_draw(
    players: tuple[Player, ...],
    round_index: int,
    rng: random.Random,
) -> tuple[Pairing, ...]:
    order = list(players)
    rng.shuffle(order)
    pairings: list[Pairing] = []
    board = 1
    index = 0
    while index < len(order):
        if index + 1 >= len(order):
            pairings.append(
                Pairing(round_index, board, order[index].player_id, None, RESULT_BYE)
            )
            break
        first, second = order[index], order[index + 1]
        if rng.random() < 0.5:
            first, second = second, first
        pairings.append(Pairing(round_index, board, first.player_id, second.player_id))
        board += 1
        index += 2
    return tuple(pairings)


def _round_robin_round(players: tuple[Player, ...], round_index: int, *, cycles: int = 1) -> tuple[Pairing, ...]:
    rounds = all_round_robin_rounds(players, cycles=cycles)
    if not 1 <= round_index <= len(rounds):
        raise ValueError(f"round_robin has {len(rounds)} rounds")
    return rounds[round_index - 1]


def _knockout_round(
    players: tuple[Player, ...],
    history: tuple[Pairing, ...],
    round_index: int,
) -> tuple[Pairing, ...]:
    if round_index == 1:
        seeds = sorted(players, key=lambda player: (-player.rating, player.player_id))
    else:
        previous = [pairing for pairing in history if pairing.round_index == round_index - 1]
        if any(pairing.result is None for pairing in previous if not pairing.is_bye):
            raise ValueError("previous knockout round is unfinished")
        winners: list[Player] = []
        by_id = {player.player_id: player for player in players}
        for pairing in previous:
            winner_id = _winner_id(pairing)
            if winner_id is not None:
                winners.append(by_id[winner_id])
        seeds = winners
        if len(seeds) < 2:
            return ()
    size = 1
    while size < len(seeds):
        size *= 2
    padded: list[Player | None] = list(seeds) + [None] * (size - len(seeds))
    pairings: list[Pairing] = []
    board = 1
    for index in range(size // 2):
        left = padded[index]
        right = padded[size - 1 - index]
        white_id = None if left is None else left.player_id
        black_id = None if right is None else right.player_id
        result = RESULT_BYE if white_id is None or black_id is None else None
        if white_id is None and black_id is None:
            continue
        if white_id is None:
            white_id, black_id = black_id, None
        pairings.append(
            Pairing(round_index, board, white_id, black_id, result)
        )
        board += 1
    return tuple(pairings)


def _scheveningen_round(players: tuple[Player, ...], round_index: int) -> tuple[Pairing, ...]:
    teams: dict[str, list[Player]] = defaultdict(list)
    for player in players:
        if not player.team:
            raise ValueError("Scheveningen pairing requires a team for every player")
        teams[player.team].append(player)
    if len(teams) != 2:
        raise ValueError("Scheveningen pairing requires exactly two teams")
    (team_a, side_a), (team_b, side_b) = tuple(teams.items())
    del team_a, team_b
    if len(side_a) != len(side_b):
        raise ValueError("Scheveningen teams must be the same size")
    shift = (round_index - 1) % len(side_b)
    pairings: list[Pairing] = []
    for index, player in enumerate(side_a):
        opponent = side_b[(index + shift) % len(side_b)]
        if (round_index + index) % 2:
            white, black = opponent, player
        else:
            white, black = player, opponent
        pairings.append(
            Pairing(round_index, index + 1, white.player_id, black.player_id)
        )
    return tuple(pairings)


def _winner_id(pairing: Pairing) -> str | None:
    if pairing.is_bye:
        return pairing.white_id or pairing.black_id
    if pairing.result in {"1-0", "1-0F"}:
        return pairing.white_id
    if pairing.result in {"0-1", "0-1F"}:
        return pairing.black_id
    return None

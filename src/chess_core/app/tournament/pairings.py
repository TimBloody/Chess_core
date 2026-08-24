"""Pairing algorithms for tournament draws."""

from __future__ import annotations

import random
from collections import defaultdict

from chess_core.app.tournament.models import (
    RESULT_BYE,
    Pairing,
    PairingSystem,
    Player,
    Standing,
    points_for,
)


def pair_round(
    system: PairingSystem,
    players: tuple[Player, ...],
    history: tuple[Pairing, ...],
    *,
    round_index: int,
    rng: random.Random | None = None,
) -> tuple[Pairing, ...]:
    if len(players) < 2 and system is not PairingSystem.KNOCKOUT:
        raise ValueError("at least two players are required")
    rng = rng or random.Random()
    if system is PairingSystem.COLOR_DRAW:
        return _color_draw(players, round_index, rng)
    if system is PairingSystem.ROUND_ROBIN:
        return _round_robin_round(players, round_index)
    if system is PairingSystem.SWISS:
        return _swiss_round(players, history, round_index)
    if system is PairingSystem.KNOCKOUT:
        return _knockout_round(players, history, round_index)
    if system is PairingSystem.SCHEVENINGEN:
        return _scheveningen_round(players, round_index)
    raise ValueError(f"unknown pairing system: {system}")


def all_round_robin_rounds(players: tuple[Player, ...]) -> tuple[tuple[Pairing, ...], ...]:
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


def standings(players: tuple[Player, ...], history: tuple[Pairing, ...]) -> tuple[Standing, ...]:
    by_id = {player.player_id: player for player in players}
    points: dict[str, float] = defaultdict(float)
    games: dict[str, int] = defaultdict(int)
    wins: dict[str, int] = defaultdict(int)
    draws: dict[str, int] = defaultdict(int)
    losses: dict[str, int] = defaultdict(int)
    white_games: dict[str, int] = defaultdict(int)
    black_games: dict[str, int] = defaultdict(int)
    opponents: dict[str, list[str]] = defaultdict(list)

    for pairing in history:
        if pairing.result is None:
            continue
        for player_id in (pairing.white_id, pairing.black_id):
            if player_id is None:
                continue
            score = points_for(pairing, player_id)
            if score is None:
                continue
            points[player_id] += score
            games[player_id] += 1
            if score == 1.0:
                wins[player_id] += 1
            elif score == 0.5:
                draws[player_id] += 1
            else:
                losses[player_id] += 1
            if pairing.white_id == player_id and pairing.black_id is not None:
                white_games[player_id] += 1
            if pairing.black_id == player_id:
                black_games[player_id] += 1
            other = pairing.black_id if player_id == pairing.white_id else pairing.white_id
            if other is not None:
                opponents[player_id].append(other)

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
                white_games=white_games[player.player_id],
                black_games=black_games[player.player_id],
            )
        )
    rows.sort(key=lambda row: (-row.points, -row.buchholz, -row.player.rating, row.player.name))
    del by_id
    return tuple(rows)


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


def _round_robin_round(players: tuple[Player, ...], round_index: int) -> tuple[Pairing, ...]:
    rounds = all_round_robin_rounds(players)
    if not 1 <= round_index <= len(rounds):
        raise ValueError(f"round_robin has {len(rounds)} rounds")
    return rounds[round_index - 1]


def _swiss_round(
    players: tuple[Player, ...],
    history: tuple[Pairing, ...],
    round_index: int,
) -> tuple[Pairing, ...]:
    scores = {row.player.player_id: row.points for row in standings(players, history)}
    played = _played_pairs(history)
    colors = {row.player.player_id: (row.white_games, row.black_games) for row in standings(players, history)}
    last_color = _last_colors(history)
    ordered = sorted(
        players,
        key=lambda player: (-scores[player.player_id], -player.rating, player.player_id),
    )
    remaining = list(ordered)
    pairings: list[Pairing] = []
    board = 1
    if len(remaining) % 2:
        bye_player = _choose_bye(remaining, history)
        remaining = [player for player in remaining if player.player_id != bye_player.player_id]
        pairings.append(
            Pairing(round_index, board, bye_player.player_id, None, RESULT_BYE)
        )
        board += 1
    used: set[str] = set()
    for player in list(remaining):
        if player.player_id in used:
            continue
        partner = _choose_opponent(player, remaining, used, played)
        used.add(player.player_id)
        used.add(partner.player_id)
        white, black = _prefer_colors(player, partner, colors, last_color)
        pairings.append(Pairing(round_index, board, white.player_id, black.player_id))
        board += 1
    return tuple(pairings)


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


def _played_pairs(history: tuple[Pairing, ...]) -> dict[str, set[str]]:
    played: dict[str, set[str]] = defaultdict(set)
    for pairing in history:
        if pairing.white_id is None or pairing.black_id is None:
            continue
        played[pairing.white_id].add(pairing.black_id)
        played[pairing.black_id].add(pairing.white_id)
    return played


def _last_colors(history: tuple[Pairing, ...]) -> dict[str, str]:
    last: dict[str, str] = {}
    for pairing in history:
        if pairing.white_id is not None and pairing.black_id is not None:
            last[pairing.white_id] = "white"
            last[pairing.black_id] = "black"
    return last


def _choose_bye(players: list[Player], history: tuple[Pairing, ...]) -> Player:
    had_bye = {
        pairing.white_id or pairing.black_id
        for pairing in history
        if pairing.is_bye
    }
    for player in reversed(players):
        if player.player_id not in had_bye:
            return player
    return players[-1]


def _choose_opponent(
    player: Player,
    remaining: list[Player],
    used: set[str],
    played: dict[str, set[str]],
) -> Player:
    candidates = [
        other
        for other in remaining
        if other.player_id not in used and other.player_id != player.player_id
    ]
    for other in candidates:
        if other.player_id not in played[player.player_id]:
            return other
    if not candidates:
        raise ValueError("no opponent available")
    return candidates[0]


def _prefer_colors(
    first: Player,
    second: Player,
    colors: dict[str, tuple[int, int]],
    last_color: dict[str, str],
) -> tuple[Player, Player]:
    first_white, first_black = colors.get(first.player_id, (0, 0))
    second_white, second_black = colors.get(second.player_id, (0, 0))
    first_pref = first_black - first_white
    second_pref = second_black - second_white
    if first_pref > second_pref:
        return first, second
    if second_pref > first_pref:
        return second, first
    if last_color.get(first.player_id) == "white":
        return second, first
    return first, second


def _winner_id(pairing: Pairing) -> str | None:
    if pairing.is_bye:
        return pairing.white_id or pairing.black_id
    if pairing.result == "1-0":
        return pairing.white_id
    if pairing.result == "0-1":
        return pairing.black_id
    return None

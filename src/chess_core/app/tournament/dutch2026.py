"""Native FIDE Dutch 2026 pairing engine (C.04.1–C.04.3 from 1 February 2026).

Not FIDE-endorsed. Pairings follow the sequential bracket search: absolute
criteria C1–C3, completion C4, PAB C5, quality C6–C21, then colour allocation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations, permutations

from chess_core.app.tournament.models import (
    RESULT_BYE,
    Pairing,
    Player,
    assign_pairing_numbers,
    is_full_point_unplayed_win,
    is_played_game,
    points_for,
)

WHITE = "white"
BLACK = "black"
TRANSPOSITION_CAP = 20_000

# Set for the duration of one pair_round call when colour balance is irrelevant
# (shogi, board games, etc.). Affects legality/quality checks and seat assignment.
_IGNORE_COLOURS = False


@dataclass(frozen=True, slots=True)
class ColourPref:
    strength: str
    colour: str | None

    @property
    def is_absolute(self) -> bool:
        return self.strength == "absolute"

    @property
    def is_strong(self) -> bool:
        return self.strength in {"absolute", "strong"}

    @property
    def rank(self) -> int:
        return {"none": 0, "mild": 1, "strong": 2, "absolute": 3}[self.strength]


@dataclass
class PlayerView:
    player: Player
    tpn: int
    score: float = 0.0
    white_games: int = 0
    black_games: int = 0
    last_colors: tuple[str, ...] = ()
    opponents: set[str] = field(default_factory=set)
    unplayed: int = 0
    had_pab: bool = False
    had_forfeit_win: bool = False
    downfloat_rounds: tuple[int, ...] = ()
    upfloat_rounds: tuple[int, ...] = ()

    @property
    def player_id(self) -> str:
        return self.player.player_id

    @property
    def colour_difference(self) -> int:
        return self.white_games - self.black_games

    def preference(self, *, last_round: bool, topscorer: bool) -> ColourPref:
        played = self.last_colors
        cd = self.colour_difference
        if not played:
            return ColourPref("none", None)
        consecutive = len(played) >= 2 and played[-1] == played[-2]
        wide = abs(cd) > 1
        if consecutive or wide:
            if consecutive:
                want = BLACK if played[-1] == WHITE else WHITE
            else:
                want = BLACK if cd > 0 else WHITE
            if last_round and topscorer:
                strength = "strong"
            else:
                strength = "absolute"
            return ColourPref(strength, want)
        if abs(cd) == 1:
            return ColourPref("strong", BLACK if cd > 0 else WHITE)
        return ColourPref("mild", BLACK if played[-1] == WHITE else WHITE)

    def pab_forbidden(self) -> bool:
        return self.had_pab or self.had_forfeit_win


@dataclass(frozen=True, slots=True)
class RawPair:
    a: PlayerView
    b: PlayerView | None

    @property
    def is_bye(self) -> bool:
        return self.b is None


class NativeDutch2026Engine:
    engine_id = "native_dutch_2026"

    def pair_round(
        self,
        players: tuple[Player, ...],
        history: tuple[Pairing, ...],
        *,
        round_index: int,
        declared_rounds: int,
        initial_color: str = WHITE,
        ignore_colours: bool = False,
    ) -> tuple[Pairing, ...]:
        global _IGNORE_COLOURS
        if len(players) < 2:
            raise ValueError("at least two players are required")
        if round_index == 1:
            numbered = assign_pairing_numbers(players)
        else:
            numbered = players if all(player.start_number for player in players) else assign_pairing_numbers(players)
        previous = _IGNORE_COLOURS
        _IGNORE_COLOURS = ignore_colours
        try:
            views = build_player_views(numbered, history)
            ordered = sorted(views.values(), key=lambda view: (-view.score, view.tpn))
            last_round = round_index >= declared_rounds
            half_max = declared_rounds / 2.0
            raw = _pair_scoregroups(ordered, round_index, last_round, half_max)
            if ignore_colours:
                seated = [_seat_without_colour(pair) for pair in raw]
            else:
                seated = [
                    _allocate_colors(pair, views, last_round, half_max, initial_color) for pair in raw
                ]
            return _publish(seated, round_index)
        finally:
            _IGNORE_COLOURS = previous


def build_player_views(players: tuple[Player, ...], history: tuple[Pairing, ...]) -> dict[str, PlayerView]:
    views = {
        player.player_id: PlayerView(player=player, tpn=player.start_number or index)
        for index, player in enumerate(players, start=1)
    }
    scores_before_round: dict[int, dict[str, float]] = {}
    running: dict[str, float] = {player_id: 0.0 for player_id in views}
    rounds = sorted({pairing.round_index for pairing in history})
    for round_index in rounds:
        scores_before_round[round_index] = dict(running)
        for pairing in history:
            if pairing.round_index != round_index or pairing.result is None:
                continue
            for player_id in pairing.player_ids():
                if player_id not in views:
                    continue
                score = points_for(pairing, player_id)
                if score is not None:
                    running[player_id] += score
    for pairing in history:
        if pairing.result is None:
            continue
        before = scores_before_round.get(pairing.round_index, {})
        ids = pairing.player_ids()
        for player_id in ids:
            view = views.get(player_id)
            if view is None:
                continue
            score = points_for(pairing, player_id) or 0.0
            view.score += score
            if pairing.is_bye and pairing.result == RESULT_BYE:
                view.had_pab = True
                view.unplayed += 1
                view.downfloat_rounds = (*view.downfloat_rounds, pairing.round_index)
            elif pairing.result in {"zpb", "hpb", "0-0"}:
                view.unplayed += 1
            if is_full_point_unplayed_win(pairing, player_id) and not pairing.is_bye:
                view.had_forfeit_win = True
                view.unplayed += 1
            elif pairing.result in {"1-0F", "0-1F"} and not is_full_point_unplayed_win(pairing, player_id):
                view.unplayed += 1
            if is_played_game(pairing):
                if player_id == pairing.white_id:
                    view.white_games += 1
                    view.last_colors = (*view.last_colors, WHITE)
                else:
                    view.black_games += 1
                    view.last_colors = (*view.last_colors, BLACK)
            other = pairing.black_id if player_id == pairing.white_id else pairing.white_id
            if other is not None:
                view.opponents.add(other)
                own_score = before.get(player_id, 0.0)
                other_score = before.get(other, 0.0)
                if own_score > other_score:
                    view.downfloat_rounds = (*view.downfloat_rounds, pairing.round_index)
                elif own_score < other_score:
                    view.upfloat_rounds = (*view.upfloat_rounds, pairing.round_index)
    return views


def _pair_scoregroups(
    ordered: list[PlayerView],
    round_index: int,
    last_round: bool,
    half_max: float,
) -> list[RawPair]:
    groups: list[list[PlayerView]] = []
    for view in ordered:
        if groups and groups[-1][0].score == view.score:
            groups[-1].append(view)
        else:
            groups.append([view])
    pairs: list[RawPair] = []
    downfloaters: list[PlayerView] = []
    for index, group in enumerate(groups):
        remaining_groups = groups[index + 1 :]
        is_last = index == len(groups) - 1
        bracket = downfloaters + group
        next_residents = remaining_groups[0] if remaining_groups else []
        chosen, downfloaters = _pair_bracket(
            bracket,
            next_residents=next_residents,
            is_last=is_last,
            last_round=last_round,
            half_max=half_max,
            round_index=round_index,
        )
        pairs.extend(chosen)
    if downfloaters:
        if len(downfloaters) == 1 and not downfloaters[0].pab_forbidden():
            pairs.append(RawPair(downfloaters[0], None))
        else:
            extra, leftover = _pair_even_bracket(downfloaters, last_round, half_max, round_index)
            pairs.extend(extra)
            for player in leftover:
                pairs.append(RawPair(player, None))
    return pairs


def _split_mdps(bracket: list[PlayerView]) -> tuple[list[PlayerView], list[PlayerView]]:
    """FIDE 1.3.2 / 1.4.1: residents share the lowest score; everyone else is an MDP."""
    if len({player.score for player in bracket}) <= 1:
        return [], list(bracket)
    lowest = min(player.score for player in bracket)
    mdps = sorted((player for player in bracket if player.score > lowest), key=lambda player: player.tpn)
    residents = sorted((player for player in bracket if player.score == lowest), key=lambda player: player.tpn)
    return mdps, residents


def _pair_bracket(
    bracket: list[PlayerView],
    *,
    next_residents: list[PlayerView],
    is_last: bool,
    last_round: bool,
    half_max: float,
    round_index: int,
) -> tuple[list[RawPair], list[PlayerView]]:
    if not bracket:
        return [], []
    mdps, residents = _split_mdps(bracket)
    if is_last:
        if mdps:
            pairs, leftover = _pair_heterogeneous(
                mdps, residents, [], last_round, half_max, round_index
            )
            if leftover:
                pairs = pairs + _pair_last_bracket(leftover, last_round, half_max, round_index)
            return pairs, []
        return _pair_last_bracket(bracket, last_round, half_max, round_index), []
    if mdps:
        return _pair_heterogeneous(
            mdps, residents, next_residents, last_round, half_max, round_index
        )
    pairs, down = _best_homogeneous(bracket, next_residents, last_round, half_max, round_index)
    return pairs, down


def _pair_last_bracket(
    bracket: list[PlayerView],
    last_round: bool,
    half_max: float,
    round_index: int,
) -> list[RawPair]:
    if len(bracket) % 2 == 0:
        pairs, leftover = _pair_even_bracket(bracket, last_round, half_max, round_index)
        return pairs + [RawPair(player, None) for player in leftover]
    eligible = [player for player in bracket if not player.pab_forbidden()]
    if not eligible:
        eligible = list(bracket)
    eligible.sort(key=lambda player: (player.score, player.unplayed, -player.tpn))
    best: tuple | None = None
    best_pairs: list[RawPair] = []
    for pab in eligible:
        rest = [player for player in bracket if player.player_id != pab.player_id]
        pairs, leftover = _pair_even_bracket(rest, last_round, half_max, round_index)
        if leftover:
            continue
        quality = _evaluate_pairs(
            pairs + [RawPair(pab, None)],
            last_round,
            half_max,
            round_index,
            next_residents=[],
            pab=pab,
        )
        if best is None or quality < best:
            best = quality
            best_pairs = pairs + [RawPair(pab, None)]
            if _is_perfect(quality):
                break
    if best_pairs:
        return best_pairs
    pairs, leftover = _pair_even_bracket(bracket[:-1], last_round, half_max, round_index)
    return pairs + [RawPair(player, None) for player in leftover] + [RawPair(bracket[-1], None)]


def _pair_heterogeneous(
    mdps: list[PlayerView],
    residents: list[PlayerView],
    next_residents: list[PlayerView],
    last_round: bool,
    half_max: float,
    round_index: int,
) -> tuple[list[RawPair], list[PlayerView]]:
    m0 = len(mdps)
    max_pairs_cap = min((m0 + len(residents)) // 2, len(residents) + m0)
    m1 = min(m0, len(residents), max_pairs_cap)
    best: tuple | None = None
    best_result: tuple[list[RawPair], list[PlayerView]] = ([], mdps + residents)
    for paired_mdp_count in range(m1, -1, -1):
        for mdp_set in combinations(range(m0), paired_mdp_count):
            chosen_mdps = [mdps[index] for index in mdp_set]
            limbo = [mdps[index] for index in range(m0) if index not in mdp_set]
            mdp_pairs, remainder = _mdp_pairing(chosen_mdps, residents, last_round, half_max)
            if mdp_pairs is None:
                continue
            rest_pairs, rest_down = _best_homogeneous(
                remainder, next_residents, last_round, half_max, round_index
            )
            down = limbo + rest_down
            all_pairs = mdp_pairs + rest_pairs
            quality = _evaluate_pairs(
                all_pairs,
                last_round,
                half_max,
                round_index,
                next_residents=next_residents,
                downfloaters=down,
                mdps=mdps,
                look_ahead=True,
            )
            if best is None or quality < best:
                best = quality
                best_result = (all_pairs, down)
                if _is_perfect(quality):
                    return best_result
        if best is not None:
            break
    return best_result


def _mdp_pairing(
    mdps: list[PlayerView],
    residents: list[PlayerView],
    last_round: bool,
    half_max: float,
) -> tuple[list[RawPair] | None, list[PlayerView]]:
    if not mdps:
        return [], list(residents)
    # C.04.3 3.2.2–3.3.1: S1 = MDPs in ranking order, S2 = residents; first vs first.
    s1 = sorted(mdps, key=lambda player: player.tpn)
    residents = sorted(residents, key=lambda player: player.tpn)
    best: list[RawPair] | None = None
    best_rest: list[PlayerView] = list(residents)
    tried = 0
    for s2 in permutations(residents):
        tried += 1
        if tried > TRANSPOSITION_CAP:
            break
        opponents = list(s2[: len(s1)])
        rest = list(s2[len(s1) :])
        pairs = [RawPair(a, b) for a, b in zip(s1, opponents, strict=True)]
        if all(_legal_pair(pair, last_round, half_max) for pair in pairs):
            best = pairs
            best_rest = rest
            break
    return best, best_rest


def _pair_even_bracket(
    players: list[PlayerView],
    last_round: bool,
    half_max: float,
    round_index: int,
) -> tuple[list[RawPair], list[PlayerView]]:
    pairs, down = _best_homogeneous(players, [], last_round, half_max, round_index)
    return pairs, down


def _best_homogeneous(
    players: list[PlayerView],
    next_residents: list[PlayerView],
    last_round: bool,
    half_max: float,
    round_index: int,
) -> tuple[list[RawPair], list[PlayerView]]:
    n = len(players)
    if n < 2:
        return [], list(players)
    ranked = sorted(players, key=lambda player: player.tpn)
    best_quality: tuple | None = None
    best_pairs: list[RawPair] = []
    best_down: list[PlayerView] = list(ranked)
    max_pairs = n // 2
    for pair_count in range(max_pairs, -1, -1):
        n1 = pair_count
        if n1 == 0:
            quality = _evaluate_pairs(
                [],
                last_round,
                half_max,
                round_index,
                next_residents=next_residents,
                downfloaters=ranked,
                look_ahead=True,
            )
            if best_quality is None or quality < best_quality:
                return [], ranked
            break
        for s1_idx, s2_idx in _subgroup_layouts(n, n1):
            s1 = [ranked[index] for index in s1_idx]
            s2_base = [ranked[index] for index in s2_idx]
            down_fixed = [ranked[index] for index in range(n) if index not in s1_idx and index not in s2_idx]
            tried = 0
            for s2 in permutations(s2_base):
                tried += 1
                if tried > TRANSPOSITION_CAP:
                    break
                pairs = [RawPair(a, b) for a, b in zip(s1, s2, strict=False)]
                if len(pairs) != n1:
                    continue
                if not all(_legal_pair(pair, last_round, half_max) for pair in pairs):
                    continue
                down = down_fixed + list(s2[n1:])
                if not _completion_possible(down + next_residents, last_round, half_max):
                    continue
                quality = _evaluate_pairs(
                    pairs,
                    last_round,
                    half_max,
                    round_index,
                    next_residents=next_residents,
                    downfloaters=down,
                    look_ahead=True,
                )
                if best_quality is None or quality < best_quality:
                    best_quality = quality
                    best_pairs = pairs
                    best_down = down
                    if _is_perfect(quality):
                        return best_pairs, best_down
        if best_quality is not None:
            break
    return best_pairs, best_down


def _subgroup_layouts(n: int, n1: int) -> list[tuple[tuple[int, ...], tuple[int, ...]]]:
    """Identity split plus resident exchanges, ordered per Dutch sequential rules."""
    all_idx = tuple(range(n))
    s1 = all_idx[:n1]
    s2 = all_idx[n1:]
    layouts: list[tuple[tuple[int, ...], tuple[int, ...]]] = [(s1, s2)]
    max_k = min(n1, n - n1, max(1, n1 // 2 + 1))
    for k in range(1, max_k + 1):
        ranked_exchanges: list[tuple[int, tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]] = []
        for left in combinations(s1, k):
            for right in combinations(s2, k):
                new_s1 = tuple(sorted(set(s1) - set(left) | set(right)))
                new_s2 = tuple(sorted(set(s2) - set(right) | set(left)))
                diff = abs(sum(right) - sum(left))
                ranked_exchanges.append(
                    (diff, tuple(sorted(left, reverse=True)), right, new_s1, new_s2)
                )
        ranked_exchanges.sort(key=lambda item: (item[0], item[1], item[2]))
        for _diff, _left, _right, new_s1, new_s2 in ranked_exchanges:
            layouts.append((new_s1, new_s2))
    seen: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()
    unique: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    for layout in layouts:
        if layout in seen:
            continue
        seen.add(layout)
        unique.append(layout)
    return unique


def _legal_pair(pair: RawPair, last_round: bool, half_max: float) -> bool:
    if pair.b is None:
        return not pair.a.pab_forbidden()
    if pair.b.player_id in pair.a.opponents:
        return False
    if _IGNORE_COLOURS:
        return True
    pref_a = pair.a.preference(last_round=last_round, topscorer=pair.a.score > half_max)
    pref_b = pair.b.preference(last_round=last_round, topscorer=pair.b.score > half_max)
    if pref_a.is_absolute and pref_b.is_absolute and pref_a.colour == pref_b.colour:
        if not last_round or (pair.a.score <= half_max and pair.b.score <= half_max):
            return False
    return True


def _completion_possible(remaining: list[PlayerView], last_round: bool, half_max: float) -> bool:
    leftover = list(remaining)
    if len(leftover) <= 1:
        return len(leftover) == 0 or not leftover[0].pab_forbidden() or True

    def search(pool: list[PlayerView]) -> bool:
        if not pool:
            return True
        if len(pool) == 1:
            return True
        first = pool[0]
        rest = pool[1:]
        for index, other in enumerate(rest):
            if _legal_pair(RawPair(first, other), last_round, half_max):
                nxt = rest[:index] + rest[index + 1 :]
                if search(nxt):
                    return True
        if search(rest):
            return True
        return False

    return search(leftover)


def _evaluate_pairs(
    pairs: list[RawPair],
    last_round: bool,
    half_max: float,
    round_index: int,
    *,
    next_residents: list[PlayerView] | None = None,
    downfloaters: list[PlayerView] | None = None,
    mdps: list[PlayerView] | None = None,
    pab: PlayerView | None = None,
    look_ahead: bool = False,
) -> tuple:
    down = list(downfloaters or ())
    for pair in pairs:
        if pair.is_bye:
            pab = pair.a
    c6 = len(down)
    c7 = tuple(sorted((player.score for player in down), reverse=True))
    next_fail = (
        _next_bracket_failure(down, next_residents or [], last_round, half_max)
        if look_ahead
        else (0, ())
    )
    c5 = pab.score if pab is not None else 0.0
    c9 = pab.unplayed if pab is not None else 0
    c10 = c11 = 0
    c12 = c13 = 0
    c14 = c15 = c16 = c17 = 0
    c18 = c19 = c20 = c21 = 0.0
    for pair in pairs:
        if pair.b is None:
            continue
        a, b = pair.a, pair.b
        if not _IGNORE_COLOURS:
            pa = a.preference(last_round=last_round, topscorer=a.score > half_max)
            pb = b.preference(last_round=last_round, topscorer=b.score > half_max)
            white, black = _prefer_without_history(a, b, pa, pb)
            del black
            for player, got, pref in (
                (a, WHITE if white is a else BLACK, pa),
                (b, WHITE if white is b else BLACK, pb),
            ):
                if pref.colour and got != pref.colour:
                    c12 += 1
                    if pref.is_strong:
                        c13 += 1
                if last_round and (
                    player.score > half_max or pair.a.score > half_max or pair.b.score > half_max
                ):
                    future_cd = player.colour_difference + (1 if got == WHITE else -1)
                    if abs(future_cd) > 2:
                        c10 += 1
                    colors = (*player.last_colors, got)
                    if len(colors) >= 3 and colors[-1] == colors[-2] == colors[-3]:
                        c11 += 1
        a_down = a.score > b.score
        b_down = b.score > a.score
        c14, c15, c16, c17 = _float_repeat_counts(
            a, b, a_down, b_down, round_index, c14, c15, c16, c17
        )
        if mdps:
            c18, c19, c20, c21 = _mdp_float_scores(
                a, b, a_down, b_down, round_index, mdps, c18, c19, c20, c21
            )
    return (c5, c6, c7, next_fail, c9, c10, c11, c12, c13, c14, c15, c16, c17, c18, c19, c20, c21)


def _is_perfect(quality: tuple) -> bool:
    c5, c6, c7, next_fail, c9, *rest = quality
    del c5, c9
    return c6 == 0 and c7 == () and next_fail == (0, ()) and all(item == 0 or item == 0.0 for item in rest)


def _next_bracket_failure(
    down: list[PlayerView],
    next_residents: list[PlayerView],
    last_round: bool,
    half_max: float,
) -> tuple:
    pool = down + next_residents
    if len(pool) <= 1:
        return (0, ())
    legal_pairs = 0
    used: set[str] = set()
    for player in pool:
        if player.player_id in used:
            continue
        partner = next(
            (
                other
                for other in pool
                if other.player_id not in used
                and other.player_id != player.player_id
                and _legal_pair(RawPair(player, other), last_round, half_max)
            ),
            None,
        )
        if partner is None:
            continue
        used.add(player.player_id)
        used.add(partner.player_id)
        legal_pairs += 1
    leftover = [player for player in pool if player.player_id not in used]
    del legal_pairs
    return (len(leftover), tuple(sorted((player.score for player in leftover), reverse=True)))


def _float_repeat_counts(
    a: PlayerView,
    b: PlayerView,
    a_down: bool,
    b_down: bool,
    round_index: int,
    c14: int,
    c15: int,
    c16: int,
    c17: int,
) -> tuple[int, int, int, int]:
    prev = round_index - 1
    prev2 = round_index - 2
    for player, down, up in ((a, a_down, b_down), (b, b_down, a_down)):
        if down:
            if prev in player.downfloat_rounds:
                c14 += 1
            if prev2 in player.downfloat_rounds:
                c15 += 1
        if up:
            if prev in player.upfloat_rounds:
                c16 += 1
            if prev2 in player.upfloat_rounds:
                c17 += 1
    return c14, c15, c16, c17


def _mdp_float_scores(
    a: PlayerView,
    b: PlayerView,
    a_down: bool,
    b_down: bool,
    round_index: int,
    mdps: list[PlayerView],
    c18: float,
    c19: float,
    c20: float,
    c21: float,
) -> tuple[float, float, float, float]:
    mdp_ids = {player.player_id for player in mdps}
    prev = round_index - 1
    prev2 = round_index - 2
    diff = abs(a.score - b.score)
    for player, down, up in ((a, a_down, b_down), (b, b_down, a_down)):
        if player.player_id not in mdp_ids:
            continue
        if down and prev in player.downfloat_rounds:
            c18 += diff
        if down and prev2 in player.downfloat_rounds:
            c19 += diff
        if up and prev in player.upfloat_rounds:
            c20 += diff
        if up and prev2 in player.upfloat_rounds:
            c21 += diff
    return c18, c19, c20, c21


def _prefer_without_history(
    a: PlayerView, b: PlayerView, pa: ColourPref, pb: ColourPref
) -> tuple[PlayerView, PlayerView]:
    if pa.colour == WHITE and pb.colour != WHITE:
        return a, b
    if pb.colour == WHITE and pa.colour != WHITE:
        return b, a
    if pa.colour == BLACK and pb.colour != BLACK:
        return b, a
    if pb.colour == BLACK and pa.colour != BLACK:
        return a, b
    if pa.rank > pb.rank:
        return (a, b) if pa.colour == WHITE else (b, a)
    if pb.rank > pa.rank:
        return (b, a) if pb.colour == WHITE else (a, b)
    return a, b


def _seat_without_colour(pair: RawPair) -> RawPair:
    """Deterministic seat order by start number; colour balance is ignored."""
    if pair.b is None:
        return pair
    first, second = (pair.a, pair.b) if pair.a.tpn <= pair.b.tpn else (pair.b, pair.a)
    return RawPair(first, second)


def _allocate_colors(
    pair: RawPair,
    views: dict[str, PlayerView],
    last_round: bool,
    half_max: float,
    initial_color: str,
) -> RawPair:
    del views
    if pair.b is None:
        return pair
    a, b = pair.a, pair.b
    pa = a.preference(last_round=last_round, topscorer=a.score > half_max)
    pb = b.preference(last_round=last_round, topscorer=b.score > half_max)
    white, black = _colour_allocation(a, b, pa, pb, initial_color)
    return RawPair(white, black)


def _colour_allocation(
    a: PlayerView,
    b: PlayerView,
    pa: ColourPref,
    pb: ColourPref,
    initial_color: str,
) -> tuple[PlayerView, PlayerView]:
    compatible = (
        pa.colour is None
        or pb.colour is None
        or pa.colour != pb.colour
    )
    if compatible and pa.colour and pb.colour:
        return (a, b) if pa.colour == WHITE else (b, a)
    if compatible and pa.colour and pb.colour is None:
        return (a, b) if pa.colour == WHITE else (b, a)
    if compatible and pb.colour and pa.colour is None:
        return (b, a) if pb.colour == WHITE else (a, b)
    if pa.rank != pb.rank:
        stronger, other, pref = (a, b, pa) if pa.rank > pb.rank else (b, a, pb)
        if pref.colour == WHITE:
            return stronger, other
        if pref.colour == BLACK:
            return other, stronger
    if pa.is_absolute and pb.is_absolute:
        if abs(a.colour_difference) != abs(b.colour_difference):
            wider = a if abs(a.colour_difference) > abs(b.colour_difference) else b
            other = b if wider is a else a
            want = wider.preference(last_round=True, topscorer=True).colour
            return (wider, other) if want == WHITE else (other, wider)
    alternate = _alternate_history(a, b)
    if alternate is not None:
        return alternate
    higher, lower = (a, b) if a.tpn < b.tpn else (b, a)
    if higher.tpn % 2 == 1:
        return (higher, lower) if initial_color == WHITE else (lower, higher)
    return (lower, higher) if initial_color == WHITE else (higher, lower)


def _alternate_history(a: PlayerView, b: PlayerView) -> tuple[PlayerView, PlayerView] | None:
    len_a, len_b = len(a.last_colors), len(b.last_colors)
    limit = min(len_a, len_b)
    for offset in range(1, limit + 1):
        ca = a.last_colors[-offset]
        cb = b.last_colors[-offset]
        if ca != cb:
            return (a, b) if ca == BLACK else (b, a)
    return None


def _publish(pairs: list[RawPair], round_index: int) -> tuple[Pairing, ...]:
    def sort_key(pair: RawPair) -> tuple:
        if pair.b is None:
            return (0.0, 0.0, pair.a.tpn)
        higher = pair.a if pair.a.score > pair.b.score or (
            pair.a.score == pair.b.score and pair.a.tpn < pair.b.tpn
        ) else pair.b
        return (-max(pair.a.score, pair.b.score), -(pair.a.score + pair.b.score), higher.tpn)

    ordered = sorted(pairs, key=sort_key)
    published: list[Pairing] = []
    board = 1
    for pair in ordered:
        if pair.b is None:
            published.append(
                Pairing(round_index, board, pair.a.player_id, None, RESULT_BYE)
            )
        else:
            published.append(Pairing(round_index, board, pair.a.player_id, pair.b.player_id))
        board += 1
    return tuple(published)

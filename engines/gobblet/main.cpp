#include <algorithm>
#include <array>
#include <chrono>
#include <compare>
#include <cstdint>
#include <exception>
#include <iostream>
#include <limits>
#include <ranges>
#include <sstream>
#include <string>
#include <vector>

namespace {

using State = std::uint64_t;

constexpr int STM = 1;
constexpr int OPP = 2;
constexpr int MATE = 30000;
constexpr int INF = 32000;
constexpr int MAX_PLY = 96;
constexpr State SWAP_OPP = 0x2AAAAAAAAAAAAAULL;
constexpr State SWAP_STM = 0x15555555555555ULL;
constexpr std::array<int, 9> SQUARE_WEIGHT{2, 1, 2, 1, 4, 1, 2, 1, 2};
constexpr std::array<int, 3> RESERVE_WEIGHT{2, 6, 14};
constexpr std::array<std::array<int, 3>, 8> LINES{{
    {{0, 1, 2}}, {{3, 4, 5}}, {{6, 7, 8}}, {{0, 3, 6}},
    {{1, 4, 7}}, {{2, 5, 8}}, {{0, 4, 8}}, {{2, 4, 6}},
}};
constexpr std::array<std::array<int, 9>, 8> D4{{
    {{0, 1, 2, 3, 4, 5, 6, 7, 8}},
    {{6, 3, 0, 7, 4, 1, 8, 5, 2}},
    {{8, 7, 6, 5, 4, 3, 2, 1, 0}},
    {{2, 5, 8, 1, 4, 7, 0, 3, 6}},
    {{2, 1, 0, 5, 4, 3, 8, 7, 6}},
    {{6, 7, 8, 3, 4, 5, 0, 1, 2}},
    {{0, 3, 6, 1, 4, 7, 2, 5, 8}},
    {{8, 5, 2, 7, 4, 1, 6, 3, 0}},
}};

struct Move {
    std::int8_t start = 127;
    std::int8_t end = 127;

    [[nodiscard]] bool valid() const { return start != 127; }
    auto operator<=>(const Move&) const = default;
};

enum Bound : std::uint8_t { EXACT = 0, LOWER = 1, UPPER = 2 };

struct TTEntry {
    State key = std::numeric_limits<State>::max();
    std::int16_t score = 0;
    std::int8_t depth = -1;
    std::uint8_t bound = EXACT;
    Move move{};
    std::uint8_t generation = 0;
};

static_assert(sizeof(TTEntry) <= 24);

struct TimeUp final : std::exception {};

[[nodiscard]] int square_cell(State state, int square) {
    return static_cast<int>((state >> (6 * square)) & 0x3FULL);
}

[[nodiscard]] std::pair<int, int> top_owner_size(int cell) {
    int owner = 0;
    int size = 0;
    while (cell != 0) {
        owner = cell & 3;
        cell >>= 2;
        ++size;
    }
    return {owner, size};
}

[[nodiscard]] bool can_cover(int cell, int size) {
    return (1 << (2 * (size - 1))) > cell;
}

[[nodiscard]] State swap_sides(State state) {
    return ((state & SWAP_OPP) >> 1) | ((state & SWAP_STM) << 1);
}

[[nodiscard]] State canonical(State state) {
    State best = state;
    for (std::size_t transform = 1; transform < D4.size(); ++transform) {
        State candidate = 0;
        for (int source = 0; source < 9; ++source) {
            candidate |= static_cast<State>(square_cell(state, source))
                << (6 * D4[transform][source]);
        }
        best = std::min(best, candidate);
    }
    return best;
}

[[nodiscard]] State apply_move(State state, Move move, int size) {
    if (move.start >= 0) {
        state ^= 1ULL << (6 * move.start + 2 * (size - 1));
    }
    return state ^ (1ULL << (6 * move.end + 2 * (size - 1)));
}

[[nodiscard]] int move_size(State state, Move move) {
    if (move.start < 0) {
        return -move.start;
    }
    return top_owner_size(square_cell(state, move.start)).second;
}

[[nodiscard]] std::array<int, 3> played_counts(State state, int who = STM) {
    std::array<int, 3> counts{};
    for (int square = 0; square < 9; ++square) {
        const int cell = square_cell(state, square);
        for (int size = 0; size < 3; ++size) {
            if (((cell >> (2 * size)) & 3) == who) {
                ++counts[size];
            }
        }
    }
    return counts;
}

[[nodiscard]] int terminal_value(State state) {
    bool stm_line = false;
    bool opp_line = false;
    for (const auto& line : LINES) {
        const int first = top_owner_size(square_cell(state, line[0])).first;
        if (first == 0) {
            continue;
        }
        const int second = top_owner_size(square_cell(state, line[1])).first;
        const int third = top_owner_size(square_cell(state, line[2])).first;
        if (first == second && second == third) {
            stm_line |= first == STM;
            opp_line |= first == OPP;
        }
    }
    if (stm_line) {
        return 1;
    }
    if (opp_line) {
        return -1;
    }
    return 0;
}

[[nodiscard]] std::array<bool, 9> opponent_line_squares(State state) {
    std::array<bool, 9> result{};
    for (const auto& line : LINES) {
        bool line_is_opponent = true;
        for (int square : line) {
            if (top_owner_size(square_cell(state, square)).first != OPP) {
                line_is_opponent = false;
                break;
            }
        }
        if (line_is_opponent) {
            for (int square : line) {
                result[square] = true;
            }
        }
    }
    return result;
}

[[nodiscard]] std::vector<Move> legal_moves(State state) {
    std::vector<Move> moves;
    moves.reserve(48);
    const auto played = played_counts(state);
    for (int start = 0; start < 9; ++start) {
        const auto [owner, size] = top_owner_size(square_cell(state, start));
        if (owner != STM || size == 0) {
            continue;
        }
        const State lifted = state ^ (1ULL << (6 * start + 2 * (size - 1)));
        const auto forced = opponent_line_squares(lifted);
        const bool has_forced = std::ranges::any_of(forced, [](bool value) { return value; });
        for (int end = 0; end < 9; ++end) {
            if (end == start || (has_forced && !forced[end])) {
                continue;
            }
            if (can_cover(square_cell(state, end), size)) {
                moves.push_back(
                    Move{static_cast<std::int8_t>(start), static_cast<std::int8_t>(end)}
                );
            }
        }
    }
    for (int size = 1; size <= 3; ++size) {
        if (played[size - 1] >= 2) {
            continue;
        }
        for (int end = 0; end < 9; ++end) {
            if (can_cover(square_cell(state, end), size)) {
                moves.push_back(
                    Move{static_cast<std::int8_t>(-size), static_cast<std::int8_t>(end)}
                );
            }
        }
    }
    return moves;
}

[[nodiscard]] bool can_place(State state, int destination, int minimum_size) {
    const int destination_cell = square_cell(state, destination);
    const auto played = played_counts(state);
    for (int size = std::max(minimum_size, 1); size <= 3; ++size) {
        if (played[size - 1] < 2 && can_cover(destination_cell, size)) {
            return true;
        }
    }
    for (int start = 0; start < 9; ++start) {
        if (start == destination) {
            continue;
        }
        const auto [owner, size] = top_owner_size(square_cell(state, start));
        if (owner != STM || size < minimum_size || !can_cover(destination_cell, size)) {
            continue;
        }
        const State lifted = state ^ (1ULL << (6 * start + 2 * (size - 1)));
        const auto forced = opponent_line_squares(lifted);
        const bool has_forced = std::ranges::any_of(forced, [](bool value) { return value; });
        if (!has_forced || forced[destination]) {
            return true;
        }
    }
    return false;
}

[[nodiscard]] std::array<std::pair<int, int>, 9> tops(State state) {
    std::array<std::pair<int, int>, 9> result{};
    for (int square = 0; square < 9; ++square) {
        result[square] = top_owner_size(square_cell(state, square));
    }
    return result;
}

[[nodiscard]] int open_threats(
    const std::array<std::pair<int, int>, 9>& visible,
    int who
) {
    int count = 0;
    for (const auto& line : LINES) {
        int ours = 0;
        int other = 0;
        for (int square : line) {
            const int owner = visible[square].first;
            ours += owner == who;
            other += owner != 0 && owner != who;
        }
        count += ours == 2 && ours + other == 3;
        count += ours == 2 && ours + other == 2;
    }
    return count;
}

[[nodiscard]] bool has_immediate_win(State state) {
    const auto visible = tops(state);
    for (const auto& line : LINES) {
        int ours = 0;
        int empty_square = -1;
        std::pair<int, int> theirs{-1, -1};
        for (int square : line) {
            const auto [owner, size] = visible[square];
            if (owner == STM) {
                ++ours;
            } else if (owner == 0) {
                empty_square = square;
            } else {
                theirs = {square, size};
            }
        }
        if (ours == 2 && empty_square >= 0 && can_place(state, empty_square, 1)) {
            return true;
        }
        if (ours == 2 && theirs.first >= 0 && can_place(state, theirs.first, theirs.second + 1)) {
            return true;
        }
    }
    return false;
}

[[nodiscard]] int evaluate(State state) {
    const int terminal = terminal_value(state);
    if (terminal != 0) {
        return terminal * MATE;
    }
    if (has_immediate_win(state)) {
        return MATE - 1;
    }
    const auto visible = tops(state);
    int score = 0;
    for (int square = 0; square < 9; ++square) {
        if (visible[square].first == STM) {
            score += SQUARE_WEIGHT[square];
        } else if (visible[square].first == OPP) {
            score -= SQUARE_WEIGHT[square];
        }
    }
    const auto threat_score = [](int count) {
        return count >= 2 ? 450 : (count == 1 ? 90 : 0);
    };
    score += threat_score(open_threats(visible, STM));
    score -= threat_score(open_threats(visible, OPP));
    const auto ours = played_counts(state, STM);
    const auto theirs = played_counts(state, OPP);
    for (int size = 0; size < 3; ++size) {
        score += RESERVE_WEIGHT[size] * (2 - ours[size]);
        score -= RESERVE_WEIGHT[size] * (2 - theirs[size]);
    }
    return score;
}

[[nodiscard]] int action_index(Move move) {
    if (move.start < 0) {
        return (-move.start - 1) * 9 + move.end;
    }
    return 27 + move.start * 9 + move.end;
}

[[nodiscard]] std::uint64_t hash_state(State state) {
    state += 0x9E3779B97F4A7C15ULL;
    state = (state ^ (state >> 30)) * 0xBF58476D1CE4E5B9ULL;
    state = (state ^ (state >> 27)) * 0x94D049BB133111EBULL;
    return state ^ (state >> 31);
}

class Searcher {
public:
    explicit Searcher(std::size_t hash_megabytes = 128) {
        std::size_t count = hash_megabytes * 1024ULL * 1024ULL / sizeof(TTEntry);
        std::size_t power = 1;
        while ((power << 1) <= count) {
            power <<= 1;
        }
        table_.resize(power);
        table_mask_ = power - 1;
    }

    struct Result {
        Move move{};
        int score = 0;
        int depth = 0;
        std::uint64_t nodes = 0;
    };

    Result search(State state, int maximum_depth, int milliseconds) {
        deadline_ = Clock::now() + std::chrono::milliseconds(std::max(milliseconds, 1));
        nodes_ = 0;
        ++generation_;
        history_.fill(0);
        for (auto& pair : killers_) {
            pair = {Move{}, Move{}};
        }
        path_.clear();
        path_.push_back(state);

        Result committed;
        auto root_moves = legal_moves(state);
        if (root_moves.empty()) {
            return committed;
        }
        committed.move = root_moves.front();
        for (int depth = 1; depth <= maximum_depth; ++depth) {
            try {
                int alpha = -INF;
                int beta = INF;
                if (depth >= 3 && committed.depth > 0 && std::abs(committed.score) < MATE - 100) {
                    alpha = committed.score - 75;
                    beta = committed.score + 75;
                }
                RootResult iteration;
                int window = 75;
                while (true) {
                    iteration = search_root(state, root_moves, depth, alpha, beta, committed.move);
                    if (iteration.score <= alpha && alpha > -INF) {
                        alpha = std::max(-INF, alpha - window);
                        window *= 2;
                        continue;
                    }
                    if (iteration.score >= beta && beta < INF) {
                        beta = std::min(INF, beta + window);
                        window *= 2;
                        continue;
                    }
                    break;
                }
                committed.move = iteration.move;
                committed.score = iteration.score;
                committed.depth = depth;
                committed.nodes = nodes_;
                root_moves = ordered_moves(state, std::move(root_moves), committed.move, 0);
                std::cout << "info depth " << depth << " score cp " << committed.score
                          << " nodes " << nodes_ << '\n' << std::flush;
            } catch (const TimeUp&) {
                break;
            }
        }
        committed.nodes = nodes_;
        return committed;
    }

private:
    using Clock = std::chrono::steady_clock;

    struct RootResult {
        Move move{};
        int score = -INF;
    };

    std::vector<TTEntry> table_;
    std::size_t table_mask_ = 0;
    std::array<int, 108> history_{};
    std::array<std::array<Move, 2>, MAX_PLY> killers_{};
    std::vector<State> path_;
    Clock::time_point deadline_{};
    std::uint64_t nodes_ = 0;
    std::uint8_t generation_ = 0;

    void check_time() {
        ++nodes_;
        if ((nodes_ & 2047ULL) == 0 && Clock::now() >= deadline_) {
            throw TimeUp{};
        }
    }

    [[nodiscard]] TTEntry* probe(State state) {
        TTEntry& entry = table_[static_cast<std::size_t>(hash_state(state)) & table_mask_];
        return entry.key == state ? &entry : nullptr;
    }

    void store(State state, int depth, int score, Bound bound, Move move) {
        TTEntry& entry = table_[static_cast<std::size_t>(hash_state(state)) & table_mask_];
        if (entry.key != state || entry.generation != generation_ || depth >= entry.depth) {
            entry.key = state;
            entry.score = static_cast<std::int16_t>(score);
            entry.depth = static_cast<std::int8_t>(std::min(depth, 127));
            entry.bound = bound;
            entry.move = move;
            entry.generation = generation_;
        }
    }

    [[nodiscard]] int move_order_score(State state, Move move, Move tt_move, int ply) {
        if (move == tt_move) {
            return 2'000'000;
        }
        const int size = move_size(state, move);
        const State child = swap_sides(apply_move(state, move, size));
        if (terminal_value(child) == -1) {
            return 1'900'000;
        }
        int score = history_[action_index(move)];
        if (ply < MAX_PLY) {
            score += move == killers_[ply][0] ? 80'000 : 0;
            score += move == killers_[ply][1] ? 70'000 : 0;
        }
        const auto child_tops = tops(child);
        score += open_threats(child_tops, OPP) * 5000;
        score -= open_threats(child_tops, STM) * 6000;
        score += SQUARE_WEIGHT[move.end] * 100 - size;
        return score;
    }

    [[nodiscard]] std::vector<Move> ordered_moves(
        State state,
        std::vector<Move> moves,
        Move tt_move,
        int ply
    ) {
        std::stable_sort(moves.begin(), moves.end(), [&](Move left, Move right) {
            return move_order_score(state, left, tt_move, ply)
                > move_order_score(state, right, tt_move, ply);
        });
        return moves;
    }

    RootResult search_root(
        State state,
        const std::vector<Move>& raw_moves,
        int depth,
        int alpha,
        int beta,
        Move previous
    ) {
        TTEntry* hit = probe(state);
        const Move tt_move = hit != nullptr && hit->move.valid() ? hit->move : previous;
        auto moves = ordered_moves(state, raw_moves, tt_move, 0);
        RootResult result;
        const int alpha_original = alpha;
        for (std::size_t index = 0; index < moves.size(); ++index) {
            if (Clock::now() >= deadline_) {
                throw TimeUp{};
            }
            const Move move = moves[index];
            const State child = canonical(
                swap_sides(apply_move(state, move, move_size(state, move)))
            );
            path_.push_back(child);
            int score;
            if (index == 0) {
                score = -negamax(child, depth - 1, -beta, -alpha, 1);
            } else {
                score = -negamax(child, depth - 1, -alpha - 1, -alpha, 1);
                if (alpha < score && score < beta) {
                    score = -negamax(child, depth - 1, -beta, -alpha, 1);
                }
            }
            path_.pop_back();
            if (score > result.score) {
                result.score = score;
                result.move = move;
            }
            alpha = std::max(alpha, score);
            if (alpha >= beta) {
                break;
            }
        }
        Bound bound = EXACT;
        if (result.score <= alpha_original) {
            bound = UPPER;
        } else if (result.score >= beta) {
            bound = LOWER;
        }
        if (std::abs(result.score) < MATE - 100) {
            store(state, depth, result.score, bound, result.move);
        }
        return result;
    }

    int negamax(State state, int depth, int alpha, int beta, int ply) {
        check_time();
        const int terminal = terminal_value(state);
        if (terminal != 0) {
            return terminal * (MATE - ply);
        }
        if (std::count(path_.begin(), path_.end(), state) >= 2) {
            return 0;
        }
        if (depth <= 0 || ply >= MAX_PLY - 1) {
            return evaluate(state);
        }

        const int alpha_original = alpha;
        const int beta_original = beta;
        TTEntry* hit = probe(state);
        Move tt_move{};
        if (hit != nullptr) {
            tt_move = hit->move;
            if (hit->depth >= depth) {
                if (hit->bound == EXACT) {
                    return hit->score;
                }
                if (hit->bound == LOWER) {
                    alpha = std::max(alpha, static_cast<int>(hit->score));
                } else if (hit->bound == UPPER) {
                    beta = std::min(beta, static_cast<int>(hit->score));
                }
                if (alpha >= beta) {
                    return hit->score;
                }
            }
        }

        auto moves = ordered_moves(state, legal_moves(state), tt_move, ply);
        if (moves.empty()) {
            return 0;
        }
        int best = -INF;
        Move best_move{};
        for (std::size_t index = 0; index < moves.size(); ++index) {
            const Move move = moves[index];
            const State child = canonical(
                swap_sides(apply_move(state, move, move_size(state, move)))
            );
            path_.push_back(child);
            int score;
            if (index == 0) {
                score = -negamax(child, depth - 1, -beta, -alpha, ply + 1);
            } else {
                score = -negamax(child, depth - 1, -alpha - 1, -alpha, ply + 1);
                if (alpha < score && score < beta) {
                    score = -negamax(child, depth - 1, -beta, -alpha, ply + 1);
                }
            }
            path_.pop_back();
            if (score > best) {
                best = score;
                best_move = move;
            }
            alpha = std::max(alpha, score);
            if (alpha >= beta) {
                history_[action_index(move)] += depth * depth;
                if (ply < MAX_PLY && move != killers_[ply][0]) {
                    killers_[ply][1] = killers_[ply][0];
                    killers_[ply][0] = move;
                }
                break;
            }
        }
        Bound bound = EXACT;
        if (best <= alpha_original) {
            bound = UPPER;
        } else if (best >= beta_original) {
            bound = LOWER;
        }
        if (std::abs(best) < MATE - 100) {
            store(state, depth, best, bound, best_move);
        }
        return best;
    }

};

[[nodiscard]] State parse_state(const std::string& token) {
    std::size_t consumed = 0;
    const int base = token.starts_with("0x") || token.starts_with("0X") ? 16 : 10;
    const State state = std::stoull(token, &consumed, base);
    if (consumed != token.size()) {
        throw std::invalid_argument("invalid state");
    }
    return state;
}

}  // namespace

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    Searcher searcher;
    State position = 0;
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream input(line);
        std::string command;
        input >> command;
        if (command == "uci") {
            std::cout << "id name ChessCore Gobblet Native\n"
                      << "id author ChessCore\n"
                      << "uciok\n" << std::flush;
        } else if (command == "isready") {
            std::cout << "readyok\n" << std::flush;
        } else if (command == "ucinewgame") {
            position = 0;
        } else if (command == "position") {
            std::string kind;
            std::string value;
            input >> kind >> value;
            if (kind == "key") {
                try {
                    position = parse_state(value);
                } catch (const std::exception&) {
                    std::cout << "info string invalid position\n" << std::flush;
                }
            }
        } else if (command == "go") {
            int milliseconds = 10'000;
            int depth = 64;
            std::string option;
            while (input >> option) {
                if (option == "movetime") {
                    input >> milliseconds;
                } else if (option == "depth") {
                    input >> depth;
                }
            }
            const Searcher::Result result = searcher.search(position, depth, milliseconds);
            std::cout << "bestmove " << static_cast<int>(result.move.start) << ' '
                      << static_cast<int>(result.move.end) << " score " << result.score
                      << " depth " << result.depth << " nodes " << result.nodes
                      << '\n' << std::flush;
        } else if (command == "quit") {
            break;
        }
    }
    return 0;
}

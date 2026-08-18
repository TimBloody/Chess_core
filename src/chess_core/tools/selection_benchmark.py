"""Compare legacy all-side selection work with selected-square generation."""

from __future__ import annotations

from statistics import median
from time import perf_counter

from chess_core.core.movegen import MoveGenerator
from chess_core.modes.chess import classic_chess


def _median_ms(operation, repeats: int = 25) -> float:
    samples: list[float] = []
    for _ in range(repeats):
        started = perf_counter()
        operation()
        samples.append((perf_counter() - started) * 1_000)
    return median(samples)


def main() -> int:
    mode = classic_chess()
    state = mode.initial_state()
    generator = MoveGenerator(mode)
    selected_index = 12  # e2

    all_moves = generator.generate_legal(state)
    selected_moves = generator.generate_legal_for_square(state, selected_index)
    all_ms = _median_ms(lambda: generator.generate_legal(state))
    selected_ms = _median_ms(
        lambda: generator.generate_legal_for_square(state, selected_index)
    )

    print("Classical initial-position selection benchmark")
    print(f"legacy all-side: {len(all_moves)} legal candidates, median {all_ms:.3f} ms")
    print(
        f"selected e2:    {len(selected_moves)} legal candidates, "
        f"median {selected_ms:.3f} ms"
    )
    print(f"candidate work reduction: {len(all_moves) / len(selected_moves):.1f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

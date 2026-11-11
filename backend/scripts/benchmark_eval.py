"""Run with PYTHONPATH=src uv run python scripts/benchmark_eval.py.

Measures a warmed single-thread batch of real, distinct seven-card hands. Reports
encoded kernel throughput separately from the public wrapper's validation/encoding.
"""

from __future__ import annotations

import platform
from time import perf_counter

import numba
import numpy as np
from numpy.random import PCG64, Generator

from pokerbot.domain import full_deck, parse_cards
from pokerbot.eval.equity import equity_vs_range
from pokerbot.eval.evaluator import _rank_batch, rank_hands
from pokerbot.eval.ranges import parse_range


def main() -> None:
    rng = Generator(PCG64(42))
    count = 200_000
    hands = np.asarray([rng.choice(52, 7, replace=False) for _ in range(count)], dtype=np.int64)
    _rank_batch(hands[:1])  # exclude JIT compilation from steady-state timing
    start = perf_counter()
    ranks = _rank_batch(hands)
    elapsed = perf_counter() - start
    rate = count / elapsed
    print(f"{platform.platform()}; Python {platform.python_version()}")
    print(f"NumPy {np.__version__}; Numba {numba.__version__}; phevaluator 0.6 native ABI")
    print(f"Single-thread encoded 7-card kernel: {rate:,.0f} evals/s ({count:,} hands)")
    print(f"Rank checksum: {int(ranks.sum())}")
    deck = full_deck()
    domain_hands = [[deck[int(card)] for card in hand] for hand in hands[:10_000]]
    start = perf_counter()
    rank_hands(domain_hands)
    public_rate = len(domain_hands) / (perf_counter() - start)
    print(f"Public batch including validation/encoding: {public_rate:,.0f} evals/s")
    equity_vs_range(parse_cards("AsAh"), parse_range("KK"), samples=1)  # warm
    start = perf_counter()
    equity = equity_vs_range(parse_cards("AsAh"), parse_range("KK"), samples=50_000, seed=42)
    print(f"AA vs KK (six suit combos), 50k samples: {equity:.5f}; {perf_counter() - start:.4f}s")
    if min(rate, public_rate) < 200_000:
        raise SystemExit("FAIL: evaluator is below 200,000 evals/s")


if __name__ == "__main__":
    main()

"""Heads-up Monte Carlo equity against fixed cards or weighted concrete combos."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numba import njit
from numpy.random import PCG64, Generator
from numpy.typing import NDArray

from pokerbot.domain import Card
from pokerbot.eval.evaluator import _NATIVE_7, encode_cards
from pokerbot.eval.ranges import WeightedCombo


@njit()
def _equity_kernel(
    hero: NDArray[np.int64],
    board: NDArray[np.int64],
    combos: NDArray[np.int64],
    cdf: NDArray[np.float64],
    decks: NDArray[np.int64],
    samples: int,
    rng: Generator,
) -> float:
    h = np.empty(7, dtype=np.int64)
    v = np.empty(7, dtype=np.int64)
    h[:2] = hero
    h[2 : 2 + len(board)] = board
    v[2 : 2 + len(board)] = board
    shares = 0.0
    for _ in range(samples):
        opponent = np.searchsorted(cdf, rng.random(), side="right")
        v[:2] = combos[opponent]
        deck = decks[opponent].copy()
        for j in range(5 - len(board)):
            selected = rng.integers(j, len(deck))
            deck[j], deck[selected] = deck[selected], deck[j]
            h[2 + len(board) + j] = deck[j]
            v[2 + len(board) + j] = deck[j]
        hr = _NATIVE_7(h[0], h[1], h[2], h[3], h[4], h[5], h[6])
        vr = _NATIVE_7(v[0], v[1], v[2], v[3], v[4], v[5], v[6])
        if hr < vr:
            shares += 1.0
        elif hr == vr:
            shares += 0.5
    return shares / samples


def equity_vs_range(
    hero: Sequence[Card],
    combos: Sequence[WeightedCombo],
    board: Sequence[Card] = (),
    *,
    samples: int = 10_000,
    seed: int = 0,
) -> float:
    """Expected pot share. Blocked/zero-weight combos are removed before normalization.

    Repeated/reversed combo weights add. Sampling uses a fresh PCG64 stream and a
    uniform runout without replacement, independent of engine/global RNG state.
    """
    hero_ids = encode_cards(hero, (2,))
    board_ids = encode_cards(board, (0, 3, 4, 5))
    known = set(hero_ids + board_ids)
    if len(known) != 2 + len(board_ids):
        raise ValueError("hero and board cards must be distinct")
    if type(samples) is not int or samples <= 0:
        raise ValueError("samples must be a positive integer")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    eligible = [
        combo
        for combo in combos
        if combo.weight > 0 and not known.intersection(encode_cards(combo.cards, (2,)))
    ]
    if not eligible:
        raise ValueError("range needs a positive-weight unblocked combo")
    # Scale before merging/summing so even repeated weights near float max remain finite.
    scale = max(combo.weight for combo in eligible)
    merged: dict[tuple[int, ...], float] = {}
    for combo in eligible:
        ids = tuple(sorted(encode_cards(combo.cards, (2,))))
        merged[ids] = merged.get(ids, 0.0) + combo.weight / scale
    ids_array = np.asarray(list(merged), dtype=np.int64)
    cdf = np.cumsum(list(merged.values()), dtype=np.float64)
    cdf /= cdf[-1]
    cdf[-1] = 1.0
    decks = np.asarray(
        [
            [card for card in range(52) if card not in known and card not in opponent]
            for opponent in merged
        ],
        dtype=np.int64,
    )
    return _equity_kernel(
        np.asarray(hero_ids, dtype=np.int64),
        np.asarray(board_ids, dtype=np.int64),
        ids_array,
        cdf,
        decks,
        samples,
        Generator(PCG64(seed)),
    )


def equity_vs_hand(
    hero: Sequence[Card],
    villain: Sequence[Card],
    board: Sequence[Card] = (),
    *,
    samples: int = 10_000,
    seed: int = 0,
) -> float:
    """Expected pot share against exactly one opponent hand; ties count one half."""
    encode_cards(villain, (2,))
    combo = WeightedCombo(cards=(villain[0], villain[1]))
    return equity_vs_range(hero, (combo,), board, samples=samples, seed=seed)

"""Validated PH Evaluator wrappers. Ranks 1..7462; smaller means stronger.

The pinned phevaluator 0.6 native ABI exports C evaluators. Keep its library handle
alive and never cache compiled native addresses across processes.
"""

from __future__ import annotations

import ctypes
from collections.abc import Sequence

import numpy as np
from numba import njit
from numpy.typing import NDArray
from phevaluator import _pheval  # type: ignore[import-untyped]

from pokerbot.domain import Card

_LIBRARY = ctypes.CDLL(_pheval.__file__)
_NATIVE_5 = _LIBRARY.evaluate_5cards
_NATIVE_6 = _LIBRARY.evaluate_6cards
_NATIVE_7 = _LIBRARY.evaluate_7cards
for _size, _function in ((5, _NATIVE_5), (6, _NATIVE_6), (7, _NATIVE_7)):
    _function.argtypes = [ctypes.c_int] * _size
    _function.restype = ctypes.c_int
_EVALUATORS = {5: _NATIVE_5, 6: _NATIVE_6, 7: _NATIVE_7}


def encode_cards(cards: Sequence[Card], counts: tuple[int, ...]) -> list[int]:
    """Validate before calling native code, which assumes unique IDs in 0..51."""
    if len(cards) not in counts:
        raise ValueError(f"expected card count in {counts}")
    ids = [(int(card.rank) - 2) * 4 + "cdhs".index(card.suit) for card in cards]
    if any(not 0 <= card_id < 52 for card_id in ids):
        raise ValueError("invalid card ID")
    if len(set(ids)) != len(ids):
        raise ValueError("cards must be distinct")
    return ids


def rank_hand(cards: Sequence[Card]) -> int:
    """Return the best-five PH rank for five, six or seven distinct domain cards."""
    ids = encode_cards(cards, (5, 6, 7))
    return int(_EVALUATORS[len(ids)](*ids))


@njit()
def _rank_batch(hands: NDArray[np.int64]) -> NDArray[np.int64]:
    result = np.empty(len(hands), dtype=np.int64)
    for i in range(len(hands)):
        h = hands[i]
        if hands.shape[1] == 5:
            result[i] = _NATIVE_5(h[0], h[1], h[2], h[3], h[4])
        elif hands.shape[1] == 6:
            result[i] = _NATIVE_6(h[0], h[1], h[2], h[3], h[4], h[5])
        else:
            result[i] = _NATIVE_7(h[0], h[1], h[2], h[3], h[4], h[5], h[6])
    return result


def rank_hands(hands: Sequence[Sequence[Card]]) -> NDArray[np.int64]:
    """Validate/encode uniform-size hands, then evaluate in one compiled batch."""
    if not hands:
        return np.empty(0, dtype=np.int64)
    size = len(hands[0])
    if any(len(hand) != size for hand in hands):
        raise ValueError("batch hands must have the same card count")
    encoded = np.asarray([encode_cards(hand, (5, 6, 7)) for hand in hands], dtype=np.int64)
    return _rank_batch(encoded)

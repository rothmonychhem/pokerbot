"""Deck generation and canonical SHA-256 commitments.

Seed replay requires the locked NumPy environment; saved deck order supports durable replay.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Sequence
from typing import Literal

from numpy.random import PCG64, Generator

from pokerbot.domain import Card, full_deck

ShuffleMode = Literal["play", "sim"]


def shuffled_deck(*, mode: ShuffleMode = "play", seed: int | None = None) -> tuple[Card, ...]:
    """Return a fresh 52-card deck: secure in play, reproducible with an explicit sim seed."""
    cards = full_deck()
    if mode == "play":
        if seed is not None:
            raise ValueError("play mode does not accept a seed")
        secrets.SystemRandom().shuffle(cards)
    elif mode == "sim":
        if type(seed) is not int or seed < 0:
            raise ValueError("sim mode requires a non-negative integer seed")
        Generator(PCG64(seed)).shuffle(cards)
    else:
        raise ValueError(f"unknown shuffle mode: {mode!r}")
    return tuple(cards)


def deck_commitment(deck: Sequence[Card]) -> str:
    """SHA-256 of concatenated two-character card codes, ASCII, in initial draw order."""
    return hashlib.sha256("".join(str(card) for card in deck).encode("ascii")).hexdigest()

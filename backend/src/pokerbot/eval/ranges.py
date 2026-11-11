"""Deterministic expansion of standard hold'em starting-hand notation."""

from __future__ import annotations

import re
from itertools import combinations, product

from pydantic import Field, model_validator

from pokerbot.domain import Card, DomainModel, Rank, Suit, parse_cards

_RANKS = "23456789TJQKA"
_CLASS = re.compile(r"([2-9TJQKA])([2-9TJQKA])([so]?)")
_CONCRETE = re.compile(r"[2-9TJQKA][cdhs][2-9TJQKA][cdhs]")


class WeightedCombo(DomainModel):
    """Two distinct cards in canonical order, with a non-negative finite weight.

    Zero weights are valid but excluded by the equity sampler. Weights are relative,
    not probabilities; the sampler normalizes after applying card-removal blockers.
    """

    cards: tuple[Card, Card]
    weight: float = Field(default=1.0, ge=0, allow_inf_nan=False, strict=True)

    @model_validator(mode="after")
    def _canonical(self) -> WeightedCombo:
        if self.cards[0] == self.cards[1]:
            raise ValueError("combo cards must be distinct")
        if self.cards[1] < self.cards[0]:
            object.__setattr__(self, "cards", (self.cards[1], self.cards[0]))
        return self


def _class_parts(text: str) -> tuple[int, int, str]:
    match = _CLASS.fullmatch(text)
    if match is None:
        raise ValueError(f"invalid hand class: {text!r}")
    first, second, suitedness = match.groups()
    high, low = _RANKS.index(first), _RANKS.index(second)
    if high < low or (high == low and suitedness):
        raise ValueError(f"invalid hand class: {text!r}")
    return high, low, suitedness


def _expand(high: int, low: int, suitedness: str) -> list[tuple[Card, Card]]:
    if high == low:
        cards = [Card(rank=Rank(high + 2), suit=suit) for suit in Suit]
        return list(combinations(cards, 2))
    out = []
    for first, second in product(Suit, repeat=2):
        if (suitedness == "s" and first != second) or (suitedness == "o" and first == second):
            continue
        out.append((Card(rank=Rank(low + 2), suit=second), Card(rank=Rank(high + 2), suit=first)))
    return out


def _token_classes(token: str) -> list[tuple[int, int, str]]:
    if token.endswith("+"):
        high, low, suitedness = _class_parts(token[:-1])
        if high == low:
            return [(rank, rank, "") for rank in range(high, 13)]
        return [(high, rank, suitedness) for rank in range(low, high)]
    if "-" in token:
        pieces = token.split("-")
        if len(pieces) != 2:
            raise ValueError(f"invalid range interval: {token!r}")
        high, low, suitedness = _class_parts(pieces[0])
        end_high, end_low, end_suitedness = _class_parts(pieces[1])
        if high == low and end_high == end_low:
            return [
                (rank, rank, "") for rank in range(min(high, end_high), max(high, end_high) + 1)
            ]
        if high == low or end_high == end_low or high != end_high or suitedness != end_suitedness:
            raise ValueError(f"incompatible range interval: {token!r}")
        return [
            (high, rank, suitedness) for rank in range(min(low, end_low), max(low, end_low) + 1)
        ]
    return [_class_parts(token)]


def parse_range(text: str) -> tuple[WeightedCombo, ...]:
    """Expand classes, plus/interval notation and concrete cards into unique combos.

    For example, ``AKs, TT+, A5s-A2s, KQo``. Pair plus climbs to AA; nonpair
    plus holds the first rank fixed and raises the kicker (``ATs+`` through AKs).
    Tokens overlap by set union, never by increasing a combo's weight.
    """
    combos: set[tuple[Card, Card]] = set()
    for raw in text.split(","):
        token = raw.strip()
        if _CONCRETE.fullmatch(token):
            first, second = parse_cards(token)
            combos.add(WeightedCombo(cards=(first, second)).cards)
        else:
            for high, low, suitedness in _token_classes(token):
                combos.update(_expand(high, low, suitedness))
    return tuple(WeightedCombo(cards=cards) for cards in sorted(combos))

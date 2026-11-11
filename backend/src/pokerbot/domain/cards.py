"""Playing cards."""

from __future__ import annotations

from enum import IntEnum, StrEnum
from functools import total_ordering
from typing import Any

from pydantic import GetJsonSchemaHandler, model_serializer, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from pokerbot.domain.base import DomainModel

_RANK_SYMBOLS = "23456789TJQKA"
CARD_PATTERN = r"^[2-9TJQKA][cdhs]$"


class Rank(IntEnum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14

    @property
    def symbol(self) -> str:
        return _RANK_SYMBOLS[self.value - 2]

    @classmethod
    def from_symbol(cls, symbol: str) -> Rank:
        index = _RANK_SYMBOLS.find(symbol)
        if len(symbol) != 1 or index < 0:
            raise ValueError(f"invalid rank symbol {symbol!r}")
        return cls(index + 2)


class Suit(StrEnum):
    CLUBS = "c"
    DIAMONDS = "d"
    HEARTS = "h"
    SPADES = "s"


_SUIT_ORDER = {suit: i for i, suit in enumerate(Suit)}


@total_ordering
class Card(DomainModel):
    """A card, serialized as its two-character string (e.g. ``"As"``)."""

    rank: Rank
    suit: Suit

    @classmethod
    def parse(cls, text: str) -> Card:
        if not isinstance(text, str) or len(text) != 2:
            raise ValueError(f"invalid card {text!r}: expected 2 characters like 'As'")
        try:
            return cls(rank=Rank.from_symbol(text[0]), suit=Suit(text[1]))
        except ValueError as exc:
            raise ValueError(f"invalid card {text!r}") from exc

    @model_validator(mode="before")
    @classmethod
    def _from_string(cls, data: Any) -> Any:
        if isinstance(data, str):
            if len(data) != 2:
                raise ValueError(f"invalid card {data!r}")
            return {"rank": Rank.from_symbol(data[0]), "suit": Suit(data[1])}
        return data

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        # Same schema for input and output: cards travel as "As"-style strings.
        return {"type": "string", "pattern": CARD_PATTERN, "title": "Card"}

    @model_serializer
    def _to_string(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"{self.rank.symbol}{self.suit.value}"

    def __repr__(self) -> str:
        return f"Card({str(self)!r})"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Card):
            return NotImplemented
        return (self.rank, _SUIT_ORDER[self.suit]) < (other.rank, _SUIT_ORDER[other.suit])


def parse_cards(text: str) -> list[Card]:
    """Parse ``"AsKd Th"`` (space-separated and/or concatenated) into cards."""
    compact = "".join(text.split())
    if len(compact) % 2:
        raise ValueError(f"invalid card list {text!r}")
    return [Card.parse(compact[i : i + 2]) for i in range(0, len(compact), 2)]


def full_deck() -> list[Card]:
    """All 52 cards ordered by rank, then suit (``2c`` ... ``As``)."""
    return [Card(rank=rank, suit=suit) for rank in Rank for suit in Suit]

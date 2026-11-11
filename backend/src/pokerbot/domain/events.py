"""Public events broadcast to every agent (used for modeling, tilt, UI)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, model_validator

from pokerbot.domain.actions import PublicAction, Street
from pokerbot.domain.base import DomainModel
from pokerbot.domain.cards import Card
from pokerbot.domain.observation import MAX_SEATS, MIN_SEATS


class HandStarted(DomainModel):
    kind: Literal["hand_started"] = "hand_started"
    hand_id: str = Field(min_length=1)
    button: int = Field(ge=0)
    stacks: tuple[int, ...] = Field(min_length=MIN_SEATS, max_length=MAX_SEATS)
    small_blind: int = Field(ge=0)
    big_blind: int = Field(gt=0)
    ante: int = Field(default=0, ge=0)
    deck_commitment: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _check_table(self) -> HandStarted:
        if self.button >= len(self.stacks):
            raise ValueError("button must index into stacks")
        if any(stack < 0 for stack in self.stacks):
            raise ValueError("stacks must be non-negative")
        if self.small_blind > self.big_blind:
            raise ValueError("small_blind must not exceed big_blind")
        return self


class PlayerActed(DomainModel):
    kind: Literal["player_acted"] = "player_acted"
    action: PublicAction


_NEW_CARDS = {Street.FLOP: 3, Street.TURN: 1, Street.RIVER: 1}


class StreetDealt(DomainModel):
    """Community cards dealt at the start of ``street`` (only the new cards)."""

    kind: Literal["street_dealt"] = "street_dealt"
    street: Street
    cards: tuple[Card, ...]

    @model_validator(mode="after")
    def _check_count(self) -> StreetDealt:
        expected = _NEW_CARDS.get(self.street)
        if expected is None:
            raise ValueError("no community cards are dealt preflop")
        if len(self.cards) != expected or len(set(self.cards)) != expected:
            raise ValueError(f"{self.street} deals {expected} distinct card(s)")
        return self


class ShowdownRevealed(DomainModel):
    """Hole cards a seat showed by rule at showdown."""

    kind: Literal["showdown_revealed"] = "showdown_revealed"
    seat: int = Field(ge=0)
    cards: tuple[Card, Card]

    @model_validator(mode="after")
    def _distinct(self) -> ShowdownRevealed:
        if self.cards[0] == self.cards[1]:
            raise ValueError("shown cards must be distinct")
        return self


class HandEnded(DomainModel):
    kind: Literal["hand_ended"] = "hand_ended"
    hand_id: str = Field(min_length=1)
    payouts: tuple[int, ...] = Field(min_length=MIN_SEATS, max_length=MAX_SEATS)
    """Net chips won (+) or lost (-), indexed by seat."""


PublicEvent = Annotated[
    HandStarted | PlayerActed | StreetDealt | ShowdownRevealed | HandEnded,
    Field(discriminator="kind"),
]

PUBLIC_EVENT_ADAPTER: TypeAdapter[PublicEvent] = TypeAdapter(PublicEvent)

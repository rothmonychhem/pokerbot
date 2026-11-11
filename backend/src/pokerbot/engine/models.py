"""Hand configuration and result models."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from pokerbot.domain import (
    MAX_SEATS,
    MIN_SEATS,
    ActionType,
    Card,
    DomainModel,
    HandStarted,
    PublicEvent,
    Street,
)
from pokerbot.engine.rng import deck_commitment


class HandConfig(DomainModel):
    hand_id: str = Field(min_length=1)
    # strict: never seat a 1-chip stack from `True` or coerce "100" / 100.0.
    stacks: tuple[Annotated[int, Field(strict=True)], ...] = Field(
        min_length=MIN_SEATS, max_length=MAX_SEATS
    )
    button: int = Field(ge=0, strict=True)
    small_blind: int = Field(gt=0, strict=True)
    big_blind: int = Field(gt=0, strict=True)
    ante: int = Field(default=0, ge=0, strict=True)

    @model_validator(mode="after")
    def _check(self) -> HandConfig:
        if self.button >= len(self.stacks):
            raise ValueError("button must index into stacks")
        if any(stack <= 0 for stack in self.stacks):
            raise ValueError("every seated player needs a positive stack")
        if self.small_blind > self.big_blind:
            raise ValueError("small_blind must not exceed big_blind")
        return self

    @property
    def n_seats(self) -> int:
        return len(self.stacks)


class IllegalActionRecord(DomainModel):
    seat: int = Field(ge=0)
    street: Street
    attempted: str
    reason: str
    applied: ActionType


class DeckAudit(DomainModel):
    """Private completed-hand history: initial draw order and its public commitment."""

    deck: tuple[Card, ...] = Field(min_length=1, max_length=52)
    commitment: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _check(self) -> DeckAudit:
        if len(set(self.deck)) != len(self.deck):
            raise ValueError("audit deck must contain unique cards")
        if deck_commitment(self.deck) != self.commitment:
            raise ValueError("audit deck does not match its commitment")
        return self


class HandResult(DomainModel):
    """Full (private) outcome of a hand, including every player's hole cards."""

    hand_id: str
    starting_stacks: tuple[int, ...]
    final_stacks: tuple[int, ...]
    payouts: tuple[int, ...]
    board: tuple[Card, ...]
    hole_cards: tuple[tuple[Card, Card], ...]
    events: tuple[PublicEvent, ...]
    illegal_actions: tuple[IllegalActionRecord, ...] = ()
    deck_audit: DeckAudit | None = None

    @model_validator(mode="after")
    def _check(self) -> HandResult:
        n = len(self.starting_stacks)
        if not len(self.final_stacks) == len(self.payouts) == len(self.hole_cards) == n:
            raise ValueError("per-seat tuples must all have one entry per seat")
        expected = tuple(
            f - s for f, s in zip(self.final_stacks, self.starting_stacks, strict=True)
        )
        if self.payouts != expected:
            raise ValueError("payouts must equal final minus starting stacks")
        if sum(self.payouts) != 0:
            raise ValueError("chips are not conserved")
        if self.deck_audit is not None and (
            not self.events
            or not isinstance(self.events[0], HandStarted)
            or self.events[0].deck_commitment != self.deck_audit.commitment
        ):
            raise ValueError("audit must match the hand start commitment")
        return self

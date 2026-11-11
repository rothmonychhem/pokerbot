"""The information set handed to an agent."""

from __future__ import annotations

from pydantic import Field, model_validator

from pokerbot.domain.actions import ActionType, PublicAction, Street
from pokerbot.domain.base import DomainModel
from pokerbot.domain.cards import Card

MIN_SEATS = 2
MAX_SEATS = 9


class Observation(DomainModel):
    """Everything one seat may know at decision time. Never contains opponents' hole cards.

    Collections are tuples so one agent can never mutate state shared with the engine.
    """

    hand_id: str = Field(min_length=1)
    seat: int = Field(ge=0)
    hole_cards: tuple[Card, Card]
    board: tuple[Card, ...]
    street: Street
    pot: int = Field(ge=0)
    stacks: tuple[int, ...] = Field(min_length=MIN_SEATS, max_length=MAX_SEATS)
    to_call: int = Field(ge=0)
    min_raise: int = Field(ge=0)
    max_raise: int = Field(ge=0)
    action_history: tuple[PublicAction, ...]
    button: int = Field(ge=0)
    small_blind: int = Field(ge=0)
    big_blind: int = Field(gt=0)
    legal_actions: tuple[ActionType, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_consistency(self) -> Observation:
        n = len(self.stacks)
        if self.seat >= n or self.button >= n:
            raise ValueError("seat and button must index into stacks")
        if any(stack < 0 for stack in self.stacks):
            raise ValueError("stacks must be non-negative")
        if len(self.board) != self.street.board_size:
            raise ValueError(f"{self.street} requires {self.street.board_size} board cards")
        visible = [*self.hole_cards, *self.board]
        if len(set(visible)) != len(visible):
            raise ValueError("duplicate cards between hole cards and board")
        if len(set(self.legal_actions)) != len(self.legal_actions):
            raise ValueError("legal_actions must be unique")
        if self.small_blind > self.big_blind:
            raise ValueError("small_blind must not exceed big_blind")
        legal = set(self.legal_actions)
        if {ActionType.CHECK, ActionType.CALL} <= legal:
            raise ValueError("check and call cannot both be legal")
        if {ActionType.BET, ActionType.RAISE} <= legal:
            raise ValueError("bet and raise cannot both be legal")
        if ActionType.CHECK in legal and self.to_call != 0:
            raise ValueError("check is only legal when to_call == 0")
        if ActionType.CALL in legal and self.to_call == 0:
            raise ValueError("call requires to_call > 0")
        if legal & {ActionType.BET, ActionType.RAISE} and not 0 < self.min_raise <= self.max_raise:
            raise ValueError("bet/raise legal requires 0 < min_raise <= max_raise")
        for past in self.action_history:
            if past.seat >= n:
                raise ValueError(f"action_history seat {past.seat} is not at the table")
            if past.street.order > self.street.order:
                raise ValueError("action_history contains a future street")
        return self

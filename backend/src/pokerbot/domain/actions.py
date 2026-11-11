"""Streets, decision actions and public (observed) actions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from pokerbot.domain.base import DomainModel


class Street(StrEnum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"

    @property
    def board_size(self) -> int:
        return (0, 3, 4, 5)[self.order]

    @property
    def order(self) -> int:
        """0 for preflop ... 3 for river (streets are ordered)."""
        return list(Street).index(self)


class ActionType(StrEnum):
    """Decisions an agent can take."""

    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"


class ForcedBetType(StrEnum):
    ANTE = "ante"
    SMALL_BLIND = "small_blind"
    BIG_BLIND = "big_blind"


_SIZED = frozenset({ActionType.BET, ActionType.RAISE})
_UNSIZED = frozenset({ActionType.FOLD, ActionType.CHECK})


class Action(DomainModel):
    """An agent decision. For bet/raise, ``amount`` is the total bet-to for the street."""

    type: ActionType
    # strict: reject true / 1.0 / "100" from buggy bots or clients instead of coercing.
    amount: int | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def _check_amount(self) -> Action:
        if self.type in _SIZED and (self.amount is None or self.amount <= 0):
            raise ValueError(f"{self.type} requires a positive amount (total bet-to)")
        if self.type in _UNSIZED and self.amount is not None:
            raise ValueError(f"{self.type} must not have an amount")
        if self.amount is not None and self.amount < 0:
            raise ValueError("amount must be non-negative")
        return self

    @classmethod
    def fold(cls) -> Action:
        return cls(type=ActionType.FOLD)

    @classmethod
    def check(cls) -> Action:
        return cls(type=ActionType.CHECK)

    @classmethod
    def call(cls) -> Action:
        return cls(type=ActionType.CALL)

    @classmethod
    def bet(cls, to: int) -> Action:
        return cls(type=ActionType.BET, amount=to)

    @classmethod
    def raise_to(cls, to: int) -> Action:
        return cls(type=ActionType.RAISE, amount=to)


class PublicAction(DomainModel):
    """An action visible to every seat (including forced bets)."""

    seat: int = Field(ge=0)
    street: Street
    kind: ActionType | ForcedBetType
    amount: int | None = Field(default=None, ge=0)
    """bet/raise/call: the player's total bet on this street after the action.
    Forced bets: chips posted. Fold/check: None."""
    all_in: bool = False

    @model_validator(mode="after")
    def _check_kind(self) -> PublicAction:
        if isinstance(self.kind, ForcedBetType):
            if self.street is not Street.PREFLOP:
                raise ValueError("forced bets are only posted preflop")
            if self.amount is None:
                raise ValueError(f"{self.kind} requires an amount")
        elif self.kind in _SIZED and not self.amount:
            raise ValueError(f"{self.kind} requires a positive amount (total bet-to)")
        elif self.kind in _UNSIZED and self.amount is not None:
            raise ValueError(f"{self.kind} must not have an amount")
        return self

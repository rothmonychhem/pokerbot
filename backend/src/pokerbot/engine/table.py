"""Synchronous cash-game sessions with stable physical seats and a moving button."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import Field, model_validator

from pokerbot.agents.base import Agent
from pokerbot.domain import Action, Card, DomainModel, Observation, PublicEvent
from pokerbot.engine.errors import EngineError
from pokerbot.engine.hand_runner import run_hand
from pokerbot.engine.history import HandHistory, map_event
from pokerbot.engine.models import HandConfig
from pokerbot.engine.rng import ShuffleMode

logger = logging.getLogger(__name__)
_StrictInt = Annotated[int, Field(strict=True)]


class TableConfig(DomainModel):
    table_id: str = Field(default="table", min_length=1)
    stacks: tuple[_StrictInt, ...] = Field(min_length=2, max_length=9)
    button: int = Field(default=0, ge=0, strict=True)
    small_blind: int = Field(default=1, gt=0, strict=True)
    big_blind: int = Field(default=2, gt=0, strict=True)
    ante: int = Field(default=0, ge=0, strict=True)
    sitting_out: tuple[_StrictInt, ...] = ()
    rebuy_policy: Literal["none", "manual", "auto"] = "none"
    rebuy_to: int | None = Field(default=None, gt=0, strict=True)
    mode: ShuffleMode = "play"
    seed: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def _check(self) -> TableConfig:
        if any(stack < 0 for stack in self.stacks):
            raise ValueError("stacks must be nonnegative")
        if self.button >= len(self.stacks):
            raise ValueError("button must index into stacks")
        if self.small_blind > self.big_blind:
            raise ValueError("small_blind must not exceed big_blind")
        if len(set(self.sitting_out)) != len(self.sitting_out) or any(
            not 0 <= seat < len(self.stacks) for seat in self.sitting_out
        ):
            raise ValueError("sitting_out must contain unique valid seats")
        if (self.rebuy_policy == "auto") != (self.rebuy_to is not None):
            raise ValueError("rebuy_to is required only for auto rebuy policy")
        if (self.mode == "sim") != (self.seed is not None):
            raise ValueError("sim mode requires a seed; play mode rejects a seed")
        return self


class _SeatAgent:
    """Translate only decision views; the session callback broadcasts events once."""

    def __init__(self, agent: Agent, seats: tuple[int, ...], stacks: tuple[int, ...]) -> None:
        self.agent, self.seats, self.stacks = agent, seats, stacks

    def decide(self, obs: Observation) -> Action:
        stacks = list(self.stacks)
        for dense, physical in enumerate(self.seats):
            stacks[physical] = obs.stacks[dense]
        mapped = obs.model_copy(
            update={
                "seat": self.seats[obs.seat],
                "button": self.seats[obs.button],
                "stacks": tuple(stacks),
                "action_history": tuple(
                    action.model_copy(update={"seat": self.seats[action.seat]})
                    for action in obs.action_history
                ),
            }
        )
        return self.agent.decide(mapped)

    def observe(self, event: PublicEvent) -> None:
        return None


class TableSession:
    """Play hands serially. State mutations/rebuys are allowed only between hands.

    Hand histories are private. Agents see physical-seat observations/public events,
    including when sitting out. A failed hand leaves session bookkeeping unchanged;
    callbacks already delivered to agents cannot be rolled back.
    """

    def __init__(self, config: TableConfig, agents: Sequence[Agent]) -> None:
        if len(agents) != len(config.stacks):
            raise EngineError("expected agents for every physical seat")
        self._config = config
        self._agents = tuple(agents)
        self._stacks = list(config.stacks)
        self._sitting_out = set(config.sitting_out)
        self._rebuy_totals = [0] * len(agents)
        self._history: list[HandHistory] = []
        self._last_button: int | None = None
        self._running = False

    @property
    def config(self) -> TableConfig:
        return self._config

    @property
    def stacks(self) -> tuple[int, ...]:
        return tuple(self._stacks)

    @property
    def history(self) -> tuple[HandHistory, ...]:
        return tuple(self._history)

    @property
    def sitting_out(self) -> tuple[int, ...]:
        return tuple(sorted(self._sitting_out))

    @property
    def rebuy_totals(self) -> tuple[int, ...]:
        return tuple(self._rebuy_totals)

    def _ensure_idle(self) -> None:
        if self._running:
            raise EngineError("a hand is already running")

    def _check_seat(self, seat: int) -> None:
        if type(seat) is not int or not 0 <= seat < len(self._agents):
            raise EngineError("invalid physical seat")

    def sit_out(self, seat: int) -> None:
        self._ensure_idle()
        self._check_seat(seat)
        self._sitting_out.add(seat)

    def sit_in(self, seat: int) -> None:
        self._ensure_idle()
        self._check_seat(seat)
        self._sitting_out.discard(seat)

    def rebuy(self, seat: int, amount: int) -> None:
        self._ensure_idle()
        self._check_seat(seat)
        if self.config.rebuy_policy == "none":
            raise EngineError("rebuys are disabled")
        if type(amount) is not int or amount <= 0:
            raise EngineError("rebuy amount must be a positive integer")
        self._stacks[seat] += amount
        self._rebuy_totals[seat] += amount

    def play_hand(self, deck: Sequence[Card] | None = None) -> HandHistory | None:
        self._ensure_idle()
        self._running = True
        try:
            stacks = list(self._stacks)
            added = [0] * len(stacks)
            if self.config.rebuy_policy == "auto":
                target = self.config.rebuy_to
                assert target is not None  # TableConfig invariant
                for seat in range(len(stacks)):
                    if stacks[seat] == 0 and seat not in self._sitting_out:
                        stacks[seat] = added[seat] = target
            seats = tuple(
                s for s, chips in enumerate(stacks) if chips > 0 and s not in self._sitting_out
            )
            if len(seats) < 2:
                return None
            start = self.config.button if self._last_button is None else self._last_button + 1
            button = next(
                (start + offset) % len(stacks)
                for offset in range(len(stacks))
                if (start + offset) % len(stacks) in seats
            )
            config = HandConfig(
                hand_id=f"{self.config.table_id}-{len(self._history) + 1}",
                stacks=tuple(stacks[s] for s in seats),
                button=seats.index(button),
                small_blind=self.config.small_blind,
                big_blind=self.config.big_blind,
                ante=self.config.ante,
            )
            table_stacks = tuple(stacks)
            adapters = [_SeatAgent(self._agents[s], seats, table_stacks) for s in seats]

            def broadcast(event: PublicEvent) -> None:
                mapped = map_event(event, seats, table_stacks)
                for seat, agent in enumerate(self._agents):
                    try:
                        agent.observe(mapped)
                    except Exception:
                        logger.exception("table observer at seat %d failed", seat)

            if deck is not None:
                result = run_hand(config, adapters, deck, on_event=broadcast)
            else:
                seed = None if self.config.seed is None else self.config.seed + len(self._history)
                result = run_hand(
                    config, adapters, mode=self.config.mode, seed=seed, on_event=broadcast
                )
            history = HandHistory(
                config=config, result=result, seats=seats, table_stacks=table_stacks
            )
            for dense, physical in enumerate(seats):
                stacks[physical] = result.final_stacks[dense]
            self._stacks = stacks
            self._rebuy_totals = [
                old + new for old, new in zip(self._rebuy_totals, added, strict=True)
            ]
            self._last_button = button
            self._history.append(history)
            return history
        finally:
            self._running = False

    def play(self, hands: int) -> tuple[HandHistory, ...]:
        self._ensure_idle()
        if type(hands) is not int or hands < 0:
            raise EngineError("hands must be a nonnegative integer")
        played = []
        for _ in range(hands):
            history = self.play_hand()
            if history is None:
                break
            played.append(history)
        return tuple(played)

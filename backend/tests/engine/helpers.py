"""Test helpers: scripted/random agents and stacked decks."""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping

from pokerbot.domain import (
    Action,
    ActionType,
    Card,
    Observation,
    PublicEvent,
    full_deck,
    parse_cards,
)
from pokerbot.engine.seating import seat_of


class RecordingAgent:
    """Base agent that records everything it sees."""

    def __init__(self) -> None:
        self.observations: list[Observation] = []
        self.events: list[PublicEvent] = []

    def decide(self, obs: Observation) -> Action:
        self.observations.append(obs)
        return self.choose(obs)

    def choose(self, obs: Observation) -> Action:
        return Action.check() if ActionType.CHECK in obs.legal_actions else Action.call()

    def observe(self, event: PublicEvent) -> None:
        self.events.append(event)


class ScriptedAgent(RecordingAgent):
    def __init__(self, actions: Iterable[Action]) -> None:
        super().__init__()
        self.script = list(actions)

    def choose(self, obs: Observation) -> Action:
        return self.script.pop(0) if self.script else super().choose(obs)


class RaisingAgent(RecordingAgent):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def choose(self, obs: Observation) -> Action:
        raise self.error


class RandomLegalAgent(RecordingAgent):
    """Uniform over legal actions; optionally injects illegal actions."""

    def __init__(self, rng: random.Random, illegal_rate: float = 0.0) -> None:
        super().__init__()
        self.rng = rng
        self.illegal_rate = illegal_rate

    def choose(self, obs: Observation) -> Action:
        if self.rng.random() < self.illegal_rate:
            return self.rng.choice(
                [Action.check(), Action.raise_to(1), Action.bet(10**9), Action.fold()]
            )
        kind = self.rng.choice(obs.legal_actions)
        if kind in (ActionType.BET, ActionType.RAISE):
            amount = self.rng.randint(obs.min_raise, obs.max_raise)
            return Action(type=kind, amount=amount)
        return Action(type=kind)


def stacked_deck(button: int, holes: Mapping[int, str], board: str = "") -> list[Card]:
    """Deck order: hole cards round-robin in PokerKit dealee order, then burn/board cards."""
    n = len(holes)
    hole_cards = {seat: parse_cards(text) for seat, text in holes.items()}
    board_cards = parse_cards(board)
    used = {c for cards in hole_cards.values() for c in cards} | set(board_cards)
    spare = [c for c in full_deck() if c not in used]
    order: list[Card] = []
    for round_ in range(2):
        for pk_index in range(n):
            order.append(hole_cards[seat_of(pk_index, button, n)][round_])
    flop, turn, river = board_cards[:3], board_cards[3:4], board_cards[4:5]
    for street in (flop, turn, river):
        if street:
            order.append(spare.pop())
            order.extend(street)
    rest = [c for c in full_deck() if c not in set(order)]
    return order + rest

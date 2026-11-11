"""Trivial legal-action reference policies for simulation sanity checks."""

from __future__ import annotations

import random

from pokerbot.domain import Action, ActionType, Observation, PublicEvent


def _passive_action(obs: Observation) -> Action:
    for kind in (ActionType.CHECK, ActionType.CALL, ActionType.FOLD):
        if kind in obs.legal_actions:
            return Action(type=kind)
    # A validated Observation may offer only a bet or a raise.
    return Action(type=obs.legal_actions[0], amount=obs.min_raise)


class _BaselineAgent:
    def observe(self, event: PublicEvent) -> None:
        """Reference policies do not learn from or retain public events."""
        return None


class RandomAgent(_BaselineAgent):
    """Uniform legal action type, then uniform inclusive integer sizing if needed.

    A private stdlib RNG supports arbitrary-size chip integers without affecting
    global randomness or the engine's secure/seeded deck generator.
    """

    def __init__(self, seed: int | None = None) -> None:
        if seed is not None and (type(seed) is not int or seed < 0):
            raise ValueError("seed must be a non-negative integer or None")
        self._rng = random.Random(seed)

    def decide(self, obs: Observation) -> Action:
        kind = self._rng.choice(obs.legal_actions)
        if kind in (ActionType.BET, ActionType.RAISE):
            return Action(type=kind, amount=self._rng.randint(obs.min_raise, obs.max_raise))
        return Action(type=kind)


class CallingStationAgent(_BaselineAgent):
    """Check or call whenever possible, with a legal fallback for restricted views."""

    def decide(self, obs: Observation) -> Action:
        return _passive_action(obs)


class RaiseAgent(_BaselineAgent):
    """Minimum raise when facing a bet; otherwise open for a clamped pot-sized bet."""

    def decide(self, obs: Observation) -> Action:
        if ActionType.RAISE in obs.legal_actions:
            return Action.raise_to(obs.min_raise)
        if ActionType.BET in obs.legal_actions:
            return Action.bet(min(obs.max_raise, max(obs.min_raise, obs.pot)))
        return _passive_action(obs)

"""The agent contract every bot implements."""

from typing import Protocol, runtime_checkable

from pokerbot.domain import Action, Observation, PublicEvent


@runtime_checkable
class Agent(Protocol):
    def decide(self, obs: Observation) -> Action:
        """Choose an action given this seat's information set."""
        ...

    def observe(self, event: PublicEvent) -> None:
        """Receive a public event (actions, streets, showdowns, results)."""
        ...


__all__ = ["Action", "Agent", "Observation", "PublicEvent"]

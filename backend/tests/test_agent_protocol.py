from pokerbot.agents.base import Action, Agent, Observation, PublicEvent


class _AlwaysCheck:
    def decide(self, obs: Observation) -> Action:
        return Action.check()

    def observe(self, event: PublicEvent) -> None:
        return None


class _NoObserve:
    def decide(self, obs: Observation) -> Action:
        return Action.fold()


def test_structural_agent_matches_protocol() -> None:
    agent: Agent = _AlwaysCheck()
    assert isinstance(agent, Agent)


def test_missing_observe_does_not_match() -> None:
    assert not isinstance(_NoObserve(), Agent)

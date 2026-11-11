import logging
import random
from typing import Any

import pytest

from pokerbot.agents import CallingStationAgent, RaiseAgent, RandomAgent
from pokerbot.agents.base import Agent
from pokerbot.domain import Action, ActionType, HandEnded, Observation
from pokerbot.engine.hand_runner import run_hand
from pokerbot.engine.models import HandConfig
from pokerbot.engine.table import TableConfig, TableSession
from tests.domain.test_observation import _base


def view(**overrides: Any) -> Observation:
    return Observation(**_base(**overrides))


@pytest.mark.parametrize("agent", [RandomAgent(0), CallingStationAgent(), RaiseAgent()])
def test_agents_implement_protocol_and_observe_without_retaining_events(agent: Agent) -> None:
    assert isinstance(agent, Agent)
    before = dict(vars(agent))
    event = HandEnded(hand_id="h", payouts=(-1, 1))
    assert agent.observe(event) is None
    assert vars(agent) == before


@pytest.mark.parametrize(
    "legal,to_call,expected",
    [
        ((ActionType.CHECK, ActionType.BET), 0, Action.check()),
        ((ActionType.FOLD, ActionType.CALL, ActionType.RAISE), 20, Action.call()),
        ((ActionType.FOLD,), 20, Action.fold()),
        ((ActionType.BET,), 0, Action.bet(100)),
        ((ActionType.RAISE,), 20, Action.raise_to(100)),
    ],
)
def test_calling_station_uses_passive_legal_fallbacks(legal, to_call, expected) -> None:
    assert CallingStationAgent().decide(view(legal_actions=legal, to_call=to_call)) == expected


@pytest.mark.parametrize(
    "pot,minimum,maximum,expected",
    [
        (300, 100, 1000, 300),
        (0, 100, 1000, 100),
        (300, 100, 200, 200),
        (300, 50, 50, 50),
    ],
)
def test_raise_agent_clamps_opening_pot_bet(
    pot: int, minimum: int, maximum: int, expected: int
) -> None:
    obs = view(pot=pot, min_raise=minimum, max_raise=maximum)
    assert RaiseAgent().decide(obs) == Action.bet(expected)


def test_raise_agent_uses_minimum_raise_including_short_all_in() -> None:
    for minimum, maximum in ((100, 1000), (70, 70)):
        obs = view(
            legal_actions=(ActionType.FOLD, ActionType.CALL, ActionType.RAISE),
            to_call=20,
            min_raise=minimum,
            max_raise=maximum,
        )
        assert RaiseAgent().decide(obs) == Action.raise_to(minimum)


@pytest.mark.parametrize(
    "legal,to_call,expected",
    [
        ((ActionType.CHECK,), 0, Action.check()),
        ((ActionType.CALL, ActionType.FOLD), 20, Action.call()),
        ((ActionType.FOLD,), 20, Action.fold()),
    ],
)
def test_raise_agent_passive_fallbacks(legal, to_call, expected) -> None:
    assert RaiseAgent().decide(view(legal_actions=legal, to_call=to_call)) == expected


def test_random_agent_equal_seeds_and_independent_instances() -> None:
    first, second = RandomAgent(42), RandomAgent(42)
    obs = view()
    expected = [first.decide(obs) for _ in range(100)]
    RandomAgent(99).decide(obs)
    assert [second.decide(obs) for _ in range(100)] == expected
    assert len(set(expected)) > 2


def test_random_agent_samples_each_action_type_and_inclusive_sizing_bounds() -> None:
    agent = RandomAgent(123)
    for legal, to_call in (
        ((ActionType.CHECK, ActionType.BET), 0),
        ((ActionType.FOLD, ActionType.CALL, ActionType.RAISE), 1),
    ):
        obs = view(legal_actions=legal, to_call=to_call, min_raise=10, max_raise=12)
        actions = [agent.decide(obs) for _ in range(1000)]
        assert {a.type for a in actions} == set(legal)
        assert {a.amount for a in actions if a.amount is not None} == {10, 11, 12}
    assert agent.decide(
        view(legal_actions=(ActionType.BET,), min_raise=2, max_raise=2)
    ) == Action.bet(2)


def test_arbitrary_size_chip_bounds_and_global_rng_isolation() -> None:
    random.seed(123)
    expected = random.random()
    random.seed(123)
    obs = view(legal_actions=(ActionType.BET,), min_raise=2**80, max_raise=2**81)
    action = RandomAgent(42).decide(obs)
    assert 2**80 <= action.amount <= 2**81
    assert random.random() == expected
    RandomAgent().decide(view())


@pytest.mark.parametrize("seed", [-1, True, 1.5, "42"])
def test_invalid_random_seeds(seed: object) -> None:
    with pytest.raises(ValueError, match="seed"):
        RandomAgent(seed)


def test_baselines_integrate_with_seeded_sessions_without_fallbacks() -> None:
    def play():
        players = [RandomAgent(1), CallingStationAgent(), RaiseAgent()]
        session = TableSession(
            TableConfig(stacks=(50, 50, 50), mode="sim", seed=42, rebuy_policy="auto", rebuy_to=50),
            players,
        )
        return session.play(10)

    first, second = play(), play()
    assert len(first) == 10 and first == second
    assert all(not hand.result.illegal_actions for hand in first)


@pytest.mark.slow
def test_all_baselines_play_1000_hands_without_errors(caplog: pytest.LogCaptureFixture) -> None:
    rng = random.Random(2001)
    players: list[Agent] = [RandomAgent(7), CallingStationAgent(), RaiseAgent()]
    caplog.set_level(logging.WARNING)
    for hand in range(1000):
        n = rng.randint(3, 9)
        lineup = players + [RandomAgent(hand * 10 + s) for s in range(n - 3)]
        bb = rng.choice((2, 10))
        config = HandConfig(
            hand_id=f"baseline-{hand}",
            button=rng.randrange(n),
            stacks=tuple(rng.randint(1, 40) * bb for _ in range(n)),
            small_blind=bb // 2,
            big_blind=bb,
            ante=rng.choice((0, 1)),
        )
        result = run_hand(config, lineup, mode="sim", seed=hand)
        assert not result.illegal_actions
        assert sum(result.final_stacks) == sum(config.stacks)
    assert not caplog.records

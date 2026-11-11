import random
from unittest.mock import patch

import pytest

from pokerbot.domain import Action, ActionType, HandStarted, PlayerActed, full_deck
from pokerbot.engine.hand_runner import EngineError, run_hand
from pokerbot.engine.models import HandResult
from pokerbot.engine.rng import deck_commitment
from tests.engine.helpers import RandomLegalAgent, RecordingAgent, ScriptedAgent, stacked_deck
from tests.engine.test_hand_runner import cfg


def _replay_agents(result: HandResult) -> list[ScriptedAgent]:
    scripts: list[list[Action]] = [[] for _ in result.starting_stacks]
    for event in result.events:
        if isinstance(event, PlayerActed) and isinstance(event.action.kind, ActionType):
            action = event.action
            # Public CALL amounts are street totals, while Action.call() takes no amount.
            amount = action.amount if action.kind in (ActionType.BET, ActionType.RAISE) else None
            scripts[action.seat].append(Action(type=action.kind, amount=amount))
    return [ScriptedAgent(script) for script in scripts]


@pytest.mark.parametrize("n", [2, 3, 6, 9])
def test_seed_and_recorded_action_log_replay_bit_identically(n: int) -> None:
    config = cfg(tuple(20 + 10 * s for s in range(n)), button=n - 1, ante=1)
    agents = [RandomLegalAgent(random.Random(s)) for s in range(n)]
    original = run_hand(config, agents, mode="sim", seed=12345)
    assert not original.illegal_actions
    replay_agents = _replay_agents(original)
    replayed = run_hand(config, replay_agents, mode="sim", seed=12345)
    assert replayed.model_dump_json() == original.model_dump_json()
    assert all(not agent.script for agent in replay_agents)
    assert original.deck_audit is not None
    restored = HandResult.model_validate_json(original.model_dump_json())
    assert restored == original and restored.deck_audit is not None
    from_deck = run_hand(config, _replay_agents(original), restored.deck_audit.deck)
    assert from_deck.model_dump_json() == original.model_dump_json()


def test_default_runner_uses_secure_shuffle_and_commits_before_callbacks() -> None:
    with patch("pokerbot.engine.rng.secrets.SystemRandom") as secure:
        result = run_hand(cfg((100, 100)), [RecordingAgent(), RecordingAgent()])
    secure.return_value.shuffle.assert_called_once()
    assert result.deck_audit is not None
    assert result.deck_audit.deck == tuple(full_deck())
    assert isinstance(result.events[0], HandStarted)
    assert result.events[0].deck_commitment == result.deck_audit.commitment
    assert "deck_audit" not in result.events[0].model_dump()


def test_explicit_deck_is_snapshotted_before_agent_callbacks() -> None:
    deck = full_deck()
    expected = tuple(deck)

    class MutatingAgent(RecordingAgent):
        def observe(self, event: object) -> None:
            if isinstance(event, HandStarted):
                assert event.deck_commitment == deck_commitment(expected)
                deck.reverse()
            super().observe(event)  # type: ignore[arg-type]

    agent = MutatingAgent()
    result = run_hand(cfg((100, 100)), [agent, RecordingAgent()], deck)
    assert result.deck_audit is not None and result.deck_audit.deck == expected
    assert isinstance(agent.events[0], HandStarted)
    assert deck != list(expected)
    baseline = run_hand(cfg((100, 100)), [RecordingAgent(), RecordingAgent()], expected)
    assert result == baseline


@pytest.mark.parametrize("kw", [{"mode": "sim"}, {"seed": 0}, {"mode": "other"}])
def test_generated_deck_rejects_invalid_options_before_events(kw: dict[str, object]) -> None:
    agents = [RecordingAgent(), RecordingAgent()]
    with pytest.raises(ValueError):
        run_hand(cfg((100, 100)), agents, **kw)  # type: ignore[arg-type]
    assert all(not agent.events for agent in agents)


@pytest.mark.parametrize("kw", [{"mode": "sim"}, {"seed": 0}, {"mode": "other"}])
def test_explicit_deck_rejects_ambiguous_rng_options_before_events(kw: dict[str, object]) -> None:
    agents = [RecordingAgent(), RecordingAgent()]
    with pytest.raises(EngineError):
        run_hand(cfg((100, 100)), agents, full_deck(), **kw)  # type: ignore[arg-type]
    assert all(not agent.events for agent in agents)


def test_explicit_partial_deck_audits_original_order() -> None:
    deck = full_deck()[:12]
    original = tuple(deck)
    result = run_hand(cfg((100, 100)), [RecordingAgent(), RecordingAgent()], deck)
    assert tuple(deck) == original
    assert result.deck_audit is not None and result.deck_audit.deck == original


def test_side_pot_action_log_replays_from_audit_deck() -> None:
    config = cfg((100, 50, 20), button=2)
    deck = stacked_deck(2, {0: "AsAh", 1: "7s7h", 2: "QsQh"}, "Qd7c2h9s4d")
    agents = [ScriptedAgent([Action.raise_to(100)]), ScriptedAgent([Action.call()]),
              ScriptedAgent([Action.raise_to(20)])]
    original = run_hand(config, agents, deck)
    assert original.final_stacks == (50, 60, 60)
    assert original.deck_audit is not None
    assert run_hand(config, _replay_agents(original), original.deck_audit.deck) == original

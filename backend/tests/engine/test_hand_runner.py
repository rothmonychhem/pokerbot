import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pokerbot.domain import (
    Action,
    ActionType,
    Card,
    ForcedBetType,
    HandEnded,
    HandStarted,
    PlayerActed,
    ShowdownRevealed,
    Street,
    StreetDealt,
    full_deck,
    parse_cards,
)
from pokerbot.engine.hand_runner import EngineError, run_hand
from pokerbot.engine.models import HandConfig
from tests.engine.helpers import (
    RaisingAgent,
    RandomLegalAgent,
    RecordingAgent,
    ScriptedAgent,
    stacked_deck,
)


def cfg(
    stacks: tuple[int, ...], button: int = 0, sb: int = 1, bb: int = 2, ante: int = 0
) -> HandConfig:
    return HandConfig(
        hand_id="h1", stacks=stacks, button=button, small_blind=sb, big_blind=bb, ante=ante
    )


def test_split_pot_heads_up() -> None:
    deck = stacked_deck(0, {0: "AsKd", 1: "AhKc"}, "2d3d4c7h9s")
    agents = [RecordingAgent(), RecordingAgent()]
    result = run_hand(cfg((100, 100)), agents, deck)
    assert result.payouts == (0, 0)
    assert result.board == tuple(parse_cards("2d3d4c7h9s"))
    shown = [e for e in result.events if isinstance(e, ShowdownRevealed)]
    assert {e.seat for e in shown} == {0, 1}


def test_three_way_all_in_two_side_pots() -> None:
    # button=2 (short, 20) shoves; seat 0 (SB, 100) re-shoves; seat 1 (BB, 50) calls.
    # Main pot 60 -> seat 2 (set of queens); side pot 60 -> seat 1 (set of sevens);
    # seat 0's uncalled 50 is returned.
    deck = stacked_deck(2, {0: "AsAh", 1: "7s7h", 2: "QsQh"}, "Qd7c2h9s4d")
    agents = [
        ScriptedAgent([Action.raise_to(100)]),
        ScriptedAgent([Action.call()]),
        ScriptedAgent([Action.raise_to(20)]),
    ]
    result = run_hand(cfg((100, 50, 20), button=2), agents, deck)
    assert result.final_stacks == (50, 60, 60)
    assert result.payouts == (-50, 10, 40)
    assert result.illegal_actions == ()
    acted = [e.action for e in result.events if isinstance(e, PlayerActed)]
    assert [a.all_in for a in acted if a.kind is ActionType.RAISE] == [True, True]


def test_walk_to_big_blind() -> None:
    deck = stacked_deck(0, {0: "2c7d", 1: "3c8d", 2: "4c9d"})
    agents = [ScriptedAgent([Action.fold()]), ScriptedAgent([Action.fold()]), RecordingAgent()]
    result = run_hand(cfg((100, 100, 100), button=0), agents, deck)
    assert result.payouts == (0, -1, 1)
    assert result.board == ()
    assert not any(isinstance(e, ShowdownRevealed | StreetDealt) for e in result.events)
    assert agents[2].observations == []  # BB never had to act


def test_heads_up_button_posts_small_blind_and_acts_first() -> None:
    deck = stacked_deck(0, {0: "AsKd", 1: "2c7d"}, "2d3d4c7h9s")
    agents = [ScriptedAgent([Action.fold()]), RecordingAgent()]
    result = run_hand(cfg((100, 100), button=0), agents, deck)
    forced = [e.action for e in result.events if isinstance(e, PlayerActed)][:2]
    assert [(a.seat, a.kind, a.amount) for a in forced] == [
        (0, ForcedBetType.SMALL_BLIND, 1),
        (1, ForcedBetType.BIG_BLIND, 2),
    ]
    first = agents[0].observations[0]
    assert first.legal_actions == (ActionType.FOLD, ActionType.CALL, ActionType.RAISE)
    assert (first.to_call, first.min_raise, first.max_raise) == (1, 4, 100)
    assert result.payouts == (-1, 1)


def test_observation_matches_state_and_hides_nothing_of_own() -> None:
    deck = stacked_deck(2, {0: "AsAh", 1: "KsKh", 2: "QsQh"}, "2d3d4c7h9s")
    agents = [RecordingAgent() for _ in range(3)]
    run_hand(cfg((100, 100, 100), button=2), agents, deck)
    utg = agents[2].observations[0]
    assert utg.seat == 2 and utg.hole_cards == tuple(parse_cards("QsQh"))
    assert utg.street is Street.PREFLOP and utg.pot == 3 and utg.to_call == 2
    bb_option = agents[1].observations[0]
    assert bb_option.legal_actions == (ActionType.CHECK, ActionType.RAISE)
    flop_obs = agents[0].observations[1]
    assert flop_obs.street is Street.FLOP
    assert flop_obs.legal_actions == (ActionType.CHECK, ActionType.BET)
    assert flop_obs.board == tuple(parse_cards("2d3d4c"))


def test_all_agents_see_identical_events_in_order() -> None:
    deck = stacked_deck(1, {0: "AsAh", 1: "KsKh", 2: "QsQh"}, "2d3d4c7h9s")
    agents = [RecordingAgent() for _ in range(3)]
    result = run_hand(cfg((100, 100, 100), button=1), agents, deck)
    assert all(a.events == list(result.events) for a in agents)
    assert isinstance(result.events[0], HandStarted)
    assert isinstance(result.events[-1], HandEnded)
    assert [e.street for e in result.events if isinstance(e, StreetDealt)] == [
        Street.FLOP,
        Street.TURN,
        Street.RIVER,
    ]
    mucked_or_shown = [e for e in result.events if isinstance(e, ShowdownRevealed)]
    assert mucked_or_shown  # at least the winner shows


def test_antes_and_short_stack_all_in_on_ante() -> None:
    deck = stacked_deck(2, {0: "AsAh", 1: "KsKh", 2: "QsQh"}, "2d3d4c7h9s")
    agents = [RecordingAgent() for _ in range(3)]
    result = run_hand(cfg((100, 3, 100), button=2, sb=10, bb=20, ante=5), agents, deck)
    forced = [
        e.action
        for e in result.events
        if isinstance(e, PlayerActed)
        if isinstance(e.action.kind, ForcedBetType)
    ]
    antes = [(a.seat, a.amount, a.all_in) for a in forced if a.kind is ForcedBetType.ANTE]
    assert sorted(antes) == [(0, 5, False), (1, 3, True), (2, 5, False)]
    assert not any(a.kind is ForcedBetType.BIG_BLIND for a in forced)  # BB had 0 left
    assert sum(result.final_stacks) == 203


@pytest.mark.parametrize(
    ("bad", "expected"),
    [
        (Action.check(), ActionType.FOLD),  # check facing the big blind
        (Action.raise_to(3), ActionType.FOLD),  # below min-raise (4)
        (Action.bet(10), ActionType.FOLD),  # bet when only raise is legal
        (Action.raise_to(1_000), ActionType.FOLD),  # above stack
    ],
)
def test_illegal_actions_fall_back(bad: Action, expected: ActionType) -> None:
    deck = stacked_deck(0, {0: "AsKd", 1: "2c7d", 2: "3c8d"})
    agents = [ScriptedAgent([bad]), RecordingAgent(), RecordingAgent()]
    result = run_hand(cfg((100, 100, 100), button=0), agents, deck)
    (record,) = result.illegal_actions
    assert record.seat == 0 and record.applied is expected
    first_decision = [e.action for e in result.events if isinstance(e, PlayerActed)][2]
    assert first_decision.seat == 0 and first_decision.kind is expected


def test_illegal_action_falls_back_to_check_when_free(caplog: pytest.LogCaptureFixture) -> None:
    deck = stacked_deck(0, {0: "AsKd", 1: "2c7d", 2: "3c8d"}, "2d3d4c7h9s")
    agents = [RecordingAgent(), RecordingAgent(), ScriptedAgent([Action.raise_to(3)])]
    result = run_hand(cfg((100, 100, 100), button=0), agents, deck)
    (record,) = result.illegal_actions
    assert (record.seat, record.applied) == (2, ActionType.CHECK)
    assert "illegal action" in caplog.text


def test_agent_exception_is_contained() -> None:
    deck = stacked_deck(0, {0: "AsKd", 1: "2c7d"})
    agents = [RaisingAgent(RuntimeError("boom")), RecordingAgent()]
    result = run_hand(cfg((100, 100), button=0), agents, deck)
    (record,) = result.illegal_actions
    assert "boom" in record.reason and record.applied is ActionType.FOLD


def test_bad_inputs_rejected() -> None:
    with pytest.raises(EngineError, match="agents"):
        run_hand(cfg((100, 100)), [RecordingAgent()], full_deck())
    with pytest.raises(EngineError, match="deck"):
        run_hand(cfg((100, 100)), [RecordingAgent(), RecordingAgent()], full_deck()[:10])
    dup: list[Card] = [*full_deck()[:-1], full_deck()[0]]
    with pytest.raises(EngineError, match="deck"):
        run_hand(cfg((100, 100)), [RecordingAgent(), RecordingAgent()], dup)


def _random_hand(seed: int, illegal_rate: float = 0.05) -> tuple[HandConfig, int]:
    rng = random.Random(seed)
    n = rng.randint(2, 9)
    bb = rng.randint(1, 10)
    config = HandConfig(
        hand_id=f"r{seed}",
        stacks=tuple(rng.randint(1, 400) for _ in range(n)),
        button=rng.randrange(n),
        small_blind=rng.randint(1, bb),
        big_blind=bb,
        ante=rng.choice([0, 0, 1, 2]),
    )
    deck = rng.sample(full_deck(), 52)
    agents = [RandomLegalAgent(random.Random(seed * 31 + i), illegal_rate) for i in range(n)]
    result = run_hand(config, agents, deck)
    assert sum(result.final_stacks) == sum(config.stacks)
    assert sum(result.payouts) == 0
    assert all(s >= 0 for s in result.final_stacks)
    assert all(a.events == list(result.events) for a in agents)
    return config, len(result.events)


def test_chip_conservation_random_hands() -> None:
    for seed in range(500):
        _random_hand(seed)


@settings(max_examples=150, deadline=None)
@given(st.integers(min_value=0, max_value=2**32))
def test_chip_conservation_property(seed: int) -> None:
    _random_hand(seed, illegal_rate=0.1)


@pytest.mark.slow
def test_chip_conservation_10k_hands() -> None:
    for seed in range(10_000):
        _random_hand(10_000 + seed)


class _BrokenObserver(RecordingAgent):
    def observe(self, event: object) -> None:
        raise ValueError("observer bug")


class _WrongReturn(RecordingAgent):
    def choose(self, obs: object) -> Action:
        return "fold"  # type: ignore[return-value]


def test_observe_failures_do_not_break_the_hand(caplog: pytest.LogCaptureFixture) -> None:
    deck = stacked_deck(0, {0: "AsKd", 1: "2c7d"}, "2d3d4c7h9s")
    result = run_hand(cfg((100, 100)), [_BrokenObserver(), RecordingAgent()], deck)
    assert sum(result.payouts) == 0
    assert "failed in observe()" in caplog.text


def test_non_action_return_is_illegal() -> None:
    deck = stacked_deck(0, {0: "AsKd", 1: "2c7d"})
    result = run_hand(cfg((100, 100)), [_WrongReturn(), RecordingAgent()], deck)
    (record,) = result.illegal_actions
    assert "not Action" in record.reason


def test_call_amount_is_street_total_after_calling() -> None:
    # Limped 3-way pot: SB completes to 2, so CALL amount is the street total (2), not 1.
    deck = stacked_deck(0, {0: "AsKd", 1: "2c7d", 2: "3c8d"}, "2d3d4c7h9s")
    result = run_hand(cfg((100, 100, 100), button=0), [RecordingAgent() for _ in range(3)], deck)
    calls = [
        e.action
        for e in result.events
        if isinstance(e, PlayerActed)
        if e.action.kind is ActionType.CALL
    ]
    assert [(a.seat, a.amount) for a in calls] == [(0, 2), (1, 2)]


def test_all_in_call_records_total_and_flag() -> None:
    # HU: button raises to 50; BB (stack 50, 2 posted) calls 48 more -> total 50, all-in.
    deck = stacked_deck(0, {0: "AsKd", 1: "2c7d"}, "2d3d4c7h9s")
    agents = [ScriptedAgent([Action.raise_to(50)]), ScriptedAgent([Action.call()])]
    result = run_hand(cfg((100, 50), button=0), agents, deck)
    call = next(
        e.action
        for e in result.events
        if isinstance(e, PlayerActed)
        if e.action.kind is ActionType.CALL
    )
    assert (call.seat, call.amount, call.all_in) == (1, 50, True)


def test_losing_hand_is_mucked_at_showdown() -> None:
    # Seat 1 shows first and wins; seat 0's losing 72o is mucked (not revealed).
    deck = stacked_deck(0, {0: "7c2d", 1: "AsAh"}, "KdQd9h4s5s")
    result = run_hand(cfg((100, 100), button=0), [RecordingAgent(), RecordingAgent()], deck)
    shown = [e.seat for e in result.events if isinstance(e, ShowdownRevealed)]
    assert shown == [1]
    assert result.payouts == (-2, 2)


def test_short_all_in_raise_does_not_reopen_action() -> None:
    # button (seat 0) raises to 10; SB (seat 1, stack 14) shoves to 14 < full raise (18):
    # BB folds; the button may only fold or call.
    deck = stacked_deck(0, {0: "AsKd", 1: "2c7d", 2: "3c8d"}, "2d3d4c7h9s")
    agents = [
        ScriptedAgent([Action.raise_to(10)]),
        ScriptedAgent([Action.raise_to(14)]),
        ScriptedAgent([Action.fold()]),
    ]
    run_hand(cfg((100, 14, 100), button=0), agents, deck)
    reopened = agents[0].observations[1]
    assert reopened.legal_actions == (ActionType.FOLD, ActionType.CALL)
    assert reopened.to_call == 4

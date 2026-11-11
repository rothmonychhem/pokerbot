"""Story 1.4: information sets and showdown reveal rules."""

from __future__ import annotations

import json
import random
import re
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pokerkit import NoLimitTexasHoldem
from pydantic import BaseModel

from pokerbot.domain import (
    Action,
    ActionType,
    Card,
    Observation,
    PlayerActed,
    PublicEvent,
    ShowdownRevealed,
    Street,
    StreetDealt,
    full_deck,
    parse_cards,
)
from pokerbot.engine.errors import EngineError
from pokerbot.engine.hand_runner import AUTOMATIONS, run_hand
from pokerbot.engine.models import HandConfig, HandResult
from pokerbot.engine.observation import HandView, build_observation
from pokerbot.engine.seating import to_pk
from tests.engine.helpers import RandomLegalAgent, RecordingAgent, ScriptedAgent, stacked_deck

_CARD_RE = re.compile(r"(?<![A-Za-z0-9])[2-9TJQKA][cdhs](?![A-Za-z0-9])")


def cfg(stacks: tuple[int, ...], button: int = 0, ante: int = 0) -> HandConfig:
    return HandConfig(
        hand_id="h1", stacks=stacks, button=button, small_blind=1, big_blind=2, ante=ante
    )


# -- build_observation ---------------------------------------------------------------------
def _fresh_view(config: HandConfig, holes: dict[int, list[Card]]) -> HandView:
    n = config.n_seats
    state = NoLimitTexasHoldem.create_state(
        AUTOMATIONS,
        True,
        config.ante,
        (config.small_blind, config.big_blind),
        config.big_blind,
        list(config.stacks),  # button 0, n=3: pk index i -> seat (i + 1) % 3; equal stacks
        n,
    )
    deck = iter(full_deck())
    while state.can_deal_hole():
        state.deal_hole(to_pk(next(deck)))
    return HandView(state=state, config=config, hole_cards=holes, board=(), history=())


def test_build_observation_for_actor() -> None:
    config = cfg((100, 100, 100), button=0)
    holes = {0: parse_cards("AsAh"), 1: parse_cards("KsKh"), 2: parse_cards("QsQh")}
    view = _fresh_view(config, holes)
    assert view.street is Street.PREFLOP
    obs = build_observation(view, 0)  # 3-handed: the button acts first preflop
    assert obs.seat == 0 and obs.hole_cards == tuple(parse_cards("AsAh"))
    assert obs.legal_actions == (ActionType.FOLD, ActionType.CALL, ActionType.RAISE)
    assert (obs.to_call, obs.min_raise, obs.max_raise, obs.pot) == (2, 4, 100, 3)
    assert obs.stacks == (100, 99, 98)


def test_build_observation_rejects_non_actor() -> None:
    config = cfg((100, 100, 100))
    view = _fresh_view(config, {s: parse_cards(c) for s, c in enumerate(("AsAh", "KsKh", "QsQh"))})
    with pytest.raises(EngineError, match="not the current actor"):
        build_observation(view, 1)


def test_build_observation_requires_two_hole_cards() -> None:
    config = cfg((100, 100, 100))
    view = _fresh_view(config, {0: parse_cards("As"), 1: [], 2: []})
    with pytest.raises(EngineError, match="two hole cards"):
        build_observation(view, 0)


def test_build_observation_rejects_finished_hand() -> None:
    config = cfg((100, 100, 100))
    view = _fresh_view(config, {s: parse_cards(c) for s, c in enumerate(("AsAh", "KsKh", "QsQh"))})
    view.state.fold()
    view.state.fold()  # walk to the BB: no actor left
    with pytest.raises(EngineError, match="not the current actor"):
        build_observation(view, 0)


# -- leak property -------------------------------------------------------------------------
def _card_strings(value: Any) -> set[str]:
    """Every card-looking token anywhere in a JSON-compatible tree (keys and values)."""
    found: set[str] = set()
    if isinstance(value, str):
        found.update(_CARD_RE.findall(value))
    elif isinstance(value, dict):
        for k, v in value.items():
            found |= _card_strings(k) | _card_strings(v)
    elif isinstance(value, list | tuple):
        for item in value:
            found |= _card_strings(item)
    return found


def _reachable_cards(value: Any) -> set[str]:
    """Every card reachable by walking the live object graph (fields, tuples, strings)."""
    if isinstance(value, Card):
        return {str(value)}
    if isinstance(value, str):
        return set(_CARD_RE.findall(value))
    if isinstance(value, BaseModel):
        return set().union(
            set(), *(_reachable_cards(getattr(value, f)) for f in type(value).model_fields)
        )
    if isinstance(value, list | tuple):
        return set().union(set(), *(_reachable_cards(v) for v in value))
    return set()


def _assert_no_leaks(result: HandResult, agents: list[RecordingAgent]) -> None:
    hole = {s: {str(c) for c in cards} for s, cards in enumerate(result.hole_cards)}
    for seat, agent in enumerate(agents):
        foreign = set().union(*(cards for s, cards in hole.items() if s != seat))
        for obs in agent.observations:
            assert obs.seat == seat
            blob = json.loads(obs.model_dump_json())
            assert not _card_strings(blob) & foreign
            assert not _card_strings(obs.model_dump()) & foreign
            assert not _reachable_cards(obs) & foreign
            assert {str(c) for c in obs.hole_cards} == hole[seat]
        for event in _before_showdown(agent.events):
            assert not _card_strings(json.loads(event.model_dump_json())) & foreign
            assert not _card_strings(event.model_dump()) & foreign


def _before_showdown(events: list[PublicEvent]) -> list[PublicEvent]:
    out: list[PublicEvent] = []
    for event in events:
        if isinstance(event, ShowdownRevealed):
            break
        out.append(event)
    return out


def _assert_reveals_valid(result: HandResult) -> None:
    folded = {
        e.action.seat
        for e in result.events
        if isinstance(e, PlayerActed) and e.action.kind is ActionType.FOLD
    }
    reveals = [e for e in result.events if isinstance(e, ShowdownRevealed)]
    seats = [e.seat for e in reveals]
    assert len(seats) == len(set(seats))
    for event in reveals:
        assert event.seat not in folded
        assert event.cards == result.hole_cards[event.seat]
    if len(folded) == len(result.hole_cards) - 1:
        assert not reveals  # uncontested


def _random_hand(seed: int) -> tuple[HandResult, list[RecordingAgent]]:
    rng = random.Random(seed)
    n = rng.randint(2, 9)
    bb = rng.choice([2, 10])
    stacks = tuple(rng.randint(1, 60) * bb // 2 + 1 for _ in range(n))
    config = HandConfig(
        hand_id=f"hand-{seed}",
        stacks=stacks,
        button=rng.randrange(n),
        small_blind=bb // 2,
        big_blind=bb,
        ante=rng.choice([0, 0, 1]),
    )
    agents: list[RecordingAgent] = [
        RandomLegalAgent(random.Random(rng.random()), illegal_rate=0.1) for _ in range(n)
    ]
    deck = full_deck()
    rng.shuffle(deck)
    return run_hand(config, agents, deck), agents


@settings(max_examples=150, deadline=None)
@given(st.integers(min_value=0, max_value=2**32 - 1))
def test_no_opponent_hole_cards_leak_property(seed: int) -> None:
    result, agents = _random_hand(seed)
    _assert_no_leaks(result, agents)
    _assert_reveals_valid(result)


def test_no_leaks_across_seeded_hands() -> None:
    for seed in range(300):
        result, agents = _random_hand(seed)
        _assert_no_leaks(result, agents)
        _assert_reveals_valid(result)


def test_leak_scanner_detects_a_leak() -> None:
    # Guard against a vacuous scanner: a real hole card inside an observation must be found.
    obs = Observation(
        hand_id="h",
        seat=0,
        hole_cards=tuple(parse_cards("AsKd")),  # type: ignore[arg-type]
        board=(),
        street=Street.PREFLOP,
        pot=3,
        stacks=(100, 100),
        to_call=1,
        min_raise=4,
        max_raise=100,
        action_history=(),
        button=0,
        small_blind=1,
        big_blind=2,
        legal_actions=(ActionType.FOLD, ActionType.CALL),
    )
    assert _card_strings(json.loads(obs.model_dump_json())) == {"As", "Kd"}
    assert _card_strings(obs.model_dump()) == {"As", "Kd"}
    assert _reachable_cards(obs) == {"As", "Kd"}
    # Hexadecimal hash metadata is not a card token; real cards remain detectable.
    assert _card_strings({"deck_commitment": "7c" * 32, "card": "As"}) == {"As"}


# -- showdown reveal rules -----------------------------------------------------------------
def _reveals(result: HandResult) -> list[int]:
    return [e.seat for e in result.events if isinstance(e, ShowdownRevealed)]


def test_uncontested_pot_reveals_nothing() -> None:
    deck = stacked_deck(0, {0: "AsAh", 1: "KsKh", 2: "QsQh"}, "2d3d4c7h9s")
    agents = [ScriptedAgent([Action.raise_to(6)]), ScriptedAgent([Action.fold()]),
              ScriptedAgent([Action.fold()])]  # fmt: skip
    result = run_hand(cfg((100, 100, 100)), agents, deck)
    assert _reveals(result) == []


def test_all_in_reveals_every_live_hand_before_runout() -> None:
    # Seat 0 (72o) shoves, seat 1 calls: both shown although 72o cannot be ahead.
    deck = stacked_deck(0, {0: "7c2d", 1: "AsAh"}, "KdQd9h4s5s")
    agents = [ScriptedAgent([Action.raise_to(100)]), ScriptedAgent([Action.call()])]
    result = run_hand(cfg((100, 100)), agents, deck)
    assert sorted(_reveals(result)) == [0, 1]
    kinds = [type(e) for e in result.events]
    assert kinds.index(ShowdownRevealed) < kinds.index(StreetDealt)


def test_river_aggressor_shows_first_and_beaten_caller_mucks() -> None:
    # Seat 1 (BB, acts first postflop heads-up) bets the river with AA; seat 0 calls with 72o.
    deck = stacked_deck(0, {0: "7c2d", 1: "AsAh"}, "KdQd9h4s5s")
    agents = [
        ScriptedAgent([Action.call(), Action.check(), Action.check(), Action.call()]),
        ScriptedAgent([Action.check(), Action.check(), Action.check(), Action.bet(10)]),
    ]
    result = run_hand(cfg((100, 100)), agents, deck)
    assert _reveals(result) == [1]


def test_caller_shows_when_aggressor_is_beaten() -> None:
    # Seat 0 bets the river with 72o (bluff) and shows first; seat 1 can win and shows too.
    deck = stacked_deck(0, {0: "7c2d", 1: "AsAh"}, "KdQd9h4s5s")
    agents = [
        ScriptedAgent([Action.call(), Action.check(), Action.check(), Action.bet(10)]),
        ScriptedAgent([Action.check(), Action.check(), Action.check(), Action.call()]),
    ]
    result = run_hand(cfg((100, 100)), agents, deck)
    assert _reveals(result) == [0, 1]


def test_tie_both_show() -> None:
    deck = stacked_deck(0, {0: "AsKd", 1: "AhKc"}, "2d3d4c7h9s")
    result = run_hand(cfg((100, 100)), [RecordingAgent(), RecordingAgent()], deck)
    assert sorted(_reveals(result)) == [0, 1]
    assert result.payouts == (0, 0)


def test_side_pot_winner_shows_after_losing_main_pot() -> None:
    # Button 0 (QQ), SB seat 1 (AA, stack 10) shoves, BB seat 2 (KK) calls and bets the
    # flop; QQ calls everything. Rivers checked: AA shows first and wins the main pot; KK
    # cannot win the main pot but wins the side pot, so it shows; QQ wins nothing: muck.
    deck = stacked_deck(0, {0: "QsQh", 1: "AsAh", 2: "KsKh"}, "2d3d4c7h9s")
    agents = [
        ScriptedAgent([Action.call(), Action.call(), Action.call()]),
        ScriptedAgent([Action.raise_to(10)]),
        ScriptedAgent([Action.call(), Action.bet(10)]),
    ]
    result = run_hand(cfg((100, 10, 100)), agents, deck)
    assert _reveals(result) == [1, 2]
    assert result.payouts == (-20, 20, 0)


def test_river_shove_and_call_tables_both_hands() -> None:
    # No more betting possible after a river all-in call: both hands shown, even 72o.
    deck = stacked_deck(0, {0: "7c2d", 1: "AsAh"}, "KdQd9h4s5s")
    agents = [
        ScriptedAgent([Action.call(), Action.check(), Action.check(), Action.call()]),
        ScriptedAgent([Action.check(), Action.check(), Action.check(), Action.bet(98)]),
    ]
    result = run_hand(cfg((100, 100)), agents, deck)
    assert _reveals(result) == [1, 0]

import random
from itertools import pairwise
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from pokerbot.domain import Action, ForcedBetType, HandStarted, full_deck
from pokerbot.engine.errors import EngineError
from pokerbot.engine.table import TableConfig, TableSession
from tests.engine.helpers import RandomLegalAgent, RecordingAgent, ScriptedAgent, stacked_deck
from tests.engine.test_observation import _card_strings


def agents(n: int) -> list[RecordingAgent]:
    return [RecordingAgent() for _ in range(n)]


def test_consecutive_hands_rotate_button_and_carry_stacks() -> None:
    players = agents(3)
    table = TableSession(TableConfig(stacks=(100, 100, 100), mode="sim", seed=10), players)
    played = table.play(4)
    assert [h.seats[h.config.button] for h in played] == [0, 1, 2, 0]
    assert [h.config.hand_id for h in played] == [f"table-{i}" for i in range(1, 5)]
    assert len({h.result.deck_audit.commitment for h in played}) == 4
    for before, after in pairwise(played):
        assert before.result.final_stacks == after.config.stacks
    assert table.stacks == played[-1].result.final_stacks
    assert table.rebuy_totals == (0, 0, 0) and sum(table.stacks) == 300
    expected = tuple(event for h in played for event in h.events)
    assert all(tuple(p.events) == expected for p in players)
    assert table.history == played


def test_gapped_physical_seats_heads_up_observation_and_broadcast() -> None:
    players = agents(4)
    table = TableSession(TableConfig(stacks=(0, 100, 50, 100), sitting_out=(2,), button=0), players)
    first = table.play_hand(full_deck())
    second = table.play_hand(full_deck())
    assert first is not None and second is not None
    assert first.seats == (1, 3)
    assert [h.seats[h.config.button] for h in (first, second)] == [1, 3]
    forced = [a for a in first.actions if isinstance(a.kind, ForcedBetType)]
    assert [(a.seat, a.kind) for a in forced] == [
        (1, ForcedBetType.SMALL_BLIND),
        (3, ForcedBetType.BIG_BLIND),
    ]
    obs = players[1].observations[0]
    assert (obs.seat, obs.button) == (1, 1)
    assert obs.stacks == (0, 99, 50, 98)
    assert [a.seat for a in obs.action_history] == [1, 3]
    assert players[0].observations == players[2].observations == []
    assert table.stacks[2] == 50
    assert all(tuple(p.events) == first.events + second.events for p in players)
    for p in players:
        for event in p.events:
            assert "deck_audit" not in event.model_dump() and "hole_cards" not in event.model_dump()


def test_sitting_in_and_out_preserves_balances_and_button_skips() -> None:
    table = TableSession(TableConfig(stacks=(100, 100, 100), sitting_out=(0,)), agents(3))
    first = table.play_hand(full_deck())
    assert first is not None and first.seats[first.config.button] == 1
    assert table.sitting_out == (0,)
    assert table.stacks[0] == 100
    table.sit_in(0)
    table.sit_out(1)
    second = table.play_hand(full_deck())
    assert second is not None and second.seats == (0, 2)
    assert second.seats[second.config.button] == 2
    table.sit_in(1)
    assert table.sitting_out == ()


def test_bust_removal_stops_table_and_manual_rebuy_resumes() -> None:
    players = [ScriptedAgent([Action.raise_to(10)]), ScriptedAgent([Action.call()])]
    table = TableSession(TableConfig(stacks=(10, 10), rebuy_policy="manual"), players)
    result = table.play_hand(stacked_deck(0, {0: "AsAh", 1: "KsKh"}, "2d3d4c7h9s"))
    assert result is not None and table.stacks == (20, 0)
    assert table.play(3) == () and len(table.history) == 1
    table.rebuy(1, 10)
    assert table.rebuy_totals == (0, 10)
    resumed = table.play_hand(full_deck())
    assert resumed is not None and resumed.seats[resumed.config.button] == 1
    assert sum(table.stacks) == 30


def test_auto_rebuy_applies_only_to_busted_participating_seats() -> None:
    table = TableSession(
        TableConfig(stacks=(0, 0, 20), sitting_out=(1,), rebuy_policy="auto", rebuy_to=50),
        agents(3),
    )
    hand = table.play_hand(full_deck())
    assert hand is not None and hand.table_stacks == (50, 0, 20)
    assert table.rebuy_totals == (50, 0, 0)
    assert sum(table.stacks) == 70
    table.rebuy(2, 5)
    assert table.rebuy_totals == (50, 0, 5)


def test_no_hand_or_failed_hand_does_not_commit_rebuys_or_consume_ids() -> None:
    table = TableSession(
        TableConfig(stacks=(0, 20), sitting_out=(1,), rebuy_policy="auto", rebuy_to=50), agents(2)
    )
    assert table.play_hand() is None
    assert table.stacks == (0, 20) and table.rebuy_totals == (0, 0)
    table.sit_in(1)
    with pytest.raises(EngineError):
        table.play_hand([])
    assert table.stacks == (0, 20) and table.rebuy_totals == (0, 0) and table.history == ()
    hand = table.play_hand(full_deck())
    assert hand is not None and hand.config.hand_id == "table-1" and hand.config.button == 0


def test_seeded_sessions_repeat_and_split_play_calls_match() -> None:
    config = TableConfig(stacks=(100, 100, 100), mode="sim", seed=0)
    first, second = TableSession(config, agents(3)), TableSession(config, agents(3))
    together = first.play(3)
    split = second.play(1) + second.play(2)
    assert [h.to_json() for h in together] == [h.to_json() for h in split]
    assert first.play(0) == ()


def test_default_session_uses_secure_shuffle() -> None:
    with patch("pokerbot.engine.rng.secrets.SystemRandom") as secure:
        assert TableSession(TableConfig(stacks=(100, 100)), agents(2)).play_hand() is not None
    secure.return_value.shuffle.assert_called_once()


def test_side_pots_keep_physical_seats_and_inactive_balances() -> None:
    players = [
        ScriptedAgent([Action.raise_to(100)]),
        RecordingAgent(),
        ScriptedAgent([Action.call()]),
        ScriptedAgent([Action.raise_to(20)]),
    ]
    table = TableSession(TableConfig(stacks=(100, 0, 50, 20), button=3), players)
    deck = stacked_deck(2, {0: "AsAh", 1: "7s7h", 2: "QsQh"}, "Qd7c2h9s4d")
    hand = table.play_hand(deck)
    assert hand is not None and hand.seats == (0, 2, 3)
    assert table.stacks == (50, 0, 60, 60)
    assert hand.events[-1].payouts == (-50, 0, 10, 40)
    assert all(tuple(player.events) == hand.events for player in players)
    assert players[1].observations == []


def test_observer_exception_does_not_skip_other_seats(caplog: pytest.LogCaptureFixture) -> None:
    class Broken(RecordingAgent):
        def observe(self, event):
            raise RuntimeError("observer failed")

    players = [Broken(), RecordingAgent(), RecordingAgent()]
    table = TableSession(TableConfig(stacks=(0, 100, 100)), players)
    hand = table.play_hand(full_deck())
    assert hand is not None
    assert tuple(players[1].events) == tuple(players[2].events) == hand.events
    assert "table observer at seat 0 failed" in caplog.text


def test_all_state_changes_and_reentrant_play_are_rejected_during_callbacks() -> None:
    players = agents(2)
    table = TableSession(TableConfig(stacks=(100, 100), rebuy_policy="manual"), players)
    seen = []

    class Reentrant(RecordingAgent):
        def observe(self, event):
            if isinstance(event, HandStarted):
                for mutate in (
                    lambda: table.sit_out(0),
                    lambda: table.sit_in(0),
                    lambda: table.rebuy(0, 1),
                    lambda: table.play_hand(),
                    lambda: table.play(0),
                ):
                    with pytest.raises(EngineError, match="running"):
                        mutate()
                    seen.append(True)

    table = TableSession(
        TableConfig(stacks=(100, 100), rebuy_policy="manual"), [Reentrant(), players[1]]
    )
    assert table.play_hand(full_deck()) is not None
    assert len(seen) == 5 and table.sitting_out == () and table.rebuy_totals == (0, 0)


@pytest.mark.parametrize(
    "kw",
    [
        {"stacks": (100,)},
        {"stacks": (100,) * 10},
        {"stacks": (-1, 100)},
        {"stacks": (True, 100)},
        {"button": 2},
        {"button": True},
        {"small_blind": 3},
        {"big_blind": 0},
        {"ante": -1},
        {"sitting_out": (2,)},
        {"sitting_out": (0, 0)},
        {"sitting_out": (True,)},
        {"rebuy_policy": "auto"},
        {"rebuy_policy": "bad"},
        {"rebuy_to": 0},
        {"rebuy_policy": "none", "rebuy_to": 50},
        {"mode": "sim"},
        {"mode": "sim", "seed": -1},
        {"mode": "sim", "seed": True},
        {"seed": 0},
        {"mode": "other"},
        {"table_id": ""},
    ],
)
def test_invalid_config(kw: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TableConfig.model_validate({"stacks": (100, 100), **kw})


def test_invalid_session_operations() -> None:
    config = TableConfig(stacks=(100, 100))
    with pytest.raises(EngineError, match="agents"):
        TableSession(config, agents(3))
    table = TableSession(config, agents(2))
    for seat in (-1, 2, True):
        with pytest.raises(EngineError, match="seat"):
            table.sit_out(seat)
    with pytest.raises(EngineError, match="disabled"):
        table.rebuy(0, 10)
    for hands in (-1, True, 1.5):
        with pytest.raises(EngineError, match="hands"):
            table.play(hands)
    manual = TableSession(TableConfig(stacks=(100, 100), rebuy_policy="manual"), agents(2))
    for amount in (0, -1, True, 1.5):
        with pytest.raises(EngineError, match="amount"):
            manual.rebuy(0, amount)


def test_random_sessions_keep_chips_information_sets_and_history_round_trips() -> None:
    from pokerbot.engine.history import HandHistory, parse_text_actions

    for seed in range(20):
        rng = random.Random(seed)
        n = rng.randint(2, 9)
        config = TableConfig(
            stacks=tuple(rng.randint(1, 60) for _ in range(n)),
            sitting_out=tuple(rng.sample(range(n), rng.randint(0, n - 2))),
            button=rng.randrange(n),
            ante=1,
            mode="sim",
            seed=seed,
            rebuy_policy="auto",
            rebuy_to=50,
        )
        players = [RandomLegalAgent(random.Random(seed * 10 + s)) for s in range(n)]
        table = TableSession(config, players)
        hands = table.play(3)
        assert len(hands) == 3
        assert sum(table.stacks) == sum(config.stacks) + sum(table.rebuy_totals)
        expected_events = tuple(event for hand in hands for event in hand.events)
        assert all(tuple(player.events) == expected_events for player in players)
        histories = {hand.config.hand_id: hand for hand in hands}
        for hand in hands:
            assert HandHistory.from_json(hand.to_json()) == hand
            assert parse_text_actions(hand.to_text()) == hand.actions
        for seat, player in enumerate(players):
            for obs in player.observations:
                history = histories[obs.hand_id]
                dense = history.seats.index(seat)
                assert obs.hole_cards == history.result.hole_cards[dense]
                foreign = {
                    str(card)
                    for i, hole in enumerate(history.result.hole_cards)
                    if i != dense
                    for card in hole
                }
                assert not _card_strings(obs.model_dump()) & foreign


def test_failure_after_event_delivery_leaves_committed_state_unchanged() -> None:
    players = agents(2)
    table = TableSession(TableConfig(stacks=(0, 100), rebuy_policy="auto", rebuy_to=50), players)
    # Result validation is part of committing the hand, not a partially applied update.
    with (
        patch("pokerbot.engine.table.HandHistory", side_effect=ValueError("history failed")),
        pytest.raises(ValueError, match="history failed"),
    ):
        table.play_hand(full_deck())
    assert players[0].events  # external callback effects cannot be rolled back
    assert table.stacks == (0, 100) and table.rebuy_totals == (0, 0) and table.history == ()
    assert table.play_hand(full_deck()).config.hand_id == "table-1"

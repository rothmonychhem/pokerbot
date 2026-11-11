import pytest
from pydantic import ValidationError

from pokerbot.domain import (
    PUBLIC_EVENT_ADAPTER,
    ActionType,
    HandEnded,
    HandStarted,
    PlayerActed,
    PublicAction,
    PublicEvent,
    ShowdownRevealed,
    Street,
    StreetDealt,
)
from tests.strategies import card_list

EVENTS: list[PublicEvent] = [
    HandStarted(hand_id="h1", button=0, stacks=[1_000, 1_000], small_blind=5, big_blind=10),
    PlayerActed(
        action=PublicAction(seat=1, street=Street.PREFLOP, kind=ActionType.RAISE, amount=30)
    ),
    StreetDealt(street=Street.FLOP, cards=card_list("2c 7h 9s")),
    ShowdownRevealed(seat=1, cards=(card_list("As Kd")[0], card_list("As Kd")[1])),
    HandEnded(hand_id="h1", payouts=(-30, 30)),
]


@pytest.mark.parametrize("event", EVENTS, ids=lambda e: e.kind)
def test_event_round_trip_through_union(event: PublicEvent) -> None:
    raw = PUBLIC_EVENT_ADAPTER.dump_json(event)
    restored = PUBLIC_EVENT_ADAPTER.validate_json(raw)
    assert restored == event
    assert type(restored) is type(event)


def test_unknown_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        PUBLIC_EVENT_ADAPTER.validate_json('{"kind": "secret_hole_cards"}')


def test_street_dealt_card_count_must_match_street() -> None:
    with pytest.raises(ValidationError):
        StreetDealt(street=Street.FLOP, cards=card_list("2c 7h"))
    with pytest.raises(ValidationError):
        StreetDealt(street=Street.PREFLOP, cards=[])
    assert len(StreetDealt(street=Street.TURN, cards=card_list("Qd")).cards) == 1


def test_showdown_cards_distinct() -> None:
    with pytest.raises(ValidationError):
        ShowdownRevealed(seat=0, cards=(card_list("As")[0], card_list("As")[0]))


def test_payouts_round_trip_indexed_by_seat() -> None:
    restored = PUBLIC_EVENT_ADAPTER.validate_json(PUBLIC_EVENT_ADAPTER.dump_json(EVENTS[-1]))
    assert isinstance(restored, HandEnded)
    assert restored.payouts == (-30, 30)


@pytest.mark.parametrize(
    "overrides",
    [{"button": 2}, {"stacks": [-5, 100]}, {"small_blind": 20}, {"stacks": [100]}],
)
def test_hand_started_rejects_inconsistent_table(overrides: dict[str, object]) -> None:
    data: dict[str, object] = {
        "hand_id": "h",
        "button": 0,
        "stacks": [100, 100],
        "small_blind": 5,
        "big_blind": 10,
    }
    data.update(overrides)
    with pytest.raises(ValidationError):
        HandStarted.model_validate(data)


def test_events_are_immutable_and_hashable() -> None:
    started = EVENTS[0]
    assert isinstance(started, HandStarted)
    assert not hasattr(started.stacks, "append")
    assert len({hash(e) for e in EVENTS}) == len(EVENTS)

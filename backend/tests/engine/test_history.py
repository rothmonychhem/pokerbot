import pytest
from pydantic import ValidationError

from pokerbot.domain import (
    Action,
    ActionType,
    HandEnded,
    HandStarted,
    PlayerActed,
    ShowdownRevealed,
    Street,
    StreetDealt,
    parse_cards,
)
from pokerbot.engine.hand_runner import run_hand
from pokerbot.engine.history import HandHistory, map_event, parse_text_actions
from tests.engine.helpers import ScriptedAgent, stacked_deck
from tests.engine.test_hand_runner import cfg


def history() -> HandHistory:
    config = cfg((100, 50, 20), button=2, ante=1)
    deck = stacked_deck(2, {0: "AsAh", 1: "7s7h", 2: "QsQh"}, "Qd7c2h9s4d")
    agents = [
        ScriptedAgent([Action.raise_to(99)]),
        ScriptedAgent([Action.call()]),
        ScriptedAgent([Action.raise_to(19)]),
    ]
    result = run_hand(config, agents, deck)
    return HandHistory(
        config=config, result=result, seats=(0, 2, 4), table_stacks=(100, 0, 50, 123, 20)
    )


def test_history_round_trips_and_maps_physical_seats() -> None:
    record = history()
    assert HandHistory.from_json(record.to_json()) == record
    assert all(action.seat in (0, 2, 4) for action in record.actions)
    start, end = record.events[0], record.events[-1]
    assert isinstance(start, HandStarted) and isinstance(end, HandEnded)
    assert start.button == 4 and start.stacks == record.table_stacks
    assert end.payouts[1] == end.payouts[3] == 0
    assert parse_text_actions(record.to_text()) == record.actions
    assert "*** PRIVATE AUDIT ***" in record.to_text()
    assert record.result.deck_audit is not None


def test_text_round_trips_checks_bets_calls_and_folds() -> None:
    config = cfg((100, 100))
    deck = stacked_deck(0, {0: "AsAh", 1: "KsKh"}, "2d3d4c7h9s")
    agents = [
        ScriptedAgent([Action.call(), Action.raise_to(10), Action.call(), Action.fold()]),
        ScriptedAgent([Action.check(), Action.bet(4), Action.call(), Action.bet(6), Action.bet(8)]),
    ]
    result = run_hand(config, agents, deck)
    record = HandHistory(config=config, result=result, seats=(1, 3), table_stacks=(0, 100, 10, 100))
    assert not result.illegal_actions
    assert parse_text_actions(record.to_text()) == record.actions


@pytest.mark.parametrize(
    "seats,stacks",
    [
        ((0, 0), (100, 100)),
        ((0, 2), (100, 100)),
        ((0,), (100, 100)),
        ((False, 1), (100, 100)),
        ((0, 1), (100, -1)),
        ((0, 1), (100, True)),
    ],
)
def test_mapping_rejects_invalid_boundaries(
    seats: tuple[int, ...], stacks: tuple[int, ...]
) -> None:
    with pytest.raises(ValueError):
        map_event(HandEnded(hand_id="h", payouts=(0, 0)), seats, stacks)


def test_mapping_rejects_bad_event_indices_and_vectors() -> None:
    for event in (
        HandStarted(hand_id="h", stacks=(1, 2, 3), button=0, small_blind=1, big_blind=2),
        HandEnded(hand_id="h", payouts=(0, 0, 0)),
        PlayerActed(action=history().actions[-1].model_copy(update={"seat": 2})),
        ShowdownRevealed(seat=2, cards=tuple(parse_cards("AsKd"))),
    ):
        with pytest.raises(ValueError):
            map_event(event, (0, 1), (100, 100))
    dealt = StreetDealt(street=Street.FLOP, cards=tuple(parse_cards("2c3d4h")))
    assert map_event(dealt, (0, 1), (100, 100)) is dealt


def test_history_rejects_inconsistent_config_result_or_mapping() -> None:
    record = history()
    for update in (
        {"seats": (0, 2)},
        {"table_stacks": (99, 0, 50, 123, 20)},
        {"config": record.config.model_copy(update={"hand_id": "wrong"})},
        {"config": record.config.model_copy(update={"button": 1})},
    ):
        with pytest.raises(ValidationError):
            record.model_copy(update=update)


def test_generated_parser_rejects_unknown_or_incomplete_text() -> None:
    text = history().to_text()
    for invalid in (
        "",
        "unrelated",
        text.replace("calls", "teleports"),
        text.replace("*** SUMMARY ***", ""),
        text + "\nPlayer0: folds",
    ):
        with pytest.raises(ValueError):
            parse_text_actions(invalid)


def test_legacy_auditless_history_exports_and_validates_event_boundaries() -> None:
    record = history()
    result = record.result.model_copy(update={"deck_audit": None})
    legacy = record.model_copy(update={"result": result})
    assert "Deck audit: unavailable" in legacy.to_text()
    assert parse_text_actions(legacy.to_text()) == legacy.actions
    for events in (
        (),
        result.events[1:],
        result.events[:-1],
        (*result.events[:-1], HandEnded(hand_id="wrong", payouts=result.payouts)),
    ):
        with pytest.raises(ValidationError):
            legacy.model_copy(update={"result": result.model_copy(update={"events": events})})


@pytest.mark.parametrize(
    "before,after",
    [
        ("5-max Seat #4", "5-max Seat #8"),
        ("Table 'PokerBot'", "Table 'Other'"),
        ("Seat 0: Player0", "Seat 0: Player1"),
        ("*** HOLE CARDS ***", "*** DRAW ***"),
        ("Player0: net", "Player8: net"),
        ("Player0: net", "Player1: net"),
        ("*** FLOP ***", "*** TURN ***"),
        ("Player0: raises", "Player8: raises"),
        ("Player0: raises", "Winner0: raises"),
        ("raises 80 to 99", "raises 3 to 99"),
    ],
)
def test_generated_parser_rejects_malformed_structure(before: str, after: str) -> None:
    text = history().to_text()
    assert before in text
    with pytest.raises(ValueError):
        parse_text_actions(text.replace(before, after, 1))


def test_parser_rejects_truncated_headers_invalid_all_in_and_missing_audit() -> None:
    text = history().to_text()
    with pytest.raises(ValueError, match="truncated"):
        parse_text_actions("\n".join(text.splitlines()[:7]))
    with pytest.raises(ValueError, match="all-in"):
        parse_text_actions(
            text.replace("Player0: raises 80 to 99 and is all-in", "Player0: checks and is all-in")
        )
    with pytest.raises(ValueError, match="incomplete"):
        parse_text_actions(text[: text.index("Deck commitment:")])


def test_history_rejects_call_without_a_street_total() -> None:
    record = history()
    events = list(record.result.events)
    call_index = next(
        i
        for i, event in enumerate(events)
        if isinstance(event, PlayerActed) and event.action.kind is ActionType.CALL
    )
    call = events[call_index]
    assert isinstance(call, PlayerActed)
    events[call_index] = call.model_copy(
        update={"action": call.action.model_copy(update={"amount": None})}
    )
    result = record.result.model_copy(update={"events": tuple(events)})
    with pytest.raises(ValueError, match="street-total"):
        record.model_copy(update={"result": result})

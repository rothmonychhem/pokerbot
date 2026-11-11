from typing import Any

import pytest
from hypothesis import given
from pydantic import ValidationError

from pokerbot.domain import CARD_PATTERN, ActionType, Card, Observation, PublicAction, Street
from tests.strategies import card_list, observations


def _base(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "hand_id": "h1",
        "seat": 1,
        "hole_cards": card_list("As Kd"),
        "board": card_list("2c 7h 9s"),
        "street": Street.FLOP,
        "pot": 300,
        "stacks": [9_900, 9_800, 10_000],
        "to_call": 0,
        "min_raise": 100,
        "max_raise": 9_800,
        "action_history": [],
        "button": 0,
        "small_blind": 50,
        "big_blind": 100,
        "legal_actions": [ActionType.CHECK, ActionType.BET],
    }
    data.update(overrides)
    return data


def test_valid_observation() -> None:
    obs = Observation(**_base())
    assert obs.hole_cards == (Card.parse("As"), Card.parse("Kd"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"seat": 3},
        {"seat": -1},
        {"button": 5},
        {"stacks": [100]},
        {"stacks": [100] * 10, "seat": 0},
        {"hole_cards": card_list("As As")},
        {"board": card_list("2c 7h")},
        {"street": Street.TURN},
        {"board": card_list("As 7h 9s")},
        {"pot": -1},
        {"to_call": -1},
        {"stacks": [100, -1, 100]},
        {"min_raise": 0},
        {"min_raise": 500, "max_raise": 400},
        {"legal_actions": []},
        {"legal_actions": [ActionType.CHECK, ActionType.CHECK]},
        {"big_blind": 0},
        {"small_blind": 200},
        {"to_call": 100},
        {"legal_actions": [ActionType.CHECK, ActionType.CALL]},
        {"legal_actions": [ActionType.BET, ActionType.RAISE]},
        {"legal_actions": [ActionType.FOLD, ActionType.CALL]},
        {"action_history": [PublicAction(seat=8, street=Street.FLOP, kind=ActionType.CHECK)]},
        {"action_history": [PublicAction(seat=0, street=Street.RIVER, kind=ActionType.CHECK)]},
    ],
)
def test_invalid_observations_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Observation(**_base(**overrides))


def test_raise_bounds_ignored_when_raise_not_legal() -> None:
    obs = Observation(
        **_base(
            legal_actions=[ActionType.FOLD, ActionType.CALL], to_call=100, min_raise=0, max_raise=0
        )
    )
    assert obs.min_raise == 0


def test_hole_cards_serialize_as_strings() -> None:
    assert '"hole_cards":["As","Kd"]' in Observation(**_base()).model_dump_json()


@given(observations())
def test_observation_json_round_trip(obs: Observation) -> None:
    assert Observation.model_validate_json(obs.model_dump_json()) == obs


def test_observation_is_immutable_and_hashable() -> None:
    obs = Observation(**_base())
    assert isinstance(obs.board, tuple)
    assert isinstance(obs.legal_actions, tuple)
    hash(obs)


def test_model_copy_cannot_create_invalid_observation() -> None:
    obs = Observation(**_base())
    with pytest.raises(ValidationError):
        obs.model_copy(update={"seat": 99})
    assert obs.model_copy(update={"pot": 900}).pot == 900


def test_card_json_schema_is_string_in_both_modes() -> None:
    for mode in ("validation", "serialization"):
        schema = Card.model_json_schema(mode=mode)
        assert schema["type"] == "string"
        assert schema["pattern"] == CARD_PATTERN
    obs_schema = Observation.model_json_schema()
    assert "Card" not in obs_schema.get("$defs", {}) or (
        obs_schema["$defs"]["Card"]["type"] == "string"
    )

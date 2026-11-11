from typing import Any

import pytest
from pydantic import ValidationError

from pokerbot.domain import Card
from pokerbot.engine.models import HandConfig, HandResult


def _cfg(**kw: Any) -> HandConfig:
    data: dict[str, Any] = {
        "hand_id": "h",
        "stacks": (100, 100),
        "button": 0,
        "small_blind": 1,
        "big_blind": 2,
    }
    data.update(kw)
    return HandConfig(**data)


def test_valid_config() -> None:
    assert _cfg().n_seats == 2


@pytest.mark.parametrize(
    "kw",
    [
        {"stacks": (100,)},
        {"stacks": (100,) * 10},
        {"button": 2},
        {"stacks": (100, 0)},
        {"small_blind": 3},
        {"big_blind": 0},
        {"ante": -1},
        {"stacks": (100.0, 100)},
        {"stacks": (True, 100)},
        {"stacks": ("100", 100)},
        {"big_blind": 2.0},
    ],
)
def test_invalid_configs(kw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _cfg(**kw)


def _result(**kw: Any) -> HandResult:
    cards = (Card.parse("As"), Card.parse("Kd"))
    data: dict[str, Any] = {
        "hand_id": "h",
        "starting_stacks": (100, 100),
        "final_stacks": (90, 110),
        "payouts": (-10, 10),
        "board": (),
        "hole_cards": (cards, cards),
        "events": (),
    }
    data.update(kw)
    return HandResult(**data)


def test_hand_result_invariants() -> None:
    assert _result().payouts == (-10, 10)
    with pytest.raises(ValidationError, match="per-seat"):
        _result(payouts=(-10, 10, 0))
    with pytest.raises(ValidationError, match="final minus starting"):
        _result(payouts=(-5, 10))
    with pytest.raises(ValidationError, match="not conserved"):
        _result(final_stacks=(90, 120), payouts=(-10, 20))

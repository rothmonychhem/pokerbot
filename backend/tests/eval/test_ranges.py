import math

import pytest
from pydantic import ValidationError

from pokerbot.domain import parse_cards
from pokerbot.eval.ranges import WeightedCombo, parse_range


def test_weighted_combo_is_validated_canonical_and_frozen() -> None:
    combo = WeightedCombo(cards=tuple(parse_cards("AsKd")), weight=2)
    assert combo.cards == tuple(parse_cards("KdAs"))
    assert combo.weight == 2.0
    assert WeightedCombo.model_validate_json(combo.model_dump_json()) == combo
    assert WeightedCombo(cards=tuple(parse_cards("KdAs"))) == combo.model_copy(update={"weight": 1})
    with pytest.raises(ValidationError):
        combo.weight = 3
    assert WeightedCombo(cards=tuple(parse_cards("AsKd")), weight=0).weight == 0


@pytest.mark.parametrize("weight", [-1, math.inf, -math.inf, math.nan, True, "1"])
def test_combo_rejects_invalid_weights(weight: object) -> None:
    with pytest.raises(ValidationError):
        WeightedCombo(cards=tuple(parse_cards("AsKd")), weight=weight)


@pytest.mark.parametrize("cards", ["AsAs", "As", "AsKdQh"])
def test_combo_rejects_invalid_cards(cards: str) -> None:
    with pytest.raises(ValidationError):
        WeightedCombo(cards=tuple(parse_cards(cards)))


@pytest.mark.parametrize(
    "notation,count",
    [
        ("AKs", 4),
        ("KQo", 12),
        ("AK", 16),
        ("TT", 6),
        ("TT+", 30),
        ("AA+", 6),
        ("ATs+", 16),
        ("KQo+", 12),
        ("A5s-A2s", 16),
        ("A2s-A5s", 16),
        ("TT-QQ", 18),
        ("QQ-TT", 18),
        ("A5-A2", 64),
        ("AsKd", 1),
    ],
)
def test_range_expansion_counts(notation: str, count: int) -> None:
    combos = parse_range(notation)
    assert len(combos) == count
    assert len({combo.cards for combo in combos}) == count
    assert all(combo.weight == 1 for combo in combos)


def test_range_suit_constraints_and_overlap() -> None:
    assert all(a.suit == b.suit for combo in parse_range("AKs") for a, b in [combo.cards])
    assert all(a.suit != b.suit for combo in parse_range("KQo") for a, b in [combo.cards])
    expected = parse_range("AK, TT+, A5s-A2s")
    assert parse_range(" AKs, AKo, TT+, AA, A2s-A5s, AsKs ") == expected
    assert parse_range("AsKd,KdAs") == parse_range("KdAs")


@pytest.mark.parametrize(
    "notation",
    [
        "",
        " ",
        ",",
        "AKs,",
        ",AKs",
        "AKs,,TT",
        "aks",
        "KA",
        "KAs",
        "AAs",
        "TTo",
        "AKx",
        "A1s",
        "A5s-K2s",
        "A5s-A2o",
        "AA-AK",
        "AK-AA",
        "AA-KK-QQ",
        "AKs+foo",
        "AsAs",
        "AsKd+",
        "AsKd-QhJd",
        "AK s",
        "A",
    ],
)
def test_invalid_range_notation(notation: str) -> None:
    with pytest.raises(ValueError):
        parse_range(notation)

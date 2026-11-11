from unittest.mock import patch

import numpy as np
import pytest

from pokerbot.domain import parse_cards
from pokerbot.eval.equity import _equity_kernel, equity_vs_hand, equity_vs_range
from pokerbot.eval.ranges import WeightedCombo, parse_range


def cards(text: str):
    return parse_cards(text)


def test_aa_vs_kk_50k_accuracy_and_repeatability() -> None:
    # Average KK's six suit combinations; fixed suits have different flush blockers.
    result = equity_vs_range(cards("AsAh"), parse_range("KK"), samples=50_000, seed=42)
    assert result == pytest.approx(0.819, abs=0.005)
    assert equity_vs_range(cards("AsAh"), parse_range("KK"), samples=50_000, seed=42) == result
    fixed = equity_vs_hand(cards("AsAh"), cards("KcKh"), samples=50_000, seed=42)
    assert fixed == pytest.approx(0.819, abs=0.005)


@pytest.mark.parametrize("board", ["2c3d4h", "2c3d4h5s", "2c3d4h5s9d"])
def test_partial_boards_compiled_and_python_agree(board: str) -> None:
    kwargs = dict(board=cards(board), samples=100, seed=123)
    compiled = equity_vs_hand(cards("AsAh"), cards("KsKh"), **kwargs)
    with patch("pokerbot.eval.equity._equity_kernel", _equity_kernel.py_func):
        interpreted = equity_vs_hand(cards("AsAh"), cards("KsKh"), **kwargs)
    assert compiled == interpreted


def test_river_win_loss_and_board_tie() -> None:
    for board, expected in [("2c3d4h8s9d", 1.0), ("Kc3d4h8s9d", 0.0), ("TcJcQcKcAc", 0.5)]:
        for kernel in (_equity_kernel, _equity_kernel.py_func):
            with patch("pokerbot.eval.equity._equity_kernel", kernel):
                assert (
                    equity_vs_hand(cards("AsAh"), cards("KsKh"), cards(board), samples=20)
                    == expected
                )


def test_weighted_range_and_blocker_removal() -> None:
    board = cards("2c3d4h8s9d")
    combos = [
        WeightedCombo(cards=cards("KsKh"), weight=3),
        WeightedCombo(cards=cards("9c9h"), weight=1),
        WeightedCombo(cards=cards("AsKd"), weight=1e10),
        WeightedCombo(cards=cards("2cKd"), weight=1e10),
        WeightedCombo(cards=cards("8d8c"), weight=0),
    ]
    for kernel in (_equity_kernel, _equity_kernel.py_func):
        with patch("pokerbot.eval.equity._equity_kernel", kernel):
            result = equity_vs_range(cards("AsAh"), combos, board, samples=10_000, seed=9)
        assert result == pytest.approx(0.75, abs=0.015)


def test_range_scales_huge_finite_weights_and_combines_reversed_duplicates() -> None:
    hero, board = cards("AsAh"), cards("2c3d4h8s9d")
    combos = [
        WeightedCombo(cards=cards("KsKh"), weight=1e308),
        WeightedCombo(cards=cards("KhKs"), weight=1e308),
        WeightedCombo(cards=cards("9c9h"), weight=1e308),
    ]
    result = equity_vs_range(hero, combos, board, samples=10_000)
    assert result == pytest.approx(2 / 3, abs=0.015)


@pytest.mark.parametrize(
    "hero,villain,board",
    [
        ("As", "KsKh", ""),
        ("AsAs", "KsKh", ""),
        ("AsAh", "Ks", ""),
        ("AsAh", "KsKh", "2c"),
        ("AsAh", "KsKh", "2c2c4h"),
        ("AsAh", "KsKh", "As2c3d"),
        ("AsAh", "AsKh", ""),
    ],
)
def test_invalid_card_inputs(hero: str, villain: str, board: str) -> None:
    with pytest.raises(ValueError):
        equity_vs_hand(cards(hero), cards(villain), cards(board), samples=1)


@pytest.mark.parametrize(
    "key,value",
    [
        ("samples", 0),
        ("samples", -1),
        ("samples", True),
        ("samples", 1.5),
        ("seed", -1),
        ("seed", True),
        ("seed", 1.5),
        ("seed", None),
    ],
)
def test_invalid_sampling_inputs(key: str, value: object) -> None:
    with pytest.raises(ValueError):
        equity_vs_hand(cards("AsAh"), cards("KsKh"), **{key: value})


def test_empty_zero_weight_and_fully_blocked_ranges_rejected() -> None:
    for combos in ((), [WeightedCombo(cards=cards("KsKh"), weight=0)], parse_range("AsKd")):
        with pytest.raises(ValueError, match="unblocked"):
            equity_vs_range(cards("AsAh"), combos, samples=1)


def test_seeded_equity_does_not_touch_global_numpy_rng() -> None:
    np.random.seed(123)
    expected = np.random.random(3)
    np.random.seed(123)
    equity_vs_hand(cards("AsAh"), cards("KsKh"), samples=10, seed=3)
    assert np.array_equal(np.random.random(3), expected)

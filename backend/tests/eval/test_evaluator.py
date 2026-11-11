import random

import numpy as np
import pytest
from phevaluator.evaluator import evaluate_cards

from pokerbot.domain import Card, Suit, full_deck, parse_cards
from pokerbot.eval.evaluator import _rank_batch, rank_hand, rank_hands


@pytest.mark.parametrize("count", [5, 6, 7])
def test_all_hand_categories_and_best_five(count: int) -> None:
    fixtures = [
        "AsKsQsJsTs",
        "AsAhAdAcKs",
        "AsAhAdKsKh",
        "AsJs9s5s2s",
        "9c8s7h6d5c",
        "AsAhAdKsQh",
        "AsAhKsKhQd",
        "AsAhKsQhJd",
        "AsKd9h7c3s",
    ]
    ranks = []
    for text in fixtures:
        cards = parse_cards(text) + parse_cards("2d4h")[: count - 5]
        result = rank_hand(cards)
        assert result == evaluate_cards(*(str(c) for c in cards))
        ranks.append(result)
    assert ranks == sorted(ranks) and len(set(ranks)) == 9
    assert rank_hand(parse_cards("AsKsQsJsTs")) == 1


def test_wheel_and_kickers() -> None:
    assert rank_hand(parse_cards("As2d3h4c5s")) > rank_hand(parse_cards("2s3d4h5c6s"))
    assert rank_hand(parse_cards("AsAhKsQdJc")) < rank_hand(parse_cards("AsAhKsQdTc"))


def test_batch_matches_library_for_random_hands_and_interpreted_kernel() -> None:
    rng = random.Random(42)
    for n in (5, 6, 7):
        hands = [rng.sample(full_deck(), n) for _ in range(100)]
        expected = [evaluate_cards(*(str(c) for c in hand)) for hand in hands]
        assert rank_hands(hands).tolist() == expected
        ids = np.array([[(c.rank - 2) * 4 + "cdhs".index(c.suit) for c in h] for h in hands])
        assert _rank_batch.py_func(ids).tolist() == expected


@pytest.mark.parametrize("text", ["AsKd", "AsKdQhJc", "AsKdQhJcTs9d8s7c", "AsAsQhJcTs"])
def test_invalid_hands_rejected_before_native_evaluation(text: str) -> None:
    with pytest.raises(ValueError):
        rank_hand(parse_cards(text))


def test_batch_validation() -> None:
    assert rank_hands([]).tolist() == []
    with pytest.raises(ValueError, match="same"):
        rank_hands([parse_cards("AsKdQhJcTs"), parse_cards("AsKdQhJcTs9d")])
    with pytest.raises(ValueError, match="distinct"):
        rank_hands([parse_cards("AsAsQhJcTs")])


@pytest.mark.parametrize("rank", [-1, 15, 10**100])
def test_unvalidated_card_cannot_send_out_of_range_ids_to_native_code(rank: int) -> None:
    # model_construct bypasses domain validation; the native boundary must remain safe.
    malformed = Card.model_construct(rank=rank, suit=Suit.CLUBS)
    hand = [malformed, *parse_cards("KdQhJcTs")]
    with pytest.raises(ValueError, match="invalid card ID"):
        rank_hand(hand)
    with pytest.raises(ValueError, match="invalid card ID"):
        rank_hands([hand])

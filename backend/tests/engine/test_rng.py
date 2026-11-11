import hashlib
from unittest.mock import patch

import pytest
from numpy.random import PCG64, Generator

from pokerbot.domain import full_deck
from pokerbot.engine.rng import deck_commitment, shuffled_deck


def test_seeded_shuffle_uses_pcg64_and_is_repeatable() -> None:
    expected = full_deck()
    Generator(PCG64(42)).shuffle(expected)
    assert shuffled_deck(mode="sim", seed=42) == tuple(expected)
    assert shuffled_deck(mode="sim", seed=42) == shuffled_deck(mode="sim", seed=42)
    assert shuffled_deck(mode="sim", seed=0) != tuple(expected)


def test_play_shuffle_uses_system_random() -> None:
    with patch("pokerbot.engine.rng.secrets.SystemRandom") as secure:
        secure.return_value.shuffle.side_effect = lambda cards: cards.reverse()
        assert shuffled_deck() == tuple(reversed(full_deck()))
        secure.return_value.shuffle.assert_called_once()


@pytest.mark.parametrize("mode,seed", [("play", None), ("sim", 0), ("sim", 2**128)])
def test_shuffled_deck_is_a_complete_permutation(mode: str, seed: int | None) -> None:
    deck = shuffled_deck(mode=mode, seed=seed)  # type: ignore[arg-type]
    assert len(deck) == 52 and set(deck) == set(full_deck())


@pytest.mark.parametrize(
    "mode,seed", [("other", None), ("play", 0), ("sim", None), ("sim", -1),
                  ("sim", True), ("sim", 1.5), ("sim", "1")],
)
def test_invalid_rng_inputs(mode: str, seed: object) -> None:
    with pytest.raises(ValueError):
        shuffled_deck(mode=mode, seed=seed)  # type: ignore[arg-type]


def test_commitment_is_canonical_sha256_and_order_sensitive() -> None:
    deck = full_deck()
    expected = hashlib.sha256("".join(str(c) for c in deck).encode("ascii")).hexdigest()
    assert deck_commitment(deck) == expected
    assert deck_commitment(deck[::-1]) != expected
    assert deck_commitment(deck[:-1]) != expected

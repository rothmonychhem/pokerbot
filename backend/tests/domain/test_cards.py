import pytest
from hypothesis import given
from pydantic import BaseModel, ValidationError

from pokerbot.domain import Card, Rank, Suit, full_deck, parse_cards
from tests.strategies import cards


def test_parse_and_str() -> None:
    card = Card.parse("As")
    assert card.rank is Rank.ACE
    assert card.suit is Suit.SPADES
    assert str(card) == "As"


@pytest.mark.parametrize("text", ["", "A", "Ax", "1s", "AsK", "as", "10h"])
def test_invalid_card_strings_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        Card.parse(text)


def test_lowercase_rank_letters_rejected_but_t_works() -> None:
    assert Card.parse("Td").rank is Rank.TEN
    with pytest.raises(ValueError):
        Card.parse("td")


def test_cards_are_hashable_ordered_and_frozen() -> None:
    a, k = Card.parse("As"), Card.parse("Kd")
    assert len({a, Card.parse("As")}) == 1
    assert k < a
    with pytest.raises(ValidationError):
        a.rank = Rank.TWO  # type: ignore[misc]


def test_full_deck() -> None:
    deck = full_deck()
    assert len(deck) == 52
    assert len(set(deck)) == 52
    assert str(deck[0]) == "2c"
    assert str(deck[-1]) == "As"


def test_parse_cards_formats() -> None:
    assert [str(c) for c in parse_cards("AsKd Th")] == ["As", "Kd", "Th"]
    assert parse_cards("") == []
    with pytest.raises(ValueError):
        parse_cards("AsK")


class _Holder(BaseModel):
    cards: list[Card]
    pair: tuple[Card, Card]


def test_nested_cards_serialize_as_strings() -> None:
    holder = _Holder(cards=parse_cards("2c 3d"), pair=(Card.parse("Ah"), Card.parse("Kh")))
    assert holder.model_dump_json() == '{"cards":["2c","3d"],"pair":["Ah","Kh"]}'
    assert _Holder.model_validate_json(holder.model_dump_json()) == holder


def test_card_accepts_dict_form() -> None:
    assert Card.model_validate({"rank": 14, "suit": "s"}) == Card.parse("As")


@given(cards)
def test_card_json_round_trip(card: Card) -> None:
    assert Card.model_validate_json(card.model_dump_json()) == card
    assert Card.parse(str(card)) == card


@pytest.mark.parametrize("raw", ["A", "Ahh", "Zs", "Ax"])
def test_model_validate_rejects_bad_strings(raw: str) -> None:
    with pytest.raises(ValidationError):
        Card.model_validate(raw)


def test_repr_and_foreign_comparison() -> None:
    card = Card.parse("Qh")
    assert repr(card) == "Card('Qh')"
    with pytest.raises(TypeError):
        _ = card < "Qh"  # type: ignore[operator]

import pytest
from pokerkit import Card as PkCard

from pokerbot.domain import Card, full_deck
from pokerbot.engine.seating import from_pk, pk_index_of, seat_of, to_pk


@pytest.mark.parametrize("n", range(2, 10))
@pytest.mark.parametrize("button", [0, 1])
def test_seat_mapping_round_trips(n: int, button: int) -> None:
    seats = [seat_of(i, button, n) for i in range(n)]
    assert sorted(seats) == list(range(n))
    assert seats[-1] == button  # last PokerKit index is the button
    assert all(pk_index_of(seat_of(i, button, n), button, n) == i for i in range(n))


def test_card_conversion_round_trips() -> None:
    for card in full_deck():
        pk = next(iter(PkCard.parse(to_pk(card))))
        assert from_pk(pk) == card
    assert to_pk(Card.parse("Td")) == "Td"

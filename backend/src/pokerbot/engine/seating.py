"""Mapping between table seats and PokerKit player indices, and card conversion.

PokerKit orders players starting with the first seat after the button; the last index is
the button. Heads-up, PokerKit itself makes the button post the small blind.
"""

from pokerkit import Card as PkCard

from pokerbot.domain import Card


def seat_of(pk_index: int, button: int, n_seats: int) -> int:
    return (button + 1 + pk_index) % n_seats


def pk_index_of(seat: int, button: int, n_seats: int) -> int:
    return (seat - button - 1) % n_seats


def to_pk(card: Card) -> str:
    return str(card)


def from_pk(card: PkCard) -> Card:
    return Card.parse(f"{card.rank.value}{card.suit.value}")

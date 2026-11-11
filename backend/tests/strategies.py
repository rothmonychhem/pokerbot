"""Reusable hypothesis strategies for domain models."""

from hypothesis import strategies as st

from pokerbot.domain import (
    ActionType,
    Card,
    ForcedBetType,
    Observation,
    PublicAction,
    Street,
    full_deck,
)

DECK = full_deck()

cards = st.sampled_from(DECK)


@st.composite
def public_actions(draw: st.DrawFn, n_players: int, max_street: Street) -> PublicAction:
    street = draw(st.sampled_from([s for s in Street if s.order <= max_street.order]))
    kinds: list[ActionType | ForcedBetType] = list(ActionType)
    if street is Street.PREFLOP:
        kinds += list(ForcedBetType)
    kind = draw(st.sampled_from(kinds))
    if kind in (ActionType.FOLD, ActionType.CHECK):
        amount = None
    elif kind is ActionType.CALL:
        amount = draw(st.none() | st.integers(1, 5_000))
    else:
        amount = draw(st.integers(1, 5_000))
    return PublicAction(
        seat=draw(st.integers(0, n_players - 1)),
        street=street,
        kind=kind,
        amount=amount,
        all_in=draw(st.booleans()),
    )


@st.composite
def observations(draw: st.DrawFn) -> Observation:
    """Engine-plausible observations (legal actions consistent with to_call)."""
    n_players = draw(st.integers(min_value=2, max_value=9))
    street = draw(st.sampled_from(list(Street)))
    dealt = draw(st.permutations(DECK))[: 2 + street.board_size]
    stacks = draw(st.lists(st.integers(0, 100_000), min_size=n_players, max_size=n_players))
    big_blind = draw(st.integers(1, 1_000))
    small_blind = draw(st.integers(0, big_blind))
    to_call = draw(st.sampled_from([0]) | st.integers(1, 10_000))
    can_size = draw(st.booleans())
    if to_call == 0:
        legal = [ActionType.CHECK] + ([ActionType.BET] if can_size else [])
    else:
        legal = [ActionType.FOLD, ActionType.CALL] + ([ActionType.RAISE] if can_size else [])
    min_raise = draw(st.integers(1, 1_000)) if can_size else 0
    max_raise = draw(st.integers(min_raise, 200_000)) if can_size else 0
    history = draw(st.lists(public_actions(n_players, street), max_size=6))
    return Observation(
        hand_id=draw(st.uuids()).hex,
        seat=draw(st.integers(0, n_players - 1)),
        hole_cards=(dealt[0], dealt[1]),
        board=tuple(dealt[2:]),
        street=street,
        pot=draw(st.integers(0, 1_000_000)),
        stacks=tuple(stacks),
        to_call=to_call,
        min_raise=min_raise,
        max_raise=max_raise,
        action_history=tuple(history),
        button=draw(st.integers(0, n_players - 1)),
        small_blind=small_blind,
        big_blind=big_blind,
        legal_actions=tuple(draw(st.permutations(legal))),
    )


def card_list(text: str) -> list[Card]:
    return [Card.parse(t) for t in text.split()]

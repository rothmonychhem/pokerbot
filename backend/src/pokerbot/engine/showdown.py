"""Showdown reveal rules.

A live hand is revealed if and only if:

* the showdown is an all-in situation: at most one live player still has chips, so no
  more betting was possible. Every live hand is tabled (before the remaining board is
  dealt when the all-in happened before the river); or
* it can still win or tie at least one pot it is eligible for, given the hands already
  shown. Players act in PokerKit's showdown order: the last aggressor first, otherwise
  the first live seat after the button.

Every other hand is mucked. Folded hands never reach the showdown, and an uncontested pot
has no showdown at all.

PokerKit's own default (``show_or_muck_hole_cards(None)``) differs: at a river showdown it
tables every hand whenever *any* player is all-in, even players who keep betting between
themselves and lose every pot. The engine therefore decides explicitly.
"""

from __future__ import annotations

from pokerkit import State


def is_all_in_situation(state: State) -> bool:
    """True if no more betting was possible. Evaluate once, before the first show/muck:
    mucking clears PokerKit statuses and would change the answer mid-showdown."""
    with_chips = sum(1 for i in state.player_indices if state.statuses[i] and state.stacks[i] > 0)
    return with_chips <= 1


def should_show(state: State, pk_index: int, *, all_in_situation: bool) -> bool:
    """Whether the player at PokerKit index ``pk_index`` shows (True) or mucks (False)."""
    return all_in_situation or state.can_win_now(pk_index)

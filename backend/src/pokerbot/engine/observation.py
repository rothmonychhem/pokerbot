"""Build a seat's information set from the hand state.

``build_observation`` is the only place an agent's view is assembled. It reads the hole
cards of the requested seat and nothing else private, so no opponent card can reach an
``Observation``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pokerkit import State

from pokerbot.domain import ActionType, Card, Observation, PublicAction, Street
from pokerbot.engine.errors import EngineError
from pokerbot.engine.models import HandConfig
from pokerbot.engine.seating import pk_index_of, seat_of

_STREET_BY_BOARD_SIZE = {0: Street.PREFLOP, 3: Street.FLOP, 4: Street.TURN, 5: Street.RIVER}


@dataclass(frozen=True, slots=True)
class HandView:
    """Read-only snapshot of a hand in progress (engine-side; never handed to agents)."""

    state: State
    config: HandConfig
    hole_cards: Mapping[int, Sequence[Card]]
    """Dealt hole cards by seat. Private: only ``build_observation`` reads one entry."""
    board: Sequence[Card]
    history: Sequence[PublicAction]

    @property
    def street(self) -> Street:
        return _STREET_BY_BOARD_SIZE[len(self.board)]


def legal_actions(state: State) -> tuple[list[ActionType], int, int, int]:
    """Return (legal actions, to_call, min_raise_to, max_raise_to) for the current actor."""
    to_call = state.checking_or_calling_amount or 0
    legal: list[ActionType] = []
    if to_call > 0 and state.can_fold():
        legal.append(ActionType.FOLD)
    if state.can_check_or_call():
        legal.append(ActionType.CHECK if to_call == 0 else ActionType.CALL)
    min_raise = max_raise = 0
    if state.can_complete_bet_or_raise_to():
        facing_bet = any(bet > 0 for bet in state.bets)
        legal.append(ActionType.RAISE if facing_bet else ActionType.BET)
        min_raise = state.min_completion_betting_or_raising_to_amount or 0
        max_raise = state.max_completion_betting_or_raising_to_amount or 0
    return legal, to_call, min_raise, max_raise


def build_observation(view: HandView, seat: int) -> Observation:
    """The information set of ``seat``, which must be the current actor."""
    config, state = view.config, view.state
    n = config.n_seats
    actor = state.actor_index
    if actor is None or seat_of(actor, config.button, n) != seat:
        raise EngineError(f"seat {seat} is not the current actor")
    own = view.hole_cards.get(seat, ())
    if len(own) != 2:
        raise EngineError(f"seat {seat} has not been dealt two hole cards")
    legal, to_call, min_raise, max_raise = legal_actions(state)
    return Observation(
        hand_id=config.hand_id,
        seat=seat,
        hole_cards=(own[0], own[1]),
        board=tuple(view.board),
        street=view.street,
        pot=state.total_pot_amount,
        stacks=tuple(state.stacks[pk_index_of(s, config.button, n)] for s in range(n)),
        to_call=to_call,
        min_raise=min_raise,
        max_raise=max_raise,
        action_history=tuple(view.history),
        button=config.button,
        small_blind=config.small_blind,
        big_blind=config.big_blind,
        legal_actions=tuple(legal),
    )

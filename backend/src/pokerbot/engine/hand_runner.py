"""Run one No-Limit Hold'em hand through PokerKit, driving agents and emitting events."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from pokerkit import Automation, Mode, NoLimitTexasHoldem, State

from pokerbot.agents.base import Agent
from pokerbot.domain import (
    Action,
    ActionType,
    Card,
    ForcedBetType,
    HandEnded,
    HandStarted,
    Observation,
    PlayerActed,
    PublicAction,
    PublicEvent,
    ShowdownRevealed,
    Street,
    StreetDealt,
)
from pokerbot.engine.errors import EngineError
from pokerbot.engine.models import DeckAudit, HandConfig, HandResult, IllegalActionRecord
from pokerbot.engine.observation import HandView, build_observation
from pokerbot.engine.rng import ShuffleMode, deck_commitment, shuffled_deck
from pokerbot.engine.seating import pk_index_of, seat_of, to_pk
from pokerbot.engine.showdown import is_all_in_situation, should_show

__all__ = ["AUTOMATIONS", "EngineError", "run_hand"]

logger = logging.getLogger(__name__)

# Dealing, burning, runout selection and show/muck stay manual: cards come from our deck
# and reveals must be observable.
AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)
_STREET_BY_BOARD_SIZE = {0: Street.PREFLOP, 3: Street.FLOP, 4: Street.TURN, 5: Street.RIVER}


class _HandDriver:
    def __init__(
        self,
        config: HandConfig,
        agents: Sequence[Agent],
        deck: Sequence[Card],
        on_event: Callable[[PublicEvent], None] | None = None,
    ) -> None:
        n = config.n_seats
        if len(agents) != n:
            raise EngineError(f"expected {n} agents, got {len(agents)}")
        if len(set(deck)) != len(deck) or len(deck) < 2 * n + 8:
            raise EngineError(f"deck must hold at least {2 * n + 8} unique cards")
        self.config = config
        self.agents = agents
        self.on_event = on_event
        self.deck = list(deck)
        self.deck_audit = DeckAudit(deck=tuple(self.deck), commitment=deck_commitment(self.deck))
        self.n = n
        self.events: list[PublicEvent] = []
        self.history: list[PublicAction] = []
        self.illegal: list[IllegalActionRecord] = []
        self.board: list[Card] = []
        self.all_in_showdown: bool | None = None  # fixed at the first show/muck
        self.holes: dict[int, list[Card]] = {seat: [] for seat in range(n)}
        self.state: State = NoLimitTexasHoldem.create_state(
            AUTOMATIONS,
            True,
            config.ante,
            (config.small_blind, config.big_blind),
            config.big_blind,
            [config.stacks[self.seat(i)] for i in range(n)],
            n,
            mode=Mode.CASH_GAME,
        )

    # -- helpers -------------------------------------------------------------------------
    def seat(self, pk_index: int) -> int:
        return seat_of(pk_index, self.config.button, self.n)

    def pk(self, seat: int) -> int:
        return pk_index_of(seat, self.config.button, self.n)

    def stack(self, seat: int) -> int:
        return int(self.state.stacks[self.pk(seat)])

    @property
    def street(self) -> Street:
        return _STREET_BY_BOARD_SIZE[len(self.board)]

    def draw(self) -> Card:
        return self.deck.pop(0)

    def emit(self, event: PublicEvent) -> None:
        self.events.append(event)
        if isinstance(event, PlayerActed):
            self.history.append(event.action)
        for seat, agent in enumerate(self.agents):
            try:
                agent.observe(event)
            except Exception:
                logger.exception("agent at seat %d failed in observe()", seat)
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception:
                logger.exception("public-event callback failed")

    # -- phases --------------------------------------------------------------------------
    def post_forced_bets(self) -> None:
        cfg = self.config
        if cfg.ante:
            for i in range(self.n):
                seat = self.seat(i)
                posted = min(cfg.ante, cfg.stacks[seat])
                self.emit(
                    PlayerActed(
                        action=PublicAction(
                            seat=seat,
                            street=Street.PREFLOP,
                            kind=ForcedBetType.ANTE,
                            amount=posted,
                            all_in=posted == cfg.stacks[seat],
                        )
                    )
                )
        sb_index, bb_index = (1, 0) if self.n == 2 else (0, 1)
        for pk_index, kind in (
            (sb_index, ForcedBetType.SMALL_BLIND),
            (bb_index, ForcedBetType.BIG_BLIND),
        ):
            amount = int(self.state.bets[pk_index])
            if amount > 0:
                self.emit(
                    PlayerActed(
                        action=PublicAction(
                            seat=self.seat(pk_index),
                            street=Street.PREFLOP,
                            kind=kind,
                            amount=amount,
                            all_in=self.state.stacks[pk_index] == 0,
                        )
                    )
                )

    def deal_hole_cards(self) -> None:
        while self.state.can_deal_hole():
            dealee = self.state.hole_dealee_index
            if dealee is None:  # pragma: no cover - defensive
                raise EngineError("PokerKit has no hole dealee")
            card = self.draw()
            self.state.deal_hole(to_pk(card))
            self.holes[self.seat(dealee)].append(card)

    def deal_board(self) -> None:
        count = 3 if not self.board else 1
        cards = [self.draw() for _ in range(count)]
        self.state.deal_board("".join(to_pk(c) for c in cards))
        self.board.extend(cards)
        self.emit(StreetDealt(street=self.street, cards=tuple(cards)))

    def show_or_muck(self) -> None:
        pk_index = self.state.showdown_index
        if pk_index is None:  # pragma: no cover - defensive
            raise EngineError("PokerKit has no showdown player")
        if self.all_in_showdown is None:
            self.all_in_showdown = is_all_in_situation(self.state)
        show = should_show(self.state, pk_index, all_in_situation=self.all_in_showdown)
        operation = self.state.show_or_muck_hole_cards(show)
        if operation.hole_cards:
            seat = self.seat(operation.player_index)
            self.emit(ShowdownRevealed(seat=seat, cards=(self.holes[seat][0], self.holes[seat][1])))

    def act(self, pk_index: int) -> None:
        seat = self.seat(pk_index)
        view = HandView(
            state=self.state,
            config=self.config,
            hole_cards=self.holes,
            board=self.board,
            history=self.history,
        )
        obs = build_observation(view, seat)
        attempted: str
        try:
            action = self.agents[seat].decide(obs)
            attempted = repr(action)
            reason = _illegal_reason(action, obs)
        except Exception as exc:
            logger.exception("agent at seat %d raised in decide()", seat)
            action, attempted, reason = Action.fold(), "<exception>", f"agent raised {exc!r}"
        if reason is not None:
            fallback = Action.check() if ActionType.CHECK in obs.legal_actions else Action.fold()
            logger.warning(
                "illegal action from seat %d (%s): %s; applying %s",
                seat,
                attempted,
                reason,
                fallback.type,
            )
            self.illegal.append(
                IllegalActionRecord(
                    seat=seat,
                    street=obs.street,
                    attempted=attempted,
                    reason=reason,
                    applied=fallback.type,
                )
            )
            action = fallback
        self.apply(seat, pk_index, action, obs)

    def apply(self, seat: int, pk_index: int, action: Action, obs: Observation) -> None:
        amount: int | None = None
        if action.type is ActionType.FOLD:
            self.state.fold()
        elif action.type in (ActionType.CHECK, ActionType.CALL):
            if action.type is ActionType.CALL:
                # Street total after calling (PokerKit caps the call at the stack). Read
                # before acting: closing the street triggers bet collection, zeroing bets.
                amount = int(self.state.bets[pk_index]) + obs.to_call
            self.state.check_or_call()
        else:
            amount = action.amount
            self.state.complete_bet_or_raise_to(amount)
        self.emit(
            PlayerActed(
                action=PublicAction(
                    seat=seat,
                    street=obs.street,
                    kind=action.type,
                    amount=amount,
                    all_in=action.type is not ActionType.FOLD and self.state.stacks[pk_index] == 0,
                )
            )
        )

    def run(self) -> HandResult:
        cfg = self.config
        self.emit(
            HandStarted(
                hand_id=cfg.hand_id,
                button=cfg.button,
                stacks=cfg.stacks,
                small_blind=cfg.small_blind,
                big_blind=cfg.big_blind,
                ante=cfg.ante,
                deck_commitment=self.deck_audit.commitment,
            )
        )
        self.post_forced_bets()
        self.deal_hole_cards()
        state = self.state
        while state.status:
            if state.actor_index is not None:
                self.act(state.actor_index)
            elif state.can_select_runout_count():
                state.select_runout_count()
            elif state.can_burn_card():
                state.burn_card(to_pk(self.draw()))
            elif state.can_deal_board():
                self.deal_board()
            elif state.can_show_or_muck_hole_cards():
                self.show_or_muck()
            else:  # pragma: no cover - defensive
                raise EngineError("PokerKit state is stuck with no pending operation")
        final = tuple(self.stack(seat) for seat in range(self.n))
        payouts = tuple(f - s for f, s in zip(final, cfg.stacks, strict=True))
        self.emit(HandEnded(hand_id=cfg.hand_id, payouts=payouts))
        return HandResult(
            hand_id=cfg.hand_id,
            starting_stacks=cfg.stacks,
            final_stacks=final,
            payouts=payouts,
            board=tuple(self.board),
            hole_cards=tuple((h[0], h[1]) for h in (self.holes[s] for s in range(self.n))),
            events=tuple(self.events),
            illegal_actions=tuple(self.illegal),
            deck_audit=self.deck_audit,
        )


def _illegal_reason(action: object, obs: Observation) -> str | None:
    if not isinstance(action, Action):
        return f"decide() returned {type(action).__name__}, not Action"
    if action.type not in obs.legal_actions:
        legal = ", ".join(a.value for a in obs.legal_actions)
        return f"{action.type.value} is not legal (legal: {legal})"
    if action.type in (ActionType.BET, ActionType.RAISE):
        assert action.amount is not None  # guaranteed by Action validation
        if not obs.min_raise <= action.amount <= obs.max_raise:
            return f"amount {action.amount} outside [{obs.min_raise}, {obs.max_raise}]"
    return None


def run_hand(
    config: HandConfig,
    agents: Sequence[Agent],
    deck: Sequence[Card] | None = None,
    *,
    mode: ShuffleMode = "play",
    seed: int | None = None,
    on_event: Callable[[PublicEvent], None] | None = None,
) -> HandResult:
    """Play one hand, securely shuffled by default; sim requires an explicit seed.

    An explicit deck is copied and consumed in order: holes, then burn/board cards.
    Its audit reveal is returned only in private completed-hand history.
    """
    if deck is None:
        deck = shuffled_deck(mode=mode, seed=seed)
    elif mode != "play" or seed is not None:
        raise EngineError("an explicit deck cannot be combined with shuffle mode or seed")
    return _HandDriver(config, agents, deck, on_event).run()

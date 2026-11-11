"""Private hand histories and the deliberately limited PokerBot text format.

The generated PokerStars-style subset uses numeric Player<physical-seat> labels,
integer chips, street markers, call deltas and raise-to totals. It is not a general
PokerStars importer. JSON and text histories contain private deck audit material;
only mapped public events may be broadcast to agents.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Self

from pydantic import Field, model_validator

from pokerbot.domain import (
    ActionType,
    DomainModel,
    ForcedBetType,
    HandEnded,
    HandStarted,
    PlayerActed,
    PublicAction,
    PublicEvent,
    ShowdownRevealed,
    Street,
    StreetDealt,
    parse_cards,
)
from pokerbot.engine.models import DeckAudit, HandConfig, HandResult

_StrictInt = Annotated[int, Field(strict=True)]
_FORCED = {
    ForcedBetType.ANTE: "the ante",
    ForcedBetType.SMALL_BLIND: "small blind",
    ForcedBetType.BIG_BLIND: "big blind",
}
_FORMAT = "# PokerBot generated subset v1; PRIVATE HISTORY"


def _validate_mapping(seats: tuple[int, ...], stacks: tuple[int, ...]) -> None:
    if not 2 <= len(seats) <= len(stacks) <= 9:
        raise ValueError("mapping requires 2-9 table seats and at least two participants")
    if any(type(s) is not int or s < 0 for s in stacks):
        raise ValueError("table stacks must be nonnegative integers")
    if len(set(seats)) != len(seats) or any(
        type(s) is not int or not 0 <= s < len(stacks) for s in seats
    ):
        raise ValueError("seat mapping must contain unique physical seat indices")


def map_event(
    event: PublicEvent, seats: tuple[int, ...], table_stacks: tuple[int, ...]
) -> PublicEvent:
    """Map dense engine seats and vectors into stable physical table seats."""
    _validate_mapping(seats, table_stacks)
    if isinstance(event, HandStarted):
        if len(event.stacks) != len(seats):
            raise ValueError("start stacks do not match seat mapping")
        stacks = list(table_stacks)
        for seat, stack in zip(seats, event.stacks, strict=True):
            stacks[seat] = stack
        return event.model_copy(update={"button": seats[event.button], "stacks": tuple(stacks)})
    if isinstance(event, HandEnded):
        if len(event.payouts) != len(seats):
            raise ValueError("payouts do not match seat mapping")
        payouts = [0] * len(table_stacks)
        for seat, payout in zip(seats, event.payouts, strict=True):
            payouts[seat] = payout
        return event.model_copy(update={"payouts": tuple(payouts)})
    if isinstance(event, PlayerActed):
        if event.action.seat >= len(seats):
            raise ValueError("action seat is outside mapping")
        return event.model_copy(
            update={"action": event.action.model_copy(update={"seat": seats[event.action.seat]})}
        )
    if isinstance(event, ShowdownRevealed):
        if event.seat >= len(seats):
            raise ValueError("showdown seat is outside mapping")
        return event.model_copy(update={"seat": seats[event.seat]})
    return event


class HandHistory(DomainModel):
    """Immutable private record: dense engine data plus physical seat context."""

    config: HandConfig
    result: HandResult
    seats: tuple[_StrictInt, ...]
    table_stacks: tuple[_StrictInt, ...]

    @model_validator(mode="after")
    def _check(self) -> HandHistory:
        _validate_mapping(self.seats, self.table_stacks)
        config, result = self.config, self.result
        if len(self.seats) != config.n_seats or config.stacks != tuple(
            self.table_stacks[s] for s in self.seats
        ):
            raise ValueError("config stacks do not match mapped table stacks")
        if result.hand_id != config.hand_id or result.starting_stacks != config.stacks:
            raise ValueError("result does not match hand config")
        if not result.events or not isinstance(result.events[0], HandStarted):
            raise ValueError("history must begin with HandStarted")
        started = result.events[0]
        if (
            started.hand_id,
            started.button,
            started.stacks,
            started.small_blind,
            started.big_blind,
            started.ante,
        ) != (
            config.hand_id,
            config.button,
            config.stacks,
            config.small_blind,
            config.big_blind,
            config.ante,
        ):
            raise ValueError("HandStarted does not match hand config")
        if not isinstance(result.events[-1], HandEnded) or (
            result.events[-1].hand_id != config.hand_id
            or result.events[-1].payouts != result.payouts
        ):
            raise ValueError("history must end with matching HandEnded")
        # Validate every dense event index/vector before exporting any physical history.
        for event in result.events:
            if isinstance(event, PlayerActed) and (
                event.action.kind is ActionType.CALL and event.action.amount is None
            ):
                raise ValueError("history calls require a street-total amount")
            map_event(event, self.seats, self.table_stacks)
        return self

    @property
    def events(self) -> tuple[PublicEvent, ...]:
        return tuple(
            map_event(event, self.seats, self.table_stacks) for event in self.result.events
        )

    @property
    def actions(self) -> tuple[PublicAction, ...]:
        return tuple(event.action for event in self.events if isinstance(event, PlayerActed))

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, text: str) -> Self:
        return cls.model_validate_json(text)

    def to_text(self) -> str:
        """Export the PokerBot v1 PokerStars-style subset, including a private audit."""
        config = self.config
        lines = [
            f"PokerStars Hand #{json.dumps(config.hand_id)}: Hold'em No Limit "
            f"({config.small_blind}/{config.big_blind})",
            _FORMAT,
            f"Table 'PokerBot' {len(self.table_stacks)}-max "
            f"Seat #{self.seats[config.button]} is the button",
        ]
        lines.extend(
            f"Seat {s}: Player{s} ({stack} in chips)" for s, stack in enumerate(self.table_stacks)
        )
        lines.append("*** HOLE CARDS ***")
        bets: dict[int, int] = {}
        for event in self.events:
            if isinstance(event, StreetDealt):
                lines.append(
                    f"*** {event.street.name} *** [" + " ".join(str(c) for c in event.cards) + "]"
                )
                bets.clear()
            elif isinstance(event, PlayerActed):
                action = event.action
                amount = action.amount or 0
                previous = bets.get(action.seat, 0)
                if isinstance(action.kind, ForcedBetType):
                    verb = f"posts {_FORCED[action.kind]} {amount}"
                    if action.kind is not ForcedBetType.ANTE:
                        bets[action.seat] = amount
                elif action.kind is ActionType.RAISE:
                    verb = f"raises {amount - max(bets.values(), default=0)} to {amount}"
                    bets[action.seat] = amount
                elif action.kind in (ActionType.CALL, ActionType.BET):
                    verb = f"{action.kind.value}s {amount - previous}"
                    bets[action.seat] = amount
                else:
                    verb = f"{action.kind.value}s"
                suffix = " and is all-in" if action.all_in else ""
                lines.append(f"Player{action.seat}: {verb}{suffix}")
            elif isinstance(event, ShowdownRevealed):
                lines.append(
                    f"Player{event.seat}: shows [" + " ".join(str(c) for c in event.cards) + "]"
                )
        lines.append("*** SUMMARY ***")
        ended = next(e for e in reversed(self.events) if isinstance(e, HandEnded))
        lines.extend(f"Player{s}: net {payout:+d}" for s, payout in enumerate(ended.payouts))
        lines.append("*** PRIVATE AUDIT ***")
        audit = self.result.deck_audit
        if audit is None:
            lines.append("Deck audit: unavailable")
        else:
            lines.append(f"Deck commitment: {audit.commitment}")
            lines.append("Deck: " + " ".join(str(card) for card in audit.deck))
        return "\n".join(lines) + "\n"


def parse_text_actions(text: str) -> tuple[PublicAction, ...]:
    """Parse only the generated v1 subset; reconstruct call street totals from deltas."""
    lines = text.splitlines()
    if (
        len(lines) < 7
        or lines[1] != _FORMAT
        or not re.fullmatch(
            r'PokerStars Hand #".*": Hold\x27em No Limit \([1-9][0-9]*/[1-9][0-9]*\)', lines[0]
        )
    ):
        raise ValueError("not a PokerBot v1 generated hand history")
    table = re.fullmatch(r"Table 'PokerBot' ([2-9])-max Seat #([0-8]) is the button", lines[2])
    if table is None or int(table[2]) >= int(table[1]):
        raise ValueError("invalid table header")
    n = int(table[1])
    if len(lines) < 4 + n:
        raise ValueError("truncated seat headers")
    for seat in range(n):
        if not re.fullmatch(rf"Seat {seat}: Player{seat} \([0-9]+ in chips\)", lines[3 + seat]):
            raise ValueError("invalid seat header")
    if lines[3 + n] != "*** HOLE CARDS ***":
        raise ValueError("missing hole-cards marker")
    street = Street.PREFLOP
    bets: dict[int, int] = {}
    actions: list[PublicAction] = []
    summary = False
    audit = False
    net: set[int] = set()
    commitment: str | None = None
    deck_seen = False
    for line in lines[4 + n :]:
        if line == "*** SUMMARY ***" and not summary:
            summary = True
        elif line == "*** PRIVATE AUDIT ***" and summary and not audit and len(net) == n:
            audit = True
        elif audit:
            if line == "Deck audit: unavailable" and not deck_seen and commitment is None:
                deck_seen = True
            elif (
                re.fullmatch(r"Deck commitment: [0-9a-f]{64}", line)
                and commitment is None
                and not deck_seen
            ):
                commitment = line.removeprefix("Deck commitment: ")
            elif line.startswith("Deck: ") and commitment is not None and not deck_seen:
                DeckAudit(deck=tuple(parse_cards(line[6:])), commitment=commitment)
                deck_seen = True
            else:
                raise ValueError("invalid private audit")
        elif summary:
            match = re.fullmatch(r"Player([0-8]): net ([+-][0-9]+)", line)
            if match is None or int(match[1]) >= n or int(match[1]) in net:
                raise ValueError("invalid summary")
            net.add(int(match[1]))
        elif match := re.fullmatch(r"\*\*\* (FLOP|TURN|RIVER) \*\*\* \[(.+)\]", line):
            next_street = Street(match[1].lower())
            if next_street.order != street.order + 1:
                raise ValueError("invalid street order")
            StreetDealt(street=next_street, cards=tuple(parse_cards(match[2])))
            street = next_street
            bets.clear()
        else:
            match = re.fullmatch(r"Player([0-8]): (.+)", line)
            if match is None or int(match[1]) >= n:
                raise ValueError("invalid action line")
            seat, verb = int(match[1]), match[2]
            if shown := re.fullmatch(r"shows \[(.+)\]", verb):
                ShowdownRevealed(seat=seat, cards=tuple(parse_cards(shown[1])))
                continue
            all_in = verb.endswith(" and is all-in")
            verb = verb.removesuffix(" and is all-in")
            action = _parse_action(verb, seat, street, bets, all_in)
            actions.append(action)
    if not summary or not audit or not deck_seen:
        raise ValueError("incomplete generated history")
    return tuple(actions)


def _parse_action(
    verb: str, seat: int, street: Street, bets: dict[int, int], all_in: bool
) -> PublicAction:
    kind: ActionType | ForcedBetType
    amount: int | None = None
    for forced, label in _FORCED.items():
        if match := re.fullmatch(rf"posts {label} ([0-9]+)", verb):
            kind, amount = forced, int(match[1])
            if forced is not ForcedBetType.ANTE:
                bets[seat] = amount
            break
    else:
        if verb in ("folds", "checks"):
            kind = ActionType(verb[:-1])
            if all_in:
                raise ValueError("fold/check cannot be all-in")
        elif match := re.fullmatch(r"(calls|bets) ([0-9]+)", verb):
            kind = ActionType(match[1][:-1])
            amount = bets.get(seat, 0) + int(match[2])
            bets[seat] = amount
        elif match := re.fullmatch(r"raises ([1-9][0-9]*) to ([1-9][0-9]*)", verb):
            kind, amount = ActionType.RAISE, int(match[2])
            if amount - max(bets.values(), default=0) != int(match[1]):
                raise ValueError("raise increment does not match raise-to total")
            bets[seat] = amount
        else:
            raise ValueError("unsupported action syntax")
    return PublicAction(seat=seat, street=street, kind=kind, amount=amount, all_in=all_in)

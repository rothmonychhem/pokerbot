"""Continuous local human-vs-bot play, replayed privately up to each human turn."""

from __future__ import annotations

import secrets
from collections import OrderedDict
from threading import Lock
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field, model_validator

from pokerbot.agents import CallingStationAgent, RaiseAgent, RandomAgent
from pokerbot.agents.base import Agent
from pokerbot.domain import (
    Action,
    ActionType,
    DomainModel,
    ForcedBetType,
    Observation,
    PublicEvent,
    ShowdownRevealed,
)
from pokerbot.engine.hand_runner import run_hand
from pokerbot.engine.history import map_event
from pokerbot.engine.models import HandConfig
from pokerbot.engine.rng import shuffled_deck

BotProfile = Literal["easy", "random", "aggressive"]


class PlaySettings(DomainModel):
    players: int = Field(default=3, ge=2, le=9, strict=True)
    starting_stack: int = Field(default=100, ge=20, le=100_000, strict=True)
    big_blind: int = Field(default=2, ge=2, le=1_000, strict=True)
    bots: tuple[BotProfile, ...] | None = None

    @model_validator(mode="after")
    def check_settings(self) -> PlaySettings:
        if self.big_blind > self.starting_stack:
            raise ValueError("big_blind must not exceed starting_stack")
        if self.bots is not None and len(self.bots) != self.players - 1:
            raise ValueError("one profile is required per bot")
        return self


class _HumanTurn(BaseException):
    def __init__(self, observation: Observation) -> None:
        self.observation = observation


class _Human:
    def __init__(self, actions: list[Action]) -> None:
        self.actions = iter(actions)

    def decide(self, obs: Observation) -> Action:
        action = next(self.actions, None)
        if action is None:
            raise _HumanTurn(obs)
        return action

    def observe(self, event: PublicEvent) -> None:
        pass


class _Game:
    def __init__(self, settings: PlaySettings) -> None:
        self.settings = settings
        self.profiles: tuple[BotProfile, ...] = settings.bots or tuple(
            "easy" if seat % 2 else "random" for seat in range(1, settings.players)
        )
        self.stacks = [settings.starting_stack] * settings.players
        self.hand_number = 0
        self.button = -1
        self.observation: Observation | None = None
        self.view: dict[str, Any] = {}
        self.new_hand()

    def new_hand(self) -> None:
        if self.view and not self.view["finished"]:
            raise HTTPException(409, "hand_in_progress")
        seats = tuple(seat for seat, stack in enumerate(self.stacks) if stack > 0)
        if self.stacks[0] == 0 or len(seats) < 2:
            raise HTTPException(409, "session_over")
        self.seats = seats
        self.button = next(
            (self.button + offset) % len(self.stacks)
            for offset in range(1, len(self.stacks) + 1)
            if (self.button + offset) % len(self.stacks) in seats
        )
        self.hand_number += 1
        self.hand_stacks = tuple(self.stacks)
        self.deck = shuffled_deck()
        self.seed = secrets.randbits(64)
        self.actions: list[Action] = []
        self.advance()

    def players(self) -> list[Agent]:
        players: list[Agent] = []
        for seat in self.seats:
            if seat == 0:
                players.append(_Human(self.actions))
            elif self.profiles[seat - 1] == "easy":
                players.append(CallingStationAgent())
            elif self.profiles[seat - 1] == "aggressive":
                players.append(RaiseAgent())
            else:
                players.append(RandomAgent(self.seed + seat))
        return players

    def advance(self) -> None:
        events: list[PublicEvent] = []
        config = HandConfig(
            hand_id=f"sandbox-{self.hand_number}",
            stacks=tuple(self.hand_stacks[s] for s in self.seats),
            button=self.seats.index(self.button),
            small_blind=self.settings.big_blind // 2,
            big_blind=self.settings.big_blind,
        )
        try:
            result = run_hand(config, self.players(), self.deck, on_event=events.append)
        except _HumanTurn as pause:
            self.observation = pause.observation
            obs = self.observation
            stacks = list(self.hand_stacks)
            for dense, physical in enumerate(self.seats):
                stacks[physical] = obs.stacks[dense]
            own = max(
                (
                    a.amount or 0
                    for a in obs.action_history
                    if a.seat == obs.seat
                    and a.street == obs.street
                    and a.kind is not ForcedBetType.ANTE
                ),
                default=0,
            )
            presets = {}
            if any(a in obs.legal_actions for a in (ActionType.BET, ActionType.RAISE)):
                for name, fraction in (
                    ("third", 1 / 3),
                    ("half", 0.5),
                    ("two_thirds", 2 / 3),
                    ("pot", 1),
                    ("one_half", 1.5),
                ):
                    target = own + obs.to_call + round((obs.pot + obs.to_call) * fraction)
                    presets[name] = min(obs.max_raise, max(obs.min_raise, target))
            self.view = {
                "finished": False,
                "session_over": False,
                "hole_cards": [str(c) for c in obs.hole_cards],
                "board": [str(c) for c in obs.board],
                "stacks": stacks,
                "pot": obs.pot,
                "street": obs.street.value,
                "to_call": obs.to_call,
                "min_raise": obs.min_raise,
                "max_raise": obs.max_raise,
                "legal_actions": [a.value for a in obs.legal_actions],
                "raise_presets": presets,
            }
        else:
            self.observation = None
            for dense, physical in enumerate(self.seats):
                self.stacks[physical] = result.final_stacks[dense]
            payouts = [0] * len(self.stacks)
            for dense, physical in enumerate(self.seats):
                payouts[physical] = result.payouts[dense]
            reveals = [e for e in events if isinstance(e, ShowdownRevealed)]
            split = False
            if len(result.board) == 5 and any(e.seat == 0 for e in reveals):
                from pokerbot.eval import rank_hand

                ranks = {e.seat: rank_hand((*e.cards, *result.board)) for e in reveals}
                best = min(ranks.values())
                split = ranks[0] == best and list(ranks.values()).count(best) > 1
            self.view = {
                "finished": True,
                "session_over": self.stacks[0] == 0 or sum(s > 0 for s in self.stacks) < 2,
                "hole_cards": [str(c) for c in result.hole_cards[0]],
                "board": [str(c) for c in result.board],
                "stacks": list(self.stacks),
                "pot": 0,
                "street": "showdown",
                "legal_actions": [],
                "payouts": payouts,
                "split_pot": split,
            }
        self.view.update(
            {
                "events": [
                    map_event(e, self.seats, self.hand_stacks).model_dump(mode="json")
                    for e in events
                ],
                "hand_number": self.hand_number,
                "button": self.button,
                "players": self.settings.players,
                "bot_profiles": list(self.profiles),
                "big_blind": self.settings.big_blind,
                "small_blind": self.settings.big_blind // 2,
                "starting_stack": self.settings.starting_stack,
                "active_seats": list(self.seats),
            }
        )

    def act(self, action: Action) -> None:
        obs = self.observation
        if obs is None:
            raise HTTPException(409, "hand_finished")
        if action.type not in obs.legal_actions:
            raise HTTPException(422, "illegal_action")
        if action.type in (ActionType.BET, ActionType.RAISE):
            if action.amount is None or not obs.min_raise <= action.amount <= obs.max_raise:
                raise HTTPException(422, "invalid_amount")
        elif action.amount is not None:
            raise HTTPException(422, "unexpected_amount")
        self.actions.append(action)
        try:
            self.advance()
        except BaseException:
            self.actions.pop()
            raise


def create_play_router() -> APIRouter:
    router = APIRouter(prefix="/play", tags=["local sandbox"])
    games: OrderedDict[str, _Game] = OrderedDict()
    lock = Lock()

    def find(game_id: str) -> _Game:
        game = games.get(game_id)
        if game is None:
            raise HTTPException(404, "table_expired")
        return game

    @router.post("")
    def start(settings: PlaySettings | None = None) -> dict[str, Any]:
        with lock:
            game_id = secrets.token_urlsafe(24)
            game = _Game(settings or PlaySettings())
            games[game_id] = game
            if len(games) > 100:
                games.popitem(last=False)
            return {"id": game_id, **game.view}

    @router.post("/{game_id}/act")
    def act(game_id: str, action: Action) -> dict[str, Any]:
        with lock:
            game = find(game_id)
            game.act(action)
            return {"id": game_id, **game.view}

    @router.post("/{game_id}/next")
    def next_hand(game_id: str) -> dict[str, Any]:
        with lock:
            game = find(game_id)
            game.new_hand()
            return {"id": game_id, **game.view}

    return router

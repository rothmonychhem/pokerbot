import pytest
from pydantic import ValidationError

from pokerbot.domain import PUBLIC_EVENT_ADAPTER, HandStarted, full_deck
from pokerbot.engine.hand_runner import run_hand
from pokerbot.engine.models import DeckAudit, HandResult
from pokerbot.engine.rng import deck_commitment
from tests.engine.helpers import RecordingAgent
from tests.engine.test_hand_runner import cfg


def test_audit_round_trip_and_immutability() -> None:
    deck = tuple(full_deck())
    audit = DeckAudit(deck=deck, commitment=deck_commitment(deck))
    assert DeckAudit.model_validate_json(audit.model_dump_json()) == audit
    with pytest.raises(ValidationError):
        audit.commitment = "0" * 64


def test_audit_rejects_tampering_and_duplicates() -> None:
    deck = tuple(full_deck())
    commitment = deck_commitment(deck)
    for tampered in (deck[::-1], deck[:-1], (*deck[:-1], deck[0])):
        with pytest.raises(ValidationError):
            DeckAudit(deck=tampered, commitment=commitment)
    for invalid in ("", "A" * 64, "0" * 63):
        with pytest.raises(ValidationError):
            DeckAudit(deck=deck, commitment=invalid)
    with pytest.raises(ValidationError):
        DeckAudit(deck=(), commitment=deck_commitment(()))


def test_start_event_carries_only_validated_commitment() -> None:
    data = dict(hand_id="h", button=0, stacks=(100, 100), small_blind=1, big_blind=2)
    commitment = deck_commitment(full_deck())
    event = HandStarted(**data, deck_commitment=commitment)
    assert PUBLIC_EVENT_ADAPTER.validate_json(event.model_dump_json()) == event
    assert event.deck_commitment == commitment
    with pytest.raises(ValidationError):
        HandStarted(**data, deck_commitment="not-a-hash")


def test_history_audit_must_match_the_original_start_commitment() -> None:
    result = run_hand(cfg((100, 100)), [RecordingAgent(), RecordingAgent()], full_deck())
    for replacement in ("0" * 64, None):
        data = result.model_dump()
        data["events"][0]["deck_commitment"] = replacement
        with pytest.raises(ValidationError, match="start commitment"):
            HandResult.model_validate(data)
    for events in ((), result.events[1:]):
        data = result.model_dump()
        data["events"] = events
        with pytest.raises(ValidationError, match="start commitment"):
            HandResult.model_validate(data)

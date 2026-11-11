import pytest

from pokerbot.domain import PublicEvent, full_deck
from pokerbot.engine.hand_runner import run_hand
from tests.engine.helpers import RecordingAgent
from tests.engine.test_hand_runner import cfg


def test_callback_receives_each_public_event_in_order_without_changing_agent_delivery() -> None:
    seen: list[PublicEvent] = []
    agents = [RecordingAgent(), RecordingAgent()]
    result = run_hand(cfg((100, 100)), agents, full_deck(), on_event=seen.append)
    assert tuple(seen) == result.events
    assert all(tuple(agent.events) == result.events for agent in agents)


def test_callback_exceptions_do_not_abort_hand_or_agent_notifications(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(event: PublicEvent) -> None:
        raise RuntimeError("broken callback")

    agents = [RecordingAgent(), RecordingAgent()]
    result = run_hand(cfg((100, 100)), agents, full_deck(), on_event=broken)
    assert all(tuple(agent.events) == result.events for agent in agents)
    assert "public-event callback failed" in caplog.text

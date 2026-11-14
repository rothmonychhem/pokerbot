from fastapi.testclient import TestClient

from pokerbot.api.app import create_app


def test_interactive_hand_can_be_played_to_completion_without_private_leaks() -> None:
    client = TestClient(create_app())
    view = client.post("/play").json()
    assert len(view["hole_cards"]) == 2 and not view["finished"]
    for _ in range(100):
        assert "deck" not in view and "seed" not in view and "deck_audit" not in view
        if view["finished"]:
            break
        action = "check" if "check" in view["legal_actions"] else "call"
        response = client.post(f"/play/{view['id']}/act", json={"type": action})
        assert response.status_code == 200
        view = response.json()
    assert view["finished"] and sum(view["stacks"]) == 300 and sum(view["payouts"]) == 0
    assert client.post(f"/play/{view['id']}/act", json={"type": "fold"}).status_code == 409


def test_invalid_actions_do_not_advance_hand() -> None:
    client = TestClient(create_app())
    view = client.post("/play").json()
    url = f"/play/{view['id']}/act"
    assert client.post(url, json={"type": "raise", "amount": 10000}).status_code == 422
    assert client.post(url, json={"type": "call", "amount": 1}).status_code == 422
    assert client.post(url, json={"type": "check"}).status_code == 422
    finished = client.post(url, json={"type": "fold"}).json()
    assert finished["finished"]
    assert client.post("/play/unknown/act", json={"type": "fold"}).status_code == 404


def finish_hand(client, view):
    for _ in range(100):
        if view["finished"]:
            return view
        kind = "check" if "check" in view["legal_actions"] else "call"
        response = client.post(f"/play/{view['id']}/act", json={"type": kind})
        assert response.status_code == 200
        view = response.json()
    raise AssertionError("hand did not finish")


def test_continuous_balances_and_rotating_button(monkeypatch) -> None:
    from tests.engine.helpers import stacked_deck

    deck = stacked_deck(0, {0: "AsAh", 1: "KsKh", 2: "QsQh"}, "2d3d4c7h9s")
    monkeypatch.setattr("pokerbot.api.play.shuffled_deck", lambda: tuple(deck))
    client = TestClient(create_app())
    view = client.post(
        "/play", json={"players": 3, "starting_stack": 20, "bots": ["easy", "easy"]}
    ).json()
    assert view["raise_presets"]["pot"] == 7
    assert all(
        view["min_raise"] <= amount <= view["max_raise"]
        for amount in view["raise_presets"].values()
    )
    assert client.post(f"/play/{view['id']}/next").status_code == 409
    finished = finish_hand(client, view)
    assert finished["stacks"] == [24, 18, 18]
    following = client.post(f"/play/{view['id']}/next").json()
    assert following["hand_number"] == 2 and following["button"] == 1
    assert following["events"][0]["stacks"] == finished["stacks"]
    assert sum(following["stacks"]) + following["pot"] == 60


def test_split_pot_and_session_elimination(monkeypatch) -> None:
    from tests.engine.helpers import stacked_deck

    deck = stacked_deck(0, {0: "2c3d", 1: "4c5d"}, "TsJsQsKsAs")
    monkeypatch.setattr("pokerbot.api.play.shuffled_deck", lambda: tuple(deck))
    client = TestClient(create_app())
    first = client.post("/play", json={"players": 2, "starting_stack": 20, "bots": ["easy"]}).json()
    assert first["raise_presets"]["pot"] == 6
    tied = finish_hand(client, first)
    assert tied["split_pot"] and tied["payouts"] == [0, 0] and not tied["session_over"]
    deck = stacked_deck(0, {0: "AsAh", 1: "KsKh"}, "2d3d4c7h9s")
    first = client.post("/play", json={"players": 2, "starting_stack": 20, "bots": ["easy"]}).json()
    won = client.post(f"/play/{first['id']}/act", json={"type": "raise", "amount": 20}).json()
    assert won["session_over"] and won["stacks"] == [40, 0]
    assert client.post(f"/play/{first['id']}/next").status_code == 409


def test_gapped_seats_preserve_physical_event_indices() -> None:
    from pokerbot.api.play import PlaySettings, _Game

    game = _Game(PlaySettings(players=3, bots=("easy", "easy")))
    game.stacks = [50, 0, 30]
    game.view["finished"] = True
    game.new_hand()
    assert game.view["active_seats"] == [0, 2]
    assert game.view["button"] == 2
    assert len(game.view["stacks"]) == 3 and game.view["stacks"][1] == 0
    assert all(event.get("action", {}).get("seat") != 1 for event in game.view["events"])


def test_settings_validation() -> None:
    client = TestClient(create_app())
    for settings in (
        {"players": 1},
        {"players": 10},
        {"starting_stack": 0},
        {"players": True},
        {"starting_stack": 20, "big_blind": 50},
        {"bots": ["easy"]},
        {"bots": ["unknown", "easy"]},
    ):
        assert client.post("/play", json=settings).status_code == 422
    view = client.post(
        "/play", json={"players": 9, "starting_stack": 200, "bots": ["easy"] * 8}
    ).json()
    assert view["players"] == 9 and len(view["stacks"]) == 9
    assert len(view["hole_cards"]) == 2

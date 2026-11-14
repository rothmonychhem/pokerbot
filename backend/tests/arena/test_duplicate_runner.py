from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from pokerbot.arena.config import ArenaConfig
from pokerbot.arena.runner import run_batch, run_simulation
from tests.arena.test_runner import InlinePool


@pytest.mark.parametrize("agent", ["calling_station", "raise"])
def test_identical_deterministic_bots_net_exactly_zero(agent: str) -> None:
    config = ArenaConfig(agents=(agent, agent), stacks=(20, 60), deal_mode="duplicate")
    records = run_batch(config, worker_id=0, start=0, count=40, workers=1)
    assert [sum(row["bot_payouts"][bot] for row in records) for bot in range(2)] == [0, 0]
    for first, second in zip(records[::2], records[1::2], strict=True):
        assert first["payouts"] == second["payouts"]
        assert first["deck_commitment"] == second["deck_commitment"]
        assert first["button"] == second["button"]
        assert first["bot_at_seat"] == [0, 1] and second["bot_at_seat"] == [1, 0]


def test_three_way_rotations_reuse_deck_and_keep_each_bot_policy_seed() -> None:
    config = ArenaConfig(
        agents=("random", "calling_station", "raise"), stacks=(20, 40, 60), deal_mode="duplicate"
    )
    records = run_batch(config, worker_id=1, start=6, count=6, workers=2)
    groups = defaultdict(list)
    for record in records:
        groups[record["deal_index"]].append(record)
        assert sum(record["bot_payouts"]) == 0
        assert sum(record["final_stacks"]) == 120
        for seat, bot in enumerate(record["bot_at_seat"]):
            assert record["bot_payouts"][bot] == record["payouts"][seat]
    assert set(groups) == {2, 3}
    for group, rows in groups.items():
        assert len({row["deck_commitment"] for row in rows}) == 1
        assert len({tuple(row["agent_seeds"]) for row in rows}) == 1
        assert [row["rotation"] for row in rows] == [0, 1, 2]
        assert {row["button"] for row in rows} == {group % 3}
        for bot in range(3):
            assert {row["bot_at_seat"].index(bot) for row in rows} == {0, 1, 2}


def test_independent_control_matches_positions_and_policy_seeds_but_changes_decks() -> None:
    config = ArenaConfig(deal_mode="duplicate")
    duplicate = run_batch(config, worker_id=0, start=0, count=8, workers=1)
    control = run_batch(
        config.model_copy(update={"deal_mode": "independent_rotations"}),
        worker_id=0,
        start=0,
        count=8,
        workers=1,
    )
    for first, second in zip(duplicate, control, strict=True):
        for key in ("hand_index", "deal_index", "rotation", "bot_at_seat", "agent_seeds", "button"):
            assert first[key] == second[key]
        if first["rotation"] == 0:
            assert first["deck_commitment"] == second["deck_commitment"]
        else:
            assert first["deck_commitment"] != second["deck_commitment"]
    assert len({row["deck_commitment"] for row in control}) == 8


def test_duplicate_real_spawn_is_repeatable_and_aggregated_by_identity(tmp_path: Path) -> None:
    config = ArenaConfig(
        agents=("calling_station", "calling_station"),
        deal_mode="duplicate",
        batch_size=2,
        output=tmp_path / "duplicate.json",
    )
    first = run_simulation(config, hands=12, workers=2)
    second = run_simulation(config, hands=12, workers=2, output=tmp_path / "again.json")
    assert first["hands"] == second["hands"] and first["summary"] == second["summary"]
    assert [bot["total_payout"] for bot in first["summary"]["bots"]] == [0, 0]
    assert first["summary"]["variance"]["stddev_bb_per_100_by_bot"] == [0.0, 0.0]


@pytest.mark.parametrize("mode", ["duplicate", "independent_rotations"])
def test_grouped_hands_must_be_divisible_before_output(tmp_path: Path, mode: str) -> None:
    config = ArenaConfig(deal_mode=mode, output=tmp_path / "must-not-exist.json")
    with pytest.raises(ValueError, match="divisible"):
        run_simulation(config, hands=3, workers=2)
    assert not list(tmp_path.iterdir())
    with pytest.raises(ValueError, match="aligned"):
        run_batch(config, worker_id=0, start=1, count=2, workers=1)


def test_duplicate_interrupt_retains_whole_groups(tmp_path: Path) -> None:
    def stop(done, total):
        if done:
            raise KeyboardInterrupt

    config = ArenaConfig(
        agents=("random", "calling_station", "raise"),
        stacks=(10, 20, 30),
        deal_mode="duplicate",
        batch_size=1,
        output=tmp_path / "partial.json",
    )
    with patch("pokerbot.arena.runner.ProcessPoolExecutor", InlinePool):
        result = run_simulation(config, hands=30, workers=2, progress=stop)
    assert result["status"] == "interrupted" and result["completed_hands"] % 3 == 0
    groups = defaultdict(list)
    for row in result["hands"]:
        groups[row["deal_index"]].append(row["rotation"])
    assert all(sorted(rotations) == [0, 1, 2] for rotations in groups.values())
    assert result["summary"]["variance"]["excluded_hands"] == 0


def test_bad_mode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ArenaConfig(deal_mode="unknown")

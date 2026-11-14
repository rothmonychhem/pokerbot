import signal
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

import pytest

from pokerbot.arena.config import ArenaConfig
from pokerbot.arena.runner import _ignore_sigint, run_batch, run_simulation


def test_batch_records_are_deterministic_and_have_no_private_history() -> None:
    config = ArenaConfig(
        deal_mode="standard", agents=("random", "calling_station", "raise"), stacks=(20, 40, 60)
    )
    records = run_batch(config, worker_id=1, start=2, count=4, workers=3)
    assert records == run_batch(config, worker_id=1, start=2, count=4, workers=3)
    for i, row in enumerate(records, start=2):
        assert row["hand_index"] == i and row["deck_seed"] == config.seed + i * 3 + 1
        assert row["button"] == i % 3
        assert sum(row["payouts"]) == 0 and sum(row["final_stacks"]) == 120
        assert row["illegal_actions"] == 0
        assert "hole_cards" not in row and "deck_audit" not in row
    with patch("pokerbot.arena.runner.run_hand") as hand:
        hand.return_value.illegal_actions = (object(),)
        with pytest.raises(RuntimeError, match="illegal"):
            run_batch(config, worker_id=0, start=0, count=1, workers=1)


def test_real_spawn_pool_writes_complete_deterministic_results(tmp_path: Path) -> None:
    config = ArenaConfig(deal_mode="standard", batch_size=3, output=tmp_path / "first.json")
    progress = []
    first = run_simulation(
        config, hands=12, workers=2, progress=lambda done, total: progress.append((done, total))
    )
    second = run_simulation(config, hands=12, workers=2, output=tmp_path / "second.json")
    assert first["status"] == second["status"] == "complete"
    assert first["hands"] == second["hands"]
    assert first["completed_hands"] == 12
    assert [r["hand_index"] for r in first["hands"]] == list(range(12))
    assert progress[0] == (0, 12) and progress[-1] == (12, 12)
    assert (tmp_path / "first.json").exists()
    assert (tmp_path / "first.json.jsonl").exists()


class InlinePool:
    """Deterministic executor double: use actual workers, exercise parent branches."""

    def __init__(self, **kwargs):
        self.shutdown_called = False

    def submit(self, fn, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, **kwargs):
        self.shutdown_called = True


def test_keyboard_interrupt_keeps_completed_batches_and_exits_cleanly(tmp_path: Path) -> None:
    def progress(done, total):
        if done:
            raise KeyboardInterrupt

    with patch("pokerbot.arena.runner.ProcessPoolExecutor", InlinePool):
        result = run_simulation(
            ArenaConfig(deal_mode="standard", batch_size=2, output=tmp_path / "partial.json"),
            hands=20,
            workers=2,
            progress=progress,
        )
    assert result["status"] == "interrupted"
    assert 0 < result["completed_hands"] < 20
    assert len({r["hand_index"] for r in result["hands"]}) == result["completed_hands"]


@pytest.mark.parametrize("error_type", [RuntimeError, OSError])
def test_worker_failure_saves_successful_partial_results(tmp_path: Path, error_type) -> None:
    original = run_batch

    def fail(config, **kwargs):
        if kwargs["start"] == 2:
            raise error_type("worker exploded")
        return original(config, **kwargs)

    with (
        patch("pokerbot.arena.runner.ProcessPoolExecutor", InlinePool),
        patch("pokerbot.arena.runner.run_batch", side_effect=fail),
    ):
        result = run_simulation(
            ArenaConfig(deal_mode="standard", batch_size=2, output=tmp_path / "failed.json"),
            hands=20,
            workers=2,
        )
    assert result["status"] == "failed" and "worker exploded" in result["error"]
    assert result["completed_hands"] >= 2 and (tmp_path / "failed.json").exists()


@pytest.mark.parametrize("hands,workers", [(0, 1), (-1, 1), (True, 1), (1, 0), (1, True)])
def test_invalid_execution_inputs(tmp_path: Path, hands, workers) -> None:
    with pytest.raises(ValueError):
        run_simulation(
            ArenaConfig(deal_mode="standard", output=tmp_path / "none.json"),
            hands=hands,
            workers=workers,
        )
    assert not list(tmp_path.iterdir())


def test_worker_initializer_ignores_sigint() -> None:
    with patch("pokerbot.arena.runner.signal.signal") as set_handler:
        _ignore_sigint()
    set_handler.assert_called_once()


def test_sigint_during_submission_cancels_unstarted_batch_and_restores_handler(
    tmp_path: Path,
) -> None:
    previous = signal.getsignal(signal.SIGINT)

    class QueuedPool(InlinePool):
        def submit(self, fn, *args, **kwargs):
            handler = signal.getsignal(signal.SIGINT)
            handler(signal.SIGINT, None)
            return Future()  # queued, not yet running

    with patch("pokerbot.arena.runner.ProcessPoolExecutor", QueuedPool):
        result = run_simulation(
            ArenaConfig(deal_mode="standard", output=tmp_path / "queued.json"), hands=4, workers=2
        )
    assert result["status"] == "interrupted" and result["completed_hands"] == 0
    assert signal.getsignal(signal.SIGINT) == previous


def test_stop_before_pool_start_writes_empty_partial_snapshot(tmp_path: Path) -> None:
    def stop(done, total):
        signal.getsignal(signal.SIGINT)(signal.SIGINT, None)

    with patch("pokerbot.arena.runner.ProcessPoolExecutor") as pool:
        result = run_simulation(
            ArenaConfig(deal_mode="standard", output=tmp_path / "empty.json"),
            hands=4,
            workers=2,
            progress=stop,
        )
    pool.assert_not_called()
    assert result["status"] == "interrupted" and result["hands"] == []


def test_bad_worker_record_indices_are_not_saved_as_success(tmp_path: Path) -> None:
    with (
        patch("pokerbot.arena.runner.ProcessPoolExecutor", InlinePool),
        patch("pokerbot.arena.runner.run_batch", return_value=[]),
    ):
        result = run_simulation(
            ArenaConfig(deal_mode="standard", batch_size=1, output=tmp_path / "bad.json"),
            hands=4,
            workers=2,
        )
    assert result["status"] == "failed" and "unexpected hand indices" in result["error"]
    assert result["hands"] == []


def test_journal_io_error_propagates_after_worker_cleanup(tmp_path: Path) -> None:
    pool = InlinePool()
    with (
        patch("pokerbot.arena.runner.ProcessPoolExecutor", return_value=pool),
        patch("pokerbot.arena.runner.ResultJournal.append", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        run_simulation(
            ArenaConfig(deal_mode="standard", batch_size=1, output=tmp_path / "full.json"),
            hands=4,
            workers=2,
        )
    assert pool.shutdown_called
    assert not (tmp_path / "full.json").exists()


def test_process_startup_oserror_saves_failed_empty_snapshot(tmp_path: Path) -> None:
    with patch("pokerbot.arena.runner.ProcessPoolExecutor", side_effect=OSError("spawn failed")):
        result = run_simulation(
            ArenaConfig(deal_mode="standard", output=tmp_path / "startup.json"), hands=4, workers=2
        )
    assert result["status"] == "failed" and result["completed_hands"] == 0
    assert "spawn failed" in result["error"] and (tmp_path / "startup.json").exists()


def test_submission_oserror_drains_existing_batch_and_saves_failed_snapshot(tmp_path: Path) -> None:
    class BrokenSubmit(InlinePool):
        def submit(self, fn, *args, **kwargs):
            if kwargs["start"]:
                raise OSError("submit failed")
            return super().submit(fn, *args, **kwargs)

    with patch("pokerbot.arena.runner.ProcessPoolExecutor", BrokenSubmit):
        result = run_simulation(
            ArenaConfig(deal_mode="standard", batch_size=2, output=tmp_path / "submit.json"),
            hands=6,
            workers=2,
        )
    assert result["status"] == "failed" and result["completed_hands"] == 2
    assert "submit failed" in result["error"] and (tmp_path / "submit.json").exists()

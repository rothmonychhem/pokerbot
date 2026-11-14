import json
import math
from pathlib import Path
from unittest.mock import patch

import pytest

from pokerbot.arena.config import ArenaConfig
from pokerbot.arena.duplicate import compare_simulations, comparison_paths, summarize_records


def row(index: int, first: int) -> dict[str, object]:
    return {
        "hand_index": index,
        "bot_at_seat": [0, 1],
        "payouts": [first, -first],
        "bot_payouts": [first, -first],
    }


def test_summary_uses_bot_identity_and_hand_calculated_block_samples() -> None:
    records = [row(0, 2), row(1, 2), row(2, 6), row(3, 6), row(5, 20)]
    records[1].update(bot_at_seat=[1, 0], payouts=[-2, 2])
    summary = summarize_records(records, agents=["raise", "raise"], big_blind=2)
    assert [bot["bot_index"] for bot in summary["bots"]] == [0, 1]
    assert summary["bots"][0]["hands"] == 5
    assert summary["bots"][0]["total_payout"] == 36
    assert summary["bots"][0]["bb_per_100"] == 360
    variance = summary["variance"]
    assert variance["complete_blocks"] == 2 and variance["excluded_hands"] == 1
    assert variance["block_hands"] == 2
    # Complete block samples are 100 and 300 bb/100, so sample SD is sqrt(20000).
    assert variance["stddev_bb_per_100_by_bot"] == [math.sqrt(20000)] * 2


def test_insufficient_blocks_report_null_not_zero() -> None:
    for records in ([], [row(0, 0)], [row(0, 0), row(1, 0)]):
        summary = summarize_records(records, agents=["random", "raise"], big_blind=2)
        assert summary["variance"]["stddev_bb_per_100_by_bot"] == [None, None]
    empty = summarize_records([], agents=["random", "raise"], big_blind=2)
    assert empty["bots"][0]["bb_per_100"] is None
    zero = summarize_records(
        [row(index, 0) for index in range(4)], agents=["raise", "raise"], big_blind=2
    )
    assert zero["variance"]["stddev_bb_per_100_by_bot"] == [0.0, 0.0]


def test_huge_integer_totals_survive_unrepresentable_float_metrics(tmp_path: Path) -> None:
    from pokerbot.arena.storage import write_result

    huge = 10**400
    records = [row(i, huge if i < 2 else -huge // 2) for i in range(4)]
    summary = summarize_records(records, agents=["raise", "raise"], big_blind=2)
    assert summary["bots"][0]["total_payout"] == huge
    assert summary["bots"][0]["bb_per_100"] is None
    assert summary["bots"][0]["bb_per_100_unavailable_reason"] == "numeric_range"
    assert summary["variance"]["stddev_bb_per_100_by_bot"] == [None, None]
    assert summary["variance"]["unavailable_reason_by_bot"] == ["numeric_range"] * 2
    result = write_result(
        tmp_path / "huge.json",
        config=ArenaConfig(),
        requested_hands=4,
        workers=1,
        records=records,
        status="complete",
        elapsed_seconds=0,
        summary=summary,
    )
    assert json.loads((tmp_path / "huge.json").read_text()) == result


def test_sd_conversion_overflow_is_unavailable_for_finite_block_samples() -> None:
    # The two block samples are about +/-1.5e308 (finite), but their sample SD
    # exceeds the largest representable float. Integer totals still cancel exactly.
    records = [row(i, 3 * 10**306 if i < 2 else -(3 * 10**306)) for i in range(4)]
    summary = summarize_records(records, agents=["raise", "raise"], big_blind=2)
    assert [bot["total_payout"] for bot in summary["bots"]] == [0, 0]
    assert summary["variance"]["stddev_bb_per_100_by_bot"] == [None, None]
    assert summary["variance"]["unavailable_reason_by_bot"] == ["numeric_range"] * 2


def test_unrepresentable_comparison_ratio_is_null_and_json_safe(tmp_path: Path) -> None:
    profiles = [profile("complete", [1e308, 1e-308]), profile("complete", [1e-308, 1e308])]
    with patch("pokerbot.arena.runner.run_simulation", side_effect=profiles):
        report = compare_simulations(
            ArenaConfig(output=tmp_path / "ratio.json"), hands=4, workers=1
        )
    assert report["comparison"]["duplicate_to_independent_ratio_by_bot"] == [None, None]
    assert json.loads((tmp_path / "ratio.json").read_text()) == report


@pytest.mark.parametrize(
    "changes",
    [
        {"hand_index": -1},
        {"hand_index": True},
        {"bot_at_seat": [0, 0]},
        {"bot_at_seat": [False, 1]},
        {"bot_at_seat": [0]},
        {"bot_payouts": [1]},
        {"bot_payouts": [True, -1]},
        {"payouts": [-1, 1]},
        {"bot_payouts": [1, 1], "payouts": [1, 1]},
        {"deal_index": -1},
        {"rotation": True},
        {"rotation": 2},
    ],
)
def test_summary_rejects_malformed_records(changes: dict[str, object]) -> None:
    record = row(0, 1)
    record.update(changes)
    with pytest.raises(ValueError):
        summarize_records([record], agents=["raise", "raise"], big_blind=2)


def test_summary_rejects_missing_fields_duplicates_and_bad_blinds() -> None:
    for records in ([{}], [row(0, 1), row(0, 1)]):
        with pytest.raises(ValueError):
            summarize_records(records, agents=["raise", "raise"], big_blind=2)
    for blind in (0, -1, True):
        with pytest.raises(ValueError):
            summarize_records([], agents=["raise", "raise"], big_blind=blind)
    with pytest.raises(ValueError):
        summarize_records([], agents=["raise"], big_blind=2)
    with pytest.raises(ValueError):
        summarize_records([None], agents=["raise", "raise"], big_blind=2)  # type: ignore[list-item]


def test_comparison_paths() -> None:
    assert comparison_paths(Path("x/report.json")) == (
        Path("x/report.duplicate.json"),
        Path("x/report.independent.json"),
    )
    assert comparison_paths(Path("report")) == (
        Path("report.duplicate.json"),
        Path("report.independent.json"),
    )


def profile(status: str, stddev: list[float | None]) -> dict[str, object]:
    return {
        "status": status,
        "completed_hands": 4,
        "error": None,
        "summary": {"variance": {"stddev_bb_per_100_by_bot": stddev}},
    }


def test_comparison_runs_matched_profiles_and_writes_atomic_report(tmp_path: Path) -> None:
    output = tmp_path / "compare.json"
    progress: list[tuple[int, int]] = []
    calls = []

    def run(config: ArenaConfig, **kwargs: object) -> dict[str, object]:
        calls.append((config, kwargs))
        callback = kwargs["progress"]
        assert callable(callback)
        callback(4, 4)
        return profile("complete", [1, None] if config.deal_mode == "duplicate" else [2, 0])

    with patch("pokerbot.arena.runner.run_simulation", side_effect=run):
        report = compare_simulations(
            ArenaConfig(),
            hands=4,
            workers=2,
            output=output,
            progress=lambda done, total: progress.append((done, total)),
        )
    assert report["status"] == "complete" and report["completed_hands"] == 8
    assert progress == [(4, 8), (8, 8)]
    assert calls[0][0].deal_mode == "duplicate"
    assert calls[1][0].deal_mode == "independent_rotations"
    assert calls[0][1]["hands"] == calls[1][1]["hands"] == 4
    assert report["comparison"]["duplicate_to_independent_ratio_by_bot"] == [0.5, None]
    assert json.loads(output.read_text()) == report


@pytest.mark.parametrize("first_status", ["interrupted", "failed"])
def test_partial_comparison_does_not_start_second_run(tmp_path: Path, first_status: str) -> None:
    result = profile(first_status, [None, None])
    result["error"] = "worker failed" if first_status == "failed" else None
    with patch("pokerbot.arena.runner.run_simulation", return_value=result) as run:
        report = compare_simulations(ArenaConfig(output=tmp_path / "report"), hands=4, workers=1)
    run.assert_called_once()
    assert report["status"] == first_status
    assert report["independent_rotations"] is None
    assert report["comparison"]["independent_stddev_bb_per_100_by_bot"] is None


@pytest.mark.parametrize("hands,workers", [(3, 1), (0, 1), (True, 1), (4, 0), (4, True)])
def test_bad_comparison_counts_touch_no_output(tmp_path: Path, hands: int, workers: int) -> None:
    with pytest.raises(ValueError):
        compare_simulations(ArenaConfig(output=tmp_path / "report"), hands=hands, workers=workers)
    assert not list(tmp_path.iterdir())


def test_interruption_between_profiles_is_saved(tmp_path: Path) -> None:
    with patch("pokerbot.arena.runner.run_simulation", side_effect=KeyboardInterrupt):
        report = compare_simulations(
            ArenaConfig(), hands=4, workers=1, output=tmp_path / "first.json"
        )
    assert report["status"] == "interrupted" and report["completed_hands"] == 0
    assert report["duplicate"] is None
    with patch(
        "pokerbot.arena.runner.run_simulation",
        side_effect=[profile("complete", [1, 1]), KeyboardInterrupt],
    ):
        report = compare_simulations(
            ArenaConfig(), hands=4, workers=1, output=tmp_path / "second.json"
        )
    assert report["status"] == "interrupted" and report["completed_hands"] == 4


def test_partial_second_profile_retains_measurements_but_suppresses_ratio(tmp_path: Path) -> None:
    with patch(
        "pokerbot.arena.runner.run_simulation",
        side_effect=[profile("complete", [1, 1]), profile("failed", [2, 2])],
    ):
        report = compare_simulations(
            ArenaConfig(), hands=4, workers=1, output=tmp_path / "report.json"
        )
    assert report["status"] == "failed"
    assert report["comparison"]["independent_stddev_bb_per_100_by_bot"] == [2, 2]
    assert report["comparison"]["duplicate_to_independent_ratio_by_bot"] == [None, None]
    assert report["comparison"]["matched_complete_profiles"] is False

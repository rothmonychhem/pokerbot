from pathlib import Path
from unittest.mock import patch

import pytest

from pokerbot.cli import main


def comparison_result(*, partial: bool = False) -> dict[str, object]:
    return {
        "status": "interrupted" if partial else "complete",
        "completed_hands": 4,
        "error": None,
        "comparison": {
            "duplicate_stddev_bb_per_100_by_bot": None if partial else [1, 1],
            "independent_stddev_bb_per_100_by_bot": None if partial else [2, 2],
            "duplicate_to_independent_ratio_by_bot": [None, None] if partial else [0.5, 0.5],
        },
    }


def test_duplicate_flag_overrides_yaml_mode(tmp_path: Path) -> None:
    source = tmp_path / "sim.yaml"
    source.write_text("deal_mode: standard\n")
    with patch(
        "pokerbot.arena.runner.run_simulation",
        return_value={"status": "complete", "completed_hands": 2, "error": None},
    ) as run:
        assert (
            main(["sim", "--config", str(source), "--hands", "2", "--duplicate", "--no-progress"])
            == 0
        )
    assert run.call_args.args[0].deal_mode == "duplicate"


@pytest.mark.parametrize("partial", [False, True])
def test_compare_flag_prints_per_bot_measured_stats(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], partial: bool
) -> None:
    source = tmp_path / "sim.yaml"
    source.write_text("deal_mode: duplicate\n")
    with patch(
        "pokerbot.arena.duplicate.compare_simulations",
        return_value=comparison_result(partial=partial),
    ) as compare:
        assert main(
            ["sim", "--config", str(source), "--hands", "2", "--compare", "--no-progress"]
        ) == (130 if partial else 0)
    compare.assert_called_once()
    output = capsys.readouterr().out
    assert "4/4 hands" in output and "bot 0 (random)" in output
    assert ("n/a" if partial else "0.500") in output


@pytest.mark.parametrize("flags", [["--duplicate"], ["--compare"]])
def test_grouped_counts_fail_before_work(tmp_path: Path, flags: list[str]) -> None:
    source = tmp_path / "sim.yaml"
    source.write_text("{}")
    with pytest.raises(SystemExit) as exc:
        main(["sim", "--config", str(source), "--hands", "3", *flags])
    assert exc.value.code == 2
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize("source_name", ["report.duplicate.json", "report.independent.json.jsonl"])
def test_comparison_derived_outputs_cannot_overwrite_config(
    tmp_path: Path, source_name: str
) -> None:
    source = tmp_path / source_name
    source.write_text("{}")
    with (
        patch("pokerbot.arena.duplicate.compare_simulations") as compare,
        pytest.raises(SystemExit) as exc,
    ):
        main(
            [
                "sim",
                "--config",
                str(source),
                "--hands",
                "2",
                "--compare",
                "--output",
                str(tmp_path / "report.json"),
            ]
        )
    assert exc.value.code == 2
    compare.assert_not_called()
    assert source.read_text() == "{}"


def test_comparison_derived_alias_cannot_overwrite_source(tmp_path: Path) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("{}")
    (tmp_path / "report.duplicate.json").symlink_to(source)
    with pytest.raises(SystemExit):
        main(
            [
                "sim",
                "--config",
                str(source),
                "--hands",
                "2",
                "--compare",
                "--output",
                str(tmp_path / "report.json"),
            ]
        )

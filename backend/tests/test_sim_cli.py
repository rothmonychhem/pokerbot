import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from pokerbot.cli import main


def stub_runner(monkeypatch: pytest.MonkeyPatch, status: str = "complete") -> MagicMock:
    module = ModuleType("pokerbot.arena.runner")
    runner = MagicMock(return_value={"status": status, "completed_hands": 2, "error": None})
    module.run_simulation = runner  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pokerbot.arena.runner", module)
    return runner


@pytest.mark.parametrize("status,code", [("complete", 0), ("interrupted", 130), ("failed", 1)])
def test_sim_statuses_and_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    code: int,
) -> None:
    source = tmp_path / "sim.yaml"
    source.write_text("{}")
    runner = stub_runner(monkeypatch, status)
    assert main(["sim", "--config", str(source), "--no-progress"]) == code
    _, kwargs = runner.call_args
    assert kwargs["hands"] == 100000 and kwargs["workers"] == 8
    assert kwargs["progress"] is None
    assert str(tmp_path / "sim-results.json") in capsys.readouterr().out


def test_sim_overrides_and_parent_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "sim.yaml"
    source.write_text("{}")
    runner = stub_runner(monkeypatch)

    def run(*args: object, **kwargs: object) -> dict[str, object]:
        progress = kwargs["progress"]
        assert callable(progress)
        progress(1, 2)
        progress(2, 2)
        return {"status": "complete", "completed_hands": 2, "error": None}

    runner.side_effect = run
    output = tmp_path / "overridden.json"
    assert (
        main(
            [
                "sim",
                "--config",
                str(source),
                "--hands",
                "2",
                "--workers",
                "1",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    _, kwargs = runner.call_args
    assert kwargs["hands"] == 2 and kwargs["workers"] == 1 and kwargs["output"] == output
    assert "2/2" in capsys.readouterr().err


@pytest.mark.parametrize("extra", [["--hands", "0"], ["--hands", "bad"], ["--workers", "-1"], []])
def test_sim_rejects_bad_arguments(extra: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["sim", *extra])
    assert exc.value.code == 2


def test_sim_rejects_bad_config_and_path_collisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "sim.yaml"
    source.write_text("invalid: true")
    runner = stub_runner(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        main(["sim", "--config", str(source)])
    assert exc.value.code == 2
    source.write_text("{}")
    with pytest.raises(SystemExit):
        main(["sim", "--config", str(source), "--output", str(source)])
    runner.assert_not_called()


def test_sim_surfaces_output_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "sim.yaml"
    source.write_text("{}")
    runner = stub_runner(monkeypatch)
    runner.side_effect = OSError("disk full")
    assert main(["sim", "--config", str(source), "--no-progress"]) == 1
    assert "disk full" in capsys.readouterr().err


def test_failed_sim_reports_saved_worker_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "sim.yaml"
    source.write_text("{}")
    runner = stub_runner(monkeypatch)
    runner.return_value = {"status": "failed", "completed_hands": 2, "error": "worker failed"}
    assert main(["sim", "--config", str(source)]) == 1
    assert "worker failed" in capsys.readouterr().err

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from pokerbot.arena.config import ArenaConfig, load_config


def test_config_defaults_and_relative_output(tmp_path: Path) -> None:
    source = tmp_path / "sim.yaml"
    source.write_text("agents: [random, raise]\nstacks: [100, 100]\noutput: data/run.json\n")
    config = load_config(source)
    assert config.agents == ("random", "raise")
    assert config.output == tmp_path / "data/run.json"
    assert config.seed == 0 and config.batch_size == 100
    assert config.small_blind == 1 and config.big_blind == 2
    source.write_text("{}")
    assert load_config(source).output == tmp_path / "sim-results.json"
    assert ArenaConfig().output == Path("sim-results.json")
    assert ArenaConfig().deal_mode == "duplicate"


@pytest.mark.parametrize(
    "data",
    [
        {"agents": ["unknown", "random"]},
        {"agents": ["random"]},
        {"agents": ["random"] * 10, "stacks": [100] * 10},
        {"stacks": [100]},
        {"stacks": [0, 100]},
        {"stacks": [True, 100]},
        {"stacks": [100.0, 100]},
        {"small_blind": 0},
        {"small_blind": 3},
        {"big_blind": 0},
        {"ante": -1},
        {"seed": -1},
        {"seed": True},
        {"batch_size": 0},
        {"batch_size": 1.5},
        {"other": 1},
    ],
)
def test_invalid_schema(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ArenaConfig.model_validate(data)


@pytest.mark.parametrize("text", ["- random\n- raise", "null", "x: [", "!!python/object:bad {}"])
def test_invalid_or_unsafe_yaml(tmp_path: Path, text: str) -> None:
    source = tmp_path / "sim.yaml"
    source.write_text(text)
    with pytest.raises(ValueError):
        load_config(source)


@pytest.mark.parametrize("output", ["sim.yaml", "sim"])
def test_config_cannot_overwrite_itself_or_its_journal(tmp_path: Path, output: str) -> None:
    source = tmp_path / ("sim.yaml" if output == "sim.yaml" else "sim.jsonl")
    source.write_text(f"output: {output}\n")
    with pytest.raises(ValueError, match="source config"):
        load_config(source)


def test_output_aliases_cannot_truncate_config(tmp_path: Path) -> None:
    source = tmp_path / "sim.yaml"
    source.write_text("output: result.json\n")
    output = tmp_path / "result.json"
    output.write_text("old result")
    assert load_config(source).output == output
    output.unlink()
    output.symlink_to(source)
    with pytest.raises(ValueError, match="source config"):
        load_config(source)
    output.unlink()
    os.link(source, output.with_suffix(".json.jsonl"))
    with pytest.raises(ValueError, match="source config"):
        load_config(source)

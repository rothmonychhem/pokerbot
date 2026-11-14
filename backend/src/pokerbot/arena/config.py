"""Validated configuration for independent baseline-agent simulation hands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field, model_validator

from pokerbot.domain import DomainModel

AgentName = Literal["random", "calling_station", "raise"]
_PositiveInt = Annotated[int, Field(strict=True, gt=0)]


class ArenaConfig(DomainModel):
    agents: tuple[AgentName, ...] = Field(default=("random", "raise"), min_length=2, max_length=9)
    stacks: tuple[_PositiveInt, ...] = (100, 100)
    small_blind: int = Field(default=1, strict=True, gt=0)
    big_blind: int = Field(default=2, strict=True, gt=0)
    ante: int = Field(default=0, strict=True, ge=0)
    deal_mode: Literal["standard", "duplicate", "independent_rotations"] = "duplicate"
    seed: int = Field(default=0, strict=True, ge=0)
    batch_size: int = Field(default=100, strict=True, gt=0)
    output: Path = Path("sim-results.json")

    @model_validator(mode="after")
    def _check(self) -> ArenaConfig:
        if len(self.stacks) != len(self.agents):
            raise ValueError("stacks must have one entry per configured agent")
        if self.small_blind > self.big_blind:
            raise ValueError("small blind must not exceed big blind")
        return self


def validate_output_path(output: Path, source: Path) -> None:
    """Prevent either result artifact from replacing the source YAML, including symlinks."""
    source = source.resolve()
    journal = output.with_suffix(output.suffix + ".jsonl")
    if any(
        candidate.resolve() == source or (candidate.exists() and candidate.samefile(source))
        for candidate in (output, journal)
    ):
        raise ValueError("result output and journal must not overwrite the source config")


def load_config(path: Path) -> ArenaConfig:
    """Safely parse YAML and resolve result paths relative to the config directory."""
    path = path.resolve()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid or unsafe simulation YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("simulation YAML must contain a mapping")
    config = ArenaConfig.model_validate(data)
    output = (path.parent / config.output).resolve()
    validate_output_path(output, path)
    return config.model_copy(update={"output": output})

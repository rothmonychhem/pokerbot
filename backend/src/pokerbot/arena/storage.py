"""Durable completed-batch journal and atomic simulation result snapshots."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Self, TextIO

from pokerbot.arena.config import ArenaConfig


class ResultJournal:
    """Replace the previous run's journal, flushing and fsyncing every completed batch."""

    def __init__(self, output: Path) -> None:
        self.path = output.with_suffix(output.suffix + ".jsonl")
        self._stream: TextIO | None = None

    def __enter__(self) -> Self:
        if self._stream is not None:
            raise RuntimeError("journal is already open")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("w", encoding="utf-8")
        return self

    def append(self, records: Sequence[Mapping[str, Any]]) -> None:
        if self._stream is None:
            raise RuntimeError("journal must be open before appending records")
        if not records:
            return
        for record in records:
            self._stream.write(
                json.dumps(dict(record), allow_nan=False, separators=(",", ":")) + "\n"
            )
        self._stream.flush()
        os.fsync(self._stream.fileno())

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None


def write_result(
    output: Path,
    *,
    config: ArenaConfig,
    requested_hands: int,
    workers: int,
    records: Sequence[Mapping[str, Any]],
    status: str,
    elapsed_seconds: float,
    error: str | None = None,
    summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one sorted final or partial snapshot; never replace a result with partial JSON."""
    if status not in ("complete", "interrupted", "failed"):
        raise ValueError("invalid simulation result status")
    hands = sorted((dict(record) for record in records), key=lambda row: row["hand_index"])
    if len({row["hand_index"] for row in hands}) != len(hands):
        raise ValueError("duplicate hand indices in simulation results")
    result: dict[str, Any] = {
        "schema_version": 1,
        "config": config.model_dump(mode="json"),
        "requested_hands": requested_hands,
        "workers": workers,
        "completed_hands": len(hands),
        "status": status,
        "elapsed_seconds": elapsed_seconds,
        "error": error,
        "hands": hands,
    }
    if summary is not None:
        result["summary"] = dict(summary)
    write_json_atomic(output, result)
    return result


def write_json_atomic(output: Path, result: Mapping[str, Any]) -> None:
    """Atomically replace a JSON artifact, preserving the previous file on failure."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, dir=output.parent, prefix=f".{output.name}."
        ) as stream:
            temporary = Path(stream.name)
            json.dump(result, stream, allow_nan=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pokerbot.arena.config import ArenaConfig
from pokerbot.arena.storage import ResultJournal, write_result


def test_journal_flushes_batches_and_replaces_old_runs(tmp_path: Path) -> None:
    output = tmp_path / "nested/run.json"
    journal = ResultJournal(output)
    with pytest.raises(RuntimeError):
        journal.append([{"hand_index": 0}])
    with journal:
        with pytest.raises(RuntimeError, match="already open"):
            journal.__enter__()
        with patch("pokerbot.arena.storage.os.fsync") as sync:
            journal.append([{"hand_index": 1}, {"hand_index": 0}])
            sync.assert_called_once()
        journal.append([])
        assert [
            json.loads(line)["hand_index"] for line in journal.path.read_text().splitlines()
        ] == [1, 0]
    with ResultJournal(output) as new:
        new.append([{"hand_index": 2}])
    assert json.loads(journal.path.read_text()) == {"hand_index": 2}


def test_atomic_result_is_sorted_and_json_compatible(tmp_path: Path) -> None:
    output = tmp_path / "nested/run.json"
    config = ArenaConfig(output=output)
    result = write_result(
        output,
        config=config,
        requested_hands=2,
        workers=8,
        records=[{"hand_index": 1}, {"hand_index": 0}],
        status="complete",
        elapsed_seconds=0.5,
    )
    assert json.loads(output.read_text()) == result
    assert result["completed_hands"] == 2
    assert result["config"]["output"] == str(output)
    assert result["error"] is None and result["schema_version"] == 1
    assert [row["hand_index"] for row in result["hands"]] == [0, 1]
    with pytest.raises(ValueError, match="duplicate"):
        write_result(
            output,
            config=config,
            requested_hands=2,
            workers=8,
            records=[{"hand_index": 0}, {"hand_index": 0}],
            status="failed",
            elapsed_seconds=0,
        )


def test_result_preserves_optional_summary(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    result = write_result(
        output,
        config=ArenaConfig(),
        requested_hands=2,
        workers=1,
        records=[],
        status="interrupted",
        elapsed_seconds=0,
        summary={"variance": {"complete_blocks": 0}},
    )
    assert result["summary"] == {"variance": {"complete_blocks": 0}}
    assert json.loads(output.read_text())["summary"] == result["summary"]
    with pytest.raises(ValueError, match="status"):
        write_result(
            output,
            config=ArenaConfig(),
            requested_hands=2,
            workers=8,
            records=[],
            status="invalid",
            elapsed_seconds=0,
        )


def test_failed_atomic_replace_preserves_old_result_and_removes_temp(tmp_path: Path) -> None:
    output = tmp_path / "run.json"
    output.write_text("old")
    with (
        patch("pokerbot.arena.storage.os.replace", side_effect=OSError("disk failure")),
        pytest.raises(OSError, match="disk failure"),
    ):
        write_result(
            output,
            config=ArenaConfig(),
            requested_hands=1,
            workers=1,
            records=[],
            status="failed",
            elapsed_seconds=1,
            error="worker failed",
        )
    assert output.read_text() == "old"
    assert list(tmp_path.iterdir()) == [output]

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "posix", reason="POSIX terminal-style process-group SIGINT")
def test_real_cli_sigint_drains_workers_and_saves_partial_results(tmp_path: Path) -> None:
    config = tmp_path / "sim.yaml"
    config.write_text("agents: [random, raise]\nstacks: [20, 20]\nbatch_size: 10\nseed: 42\n")
    output = tmp_path / "partial.json"
    journal = tmp_path / "partial.json.jsonl"
    backend = Path(__file__).resolve().parents[2]
    environment = {**os.environ, "PYTHONPATH": str(backend / "src")}
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pokerbot.cli",
            "sim",
            "--config",
            str(config),
            "--hands",
            "1000000",
            "--workers",
            "2",
            "--output",
            str(output),
            "--no-progress",
        ],
        cwd=backend,
        env=environment,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 15
        while not journal.exists() or journal.stat().st_size == 0:
            assert process.poll() is None, process.communicate()
            assert time.monotonic() < deadline, "CLI did not produce a completed batch"
            time.sleep(0.02)
        os.killpg(process.pid, signal.SIGINT)
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 130, (stdout, stderr)
        result = json.loads(output.read_text())
        assert result["status"] == "interrupted"
        assert 0 < result["completed_hands"] < 1_000_000
        saved = [json.loads(line) for line in journal.read_text().splitlines()]
        assert len(saved) == result["completed_hands"]
        assert sorted(saved, key=lambda row: row["hand_index"]) == result["hands"]
        assert all(sum(row["payouts"]) == 0 for row in saved)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)

"""Eight-worker end-to-end arena benchmark, including spawn and both result writes."""

from __future__ import annotations

import argparse
import os
import platform
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from pokerbot.arena.config import ArenaConfig
from pokerbot.arena.runner import run_simulation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hands", type=int, default=50_000)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="poker-arena-benchmark-") as directory:
        config = ArenaConfig(deal_mode="standard", seed=42, output=Path(directory) / "results.json")
        started = perf_counter()
        result = run_simulation(config, hands=args.hands, workers=args.workers)
        elapsed = perf_counter() - started
        assert result["status"] == "complete" and result["completed_hands"] == args.hands
        assert all(sum(row["payouts"]) == 0 for row in result["hands"])
        rate = args.hands / elapsed
        print(f"{platform.platform()}; Python {platform.python_version()}; CPUs={os.cpu_count()}")
        print("random vs raise; 100 chips each; blinds 1/2; seed42; batch100")
        print(f"{args.hands:,} hands; {args.workers} workers; {elapsed:.3f}s; {rate:,.0f} hands/s")
        print(
            "Includes spawn, engine, IPC, flushed JSONL, final JSON and shutdown; no progress UI."
        )
        if args.workers == 8 and rate < 2_000:
            print("FAIL: below 2,000 hands/s target")
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

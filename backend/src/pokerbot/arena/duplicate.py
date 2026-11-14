"""Duplicate-deal analysis and matched independent-rotation comparisons.

Variance is the observed sample standard deviation of n-hand block means in
bb/100, not literal 100-hand session variance or a confidence interval.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pokerbot.arena.config import ArenaConfig
from pokerbot.arena.storage import write_json_atomic

_DEFINITION = (
    "Sample standard deviation (ddof=1) of complete n-hand block samples: "
    "100 * sum(bot_payouts) / (n * big_blind). Not literal 100-hand session "
    "variance, a confidence interval, or a guarantee of variance reduction."
)


def _vector(value: Any, n: int, *, permutation: bool = False) -> list[int]:
    if (
        not isinstance(value, list | tuple)
        or len(value) != n
        or any(type(item) is not int for item in value)
    ):
        raise ValueError("record vectors must contain one integer per bot")
    if permutation and sorted(value) != list(range(n)):
        raise ValueError("bot_at_seat must be a permutation of bot identities")
    return list(value)


def _finite_ratio(numerator: int | float, denominator: int | float) -> float | None:
    try:
        value = numerator / denominator
    except OverflowError:
        return None
    if not math.isfinite(value) or (value == 0 and numerator != 0):
        return None
    return value


def summarize_records(
    records: Sequence[Mapping[str, Any]], *, agents: Sequence[str], big_blind: int
) -> dict[str, Any]:
    """Aggregate by configured bot slot, excluding incomplete n-hand blocks from SD."""
    n = len(agents)
    if not 2 <= n <= 9 or any(not isinstance(agent, str) or not agent for agent in agents):
        raise ValueError("summary requires 2-9 named bot identities")
    if type(big_blind) is not int or big_blind <= 0:
        raise ValueError("big blind must be a positive integer")
    indices: set[int] = set()
    totals = [0] * n
    blocks: dict[int, list[list[int]]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("summary records must be mappings")
        index = record.get("hand_index")
        if type(index) is not int or index < 0 or index in indices:
            raise ValueError("hand indices must be unique nonnegative integers")
        indices.add(index)
        for field in ("deal_index", "rotation"):
            if field in record and (type(record[field]) is not int or record[field] < 0):
                raise ValueError("record indices must be nonnegative integers")
        if "rotation" in record and record["rotation"] >= n:
            raise ValueError("rotation must index a bot seat")
        mapping = _vector(record.get("bot_at_seat"), n, permutation=True)
        payouts = _vector(record.get("payouts"), n)
        bot_payouts = _vector(record.get("bot_payouts"), n)
        if sum(bot_payouts) != 0 or any(
            bot_payouts[bot] != payouts[seat] for seat, bot in enumerate(mapping)
        ):
            raise ValueError("bot payouts must match seat payouts and conserve chips")
        for bot, payout in enumerate(bot_payouts):
            totals[bot] += payout
        blocks.setdefault(index // n, []).append(bot_payouts)
    complete = [block for block in blocks.values() if len(block) == n]
    deviation: list[float | None] = [None] * n
    reasons: list[str | None] = ["insufficient_complete_blocks"] * n
    if len(complete) >= 2:
        for bot in range(n):
            samples = [
                _finite_ratio(100 * sum(hand[bot] for hand in block), n * big_blind)
                for block in complete
            ]
            reasons[bot] = "numeric_range"
            if any(sample is None for sample in samples):
                continue
            try:
                value = statistics.stdev([sample for sample in samples if sample is not None])
            except OverflowError:
                continue
            if math.isfinite(value):
                deviation[bot] = value
                reasons[bot] = None
    count = len(records)
    rates = [_finite_ratio(100 * total, count * big_blind) if count else None for total in totals]
    return {
        "bots": [
            {
                "bot_index": bot,
                "agent": agents[bot],
                "hands": count,
                "total_payout": totals[bot],
                "bb_per_100": rates[bot],
                "bb_per_100_unavailable_reason": (
                    "no_hands" if not count else "numeric_range" if rates[bot] is None else None
                ),
            }
            for bot in range(n)
        ],
        "variance": {
            "block_hands": n,
            "complete_blocks": len(complete),
            "excluded_hands": count - len(complete) * n,
            "stddev_bb_per_100_by_bot": deviation,
            "unavailable_reason_by_bot": reasons,
            "definition": _DEFINITION,
        },
    }


def comparison_paths(output: Path) -> tuple[Path, Path]:
    """Derive the duplicate and matched-control artifact paths beside the report."""
    suffix = output.suffix or ".json"
    return (
        output.with_name(f"{output.stem}.duplicate{suffix}"),
        output.with_name(f"{output.stem}.independent{suffix}"),
    )


def compare_simulations(
    config: ArenaConfig,
    *,
    hands: int,
    workers: int,
    output: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Run paired profiles and persist a truthful complete or partial comparison."""
    if type(hands) is not int or hands <= 0 or hands % len(config.agents):
        raise ValueError("comparison hands must be positive and divisible by seat count")
    if type(workers) is not int or workers <= 0:
        raise ValueError("workers must be a positive integer")
    from pokerbot.arena.runner import run_simulation

    output = config.output if output is None else output
    duplicate_path, control_path = comparison_paths(output)
    duplicate: dict[str, Any] | None = None
    control: dict[str, Any] | None = None
    try:
        duplicate = run_simulation(
            config.model_copy(update={"deal_mode": "duplicate", "output": duplicate_path}),
            hands=hands,
            workers=workers,
            output=duplicate_path,
            progress=(lambda done, total: progress(done, 2 * hands)) if progress else None,
        )
        status = duplicate["status"]
        error = duplicate.get("error")
        if status == "complete":
            control = run_simulation(
                config.model_copy(
                    update={"deal_mode": "independent_rotations", "output": control_path}
                ),
                hands=hands,
                workers=workers,
                output=control_path,
                progress=(lambda done, total: progress(hands + done, 2 * hands))
                if progress
                else None,
            )
            status = control["status"]
            error = control.get("error")
    except KeyboardInterrupt:
        status, error = "interrupted", None
    dup_sd = duplicate["summary"]["variance"]["stddev_bb_per_100_by_bot"] if duplicate else None
    control_sd = control["summary"]["variance"]["stddev_bb_per_100_by_bot"] if control else None
    ratios = (
        [
            _finite_ratio(dup, independent)
            if dup is not None and independent is not None and independent > 0
            else None
            for dup, independent in zip(dup_sd, control_sd, strict=True)
        ]
        if status == "complete" and dup_sd is not None and control_sd is not None
        else [None] * len(config.agents)
    )
    report: dict[str, Any] = {
        "status": status,
        "requested_hands": hands,
        "completed_hands": (duplicate["completed_hands"] if duplicate else 0)
        + (control["completed_hands"] if control else 0),
        "error": error,
        "duplicate": duplicate,
        "independent_rotations": control,
        "comparison": {
            "matched_complete_profiles": status == "complete",
            "block_hands": len(config.agents),
            "definition": _DEFINITION,
            "duplicate_stddev_bb_per_100_by_bot": dup_sd,
            "independent_stddev_bb_per_100_by_bot": control_sd,
            "duplicate_to_independent_ratio_by_bot": ratios,
        },
    }
    write_json_atomic(output, report)
    return report

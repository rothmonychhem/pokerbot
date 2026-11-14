"""Command-line entry point and headless baseline simulations."""

import argparse
import sys
from pathlib import Path

from pokerbot import __version__
from pokerbot.arena.config import load_config, validate_output_path


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _show_progress(completed: int, total: int) -> None:
    filled = min(20, completed * 20 // total)
    bar = "#" * filled + "-" * (20 - filled)
    print(
        f"\r[{bar}] {completed}/{total}",
        file=sys.stderr,
        end="\n" if completed >= total else "",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pokerbot", description="Poker Bot Arena CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    sim = commands.add_parser("sim", help="run baseline hands with configurable deal modes")
    sim.add_argument("--config", required=True, type=Path, help="simulation YAML file")
    sim.add_argument("--hands", type=_positive_int, default=100000)
    sim.add_argument("--workers", type=_positive_int, default=8)
    sim.add_argument("--output", type=Path, help="override JSON result path")
    sim.add_argument("--no-progress", action="store_true", help="disable parent progress bar")
    sim.add_argument(
        "--duplicate", action="store_true", help="replay each deal over all bot rotations"
    )
    sim.add_argument(
        "--compare", action="store_true", help="compare duplicate deals with matched control"
    )
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        config = load_config(args.config)
        if args.duplicate:
            config = config.model_copy(update={"deal_mode": "duplicate"})
        if (args.compare or config.deal_mode != "standard") and args.hands % len(config.agents):
            raise ValueError("grouped simulation hands must be divisible by seat count")
        output = args.output.resolve() if args.output is not None else config.output
        validate_output_path(output, args.config)
        if args.compare:
            from pokerbot.arena.duplicate import comparison_paths

            for child in comparison_paths(output):
                validate_output_path(child, args.config)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    # Keep argparse help/version lightweight; workers import the runner only when requested.
    if args.compare:
        from pokerbot.arena.duplicate import compare_simulations as run
    else:
        from pokerbot.arena.runner import run_simulation as run

    try:
        result = run(
            config,
            hands=args.hands,
            workers=args.workers,
            output=output,
            progress=None if args.no_progress else _show_progress,
        )
    except (OSError, ValueError) as exc:
        print(f"simulation output failed: {exc}", file=sys.stderr)
        return 1
    status = result["status"]
    if not args.no_progress and status != "complete":
        print(file=sys.stderr)
    total_hands = args.hands * (2 if args.compare else 1)
    print(f"{status}: {result['completed_hands']}/{total_hands} hands -> {output}")
    if args.compare:
        comparison = result["comparison"]
        duplicate_sd = comparison["duplicate_stddev_bb_per_100_by_bot"]
        independent_sd = comparison["independent_stddev_bb_per_100_by_bot"]
        ratios = comparison["duplicate_to_independent_ratio_by_bot"]
        for bot, agent in enumerate(config.agents):
            dup = duplicate_sd[bot] if duplicate_sd is not None else None
            independent = independent_sd[bot] if independent_sd is not None else None
            print(
                f"bot {bot} ({agent}): duplicate SD={_metric(dup)}, "
                f"independent SD={_metric(independent)}, observed ratio={_metric(ratios[bot])}"
            )
    if result.get("error"):
        print(result["error"], file=sys.stderr)
    return {"complete": 0, "interrupted": 130, "failed": 1}.get(status, 1)


def _metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

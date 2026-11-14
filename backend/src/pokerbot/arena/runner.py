"""Bounded, reproducible spawn-process execution of independent baseline hands."""

from __future__ import annotations

import multiprocessing
import signal
import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from pathlib import Path
from time import perf_counter
from types import FrameType
from typing import Any, TypedDict

from pokerbot.agents import CallingStationAgent, RaiseAgent, RandomAgent
from pokerbot.agents.base import Agent
from pokerbot.arena.config import ArenaConfig
from pokerbot.arena.duplicate import summarize_records
from pokerbot.arena.storage import ResultJournal, write_result
from pokerbot.engine.hand_runner import run_hand
from pokerbot.engine.models import HandConfig
from pokerbot.engine.rng import shuffled_deck


class HandRecord(TypedDict):
    hand_index: int
    worker_id: int
    deck_seed: int
    button: int
    payouts: list[int]
    final_stacks: list[int]
    board: list[str]
    deck_commitment: str
    illegal_actions: int
    deal_index: int
    rotation: int
    bot_at_seat: list[int]
    bot_payouts: list[int]
    agent_seeds: list[int]


def _ignore_sigint() -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def run_batch(
    config: ArenaConfig, *, worker_id: int, start: int, count: int, workers: int
) -> list[HandRecord]:
    """A logical worker/batch has no process-global RNG or agent state."""
    records: list[HandRecord] = []
    n = len(config.agents)
    grouped = config.deal_mode != "standard"
    group_size = n if grouped else 1
    if start % group_size or count % group_size:
        raise ValueError("batch must be aligned to complete deal groups")
    for first in range(start, start + count, group_size):
        deal_index = first // n if grouped else first
        group_seed = config.seed + deal_index * workers + worker_id
        shared_deck = (
            shuffled_deck(mode="sim", seed=group_seed * n)
            if config.deal_mode == "duplicate"
            else None
        )
        agent_seeds = [group_seed * (n + 1) + bot + 1 for bot in range(n)]
        for rotation in range(group_size):
            index = first + rotation
            seed = (
                group_seed * n + (rotation if config.deal_mode == "independent_rotations" else 0)
                if grouped
                else group_seed
            )
            bot_at_seat = [(seat + rotation) % n for seat in range(n)]
            players: list[Agent] = []
            for bot in bot_at_seat:
                name = config.agents[bot]
                if name == "random":
                    players.append(RandomAgent(agent_seeds[bot]))
                elif name == "calling_station":
                    players.append(CallingStationAgent())
                else:
                    players.append(RaiseAgent())
            hand = HandConfig(
                hand_id=f"sim-{index}",
                stacks=config.stacks,
                button=deal_index % n,
                small_blind=config.small_blind,
                big_blind=config.big_blind,
                ante=config.ante,
            )
            result = (
                run_hand(hand, players, shared_deck)
                if shared_deck is not None
                else run_hand(hand, players, mode="sim", seed=seed)
            )
            if result.illegal_actions:
                raise RuntimeError(f"baseline produced illegal actions on hand {index}")
            assert result.deck_audit is not None
            by_bot = [0] * n
            for seat, bot in enumerate(bot_at_seat):
                by_bot[bot] = result.payouts[seat]
            records.append(
                HandRecord(
                    hand_index=index,
                    worker_id=worker_id,
                    deck_seed=seed,
                    button=hand.button,
                    payouts=list(result.payouts),
                    final_stacks=list(result.final_stacks),
                    board=[str(card) for card in result.board],
                    deck_commitment=result.deck_audit.commitment,
                    illegal_actions=0,
                    deal_index=deal_index,
                    rotation=rotation,
                    bot_at_seat=bot_at_seat,
                    bot_payouts=by_bot,
                    agent_seeds=agent_seeds,
                )
            )
    return records


def run_simulation(
    config: ArenaConfig,
    *,
    hands: int,
    workers: int,
    output: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Save complete/partial results; return failed status for worker errors.

    SIGINT sets a flag instead of asynchronously interrupting a journal commit.
    Running batches drain; queued batches cancel. A second SIGINT keeps requesting
    the same bounded graceful stop. IO errors propagate after pool cleanup.
    """
    if type(hands) is not int or hands <= 0:
        raise ValueError("hands must be a positive integer")
    if type(workers) is not int or workers <= 0:
        raise ValueError("workers must be a positive integer")
    group_size = len(config.agents) if config.deal_mode != "standard" else 1
    if hands % group_size:
        raise ValueError("hands must be divisible by seat count for grouped modes")
    batch_hands = config.batch_size * group_size
    destination = config.output if output is None else output
    started = perf_counter()
    records: list[HandRecord] = []
    pending: dict[Future[list[HandRecord]], tuple[int, int]] = {}
    pool: ProcessPoolExecutor | None = None
    interrupted = False
    error: str | None = None
    main_thread = threading.current_thread() is threading.main_thread()
    old_handler = signal.getsignal(signal.SIGINT)

    def request_stop(signum: int, frame: FrameType | None) -> None:
        nonlocal interrupted
        interrupted = True

    def accept(
        future: Future[list[HandRecord]], start: int, count: int, journal: ResultJournal
    ) -> None:
        try:
            batch = future.result()
        except Exception as exc:
            # Remote OSError is a worker failure, not a parent journal/disk error.
            raise RuntimeError(f"worker failed: {type(exc).__name__}: {exc}") from exc
        if [row["hand_index"] for row in batch] != list(range(start, start + count)):
            raise ValueError("worker returned unexpected hand indices")
        journal.append(batch)
        records.extend(batch)
        if progress is not None:
            progress(len(records), hands)

    if main_thread:
        signal.signal(signal.SIGINT, request_stop)
    try:
        with ResultJournal(destination) as journal:
            try:
                if progress is not None:
                    progress(0, hands)
                if not interrupted:
                    try:
                        pool = ProcessPoolExecutor(
                            max_workers=workers,
                            mp_context=multiprocessing.get_context("spawn"),
                            initializer=_ignore_sigint,
                        )
                    except OSError as exc:
                        raise RuntimeError(f"process pool startup failed: {exc}") from exc
                next_start = batch_index = 0
                while not interrupted and (pending or next_start < hands):
                    assert pool is not None
                    while len(pending) < workers and next_start < hands and not interrupted:
                        count = min(batch_hands, hands - next_start)
                        try:
                            future = pool.submit(
                                run_batch,
                                config,
                                worker_id=batch_index % workers,
                                start=next_start,
                                count=count,
                                workers=workers,
                            )
                        except OSError as exc:
                            raise RuntimeError(f"process pool submission failed: {exc}") from exc
                        pending[future] = (next_start, count)
                        next_start += count
                        batch_index += 1
                    done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                    for future in sorted(done, key=lambda f: pending[f][0]):
                        start, count = pending.pop(future)
                        accept(future, start, count, journal)
            except KeyboardInterrupt:
                interrupted = True
            except OSError:
                raise
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            finally:
                try:
                    for future, (start, count) in pending.items():
                        if future.cancel():
                            continue
                        try:
                            accept(future, start, count, journal)
                        except KeyboardInterrupt:
                            interrupted = True
                        except OSError:
                            raise
                        except Exception as exc:
                            error = f"{type(exc).__name__}: {exc}"
                finally:
                    if pool is not None:
                        pool.shutdown(wait=True, cancel_futures=True)
            status = "failed" if error is not None else "interrupted" if interrupted else "complete"
            return write_result(
                destination,
                config=config,
                requested_hands=hands,
                workers=workers,
                records=records,
                status=status,
                elapsed_seconds=perf_counter() - started,
                error=error,
                summary=summarize_records(
                    records, agents=config.agents, big_blind=config.big_blind
                ),
            )
    finally:
        if main_thread:
            signal.signal(signal.SIGINT, old_handler)

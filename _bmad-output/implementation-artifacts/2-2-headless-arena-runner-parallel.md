---
baseline_commit: 09058051cef3368fe4213b811757655535c9e72e
---

# Story 2.2: Headless arena runner (parallel)

Status: done

## Story

As a researcher, I want to run N hands between configured bots in parallel, so that sims finish fast.

## Acceptance Criteria

1. `pokerbot sim --config sim.yaml --hands 100000 --workers 8` loads validated YAML, runs that many independent baseline hands through the existing engine and writes JSON results. Preserve CLI help/version. Config supplies agents, reset stacks/blinds/ante, base seed, batch size and output path; CLI can override output and disable progress. No table-session bankroll elimination across independent hands.
2. Use ProcessPoolExecutor with explicit spawn, bounded in-flight batches and deterministic logical worker IDs/seeds. Every requested hand index appears exactly once on success. For fixed config/workers/batch layout, repeated runs produce identical hand records regardless of scheduling. Record layout and seeds; elapsed time is not deterministic. Keep baseline agents and deck RNG local; no global seeding.
3. Show a parent-only progress bar on stderr. Ctrl-C stops scheduling, cancels unstarted work, drains running bounded batches, and atomically writes `interrupted` results with actual completed hands; CLI exits 130. Worker errors retain completed records, report `failed`, save partial output and CLI exits 1. Workers ignore SIGINT so the parent coordinates graceful stopping. A completed-batch JSONL journal is flushed while running; final JSON contains sorted unique records and run status.
4. Measure at least 2,000 hands/s with baseline agents using eight workers on the available machine. Include workload, configuration, hand count, hardware/runtime and whether startup/result IO are included. Do not claim the target without a successful measured benchmark. Run the requested 100k-hand CLI path when practical and verify count/conservation; retain evidence outside tracked results.
5. Validate bad YAML/schema/agent names/stack counts/seeds/counts before work. Use safe YAML parsing. JSON output and journal must not overwrite the source config. Persist partial output before reporting worker failures; output IO failure must surface rather than claim success. Do not expose full private histories/decks in result summaries. Add real spawn-pool determinism tests, simulated interruption/failure tests and a subprocess CLI interrupt test. Default source coverage remains 100% with meaningful direct worker tests alongside real process integration.

## Tasks / Subtasks

- [x] Task 1: Add validated YAML configuration, minimal PyYAML dependency/type stubs, atomic JSON and flushed JSONL storage, CLI arguments/progress/exit statuses and tests (AC 1, 3, 5).
- [x] Task 2: Add typed hand records, deterministic batch workers, bounded spawn-process orchestration, interruption/failure collection and tests (AC 2, 3, 5).
- [x] Task 3: Add example config/benchmark command/docs; run real CLI, Ctrl-C, 100k workload and eight-worker performance measurement; regression/lint/types and focused review (AC 4, 5).

## Dev Notes

- Source architecture places headless runner under `backend/src/pokerbot/arena/` and CLI in cli.py (currently argparse help/version stub). Existing runner `run_hand` and baseline agents are implemented; reuse them. No duplicate mode, stats/CI reporting, leaderboard or arbitrary agent plugins in this story.
- Shared config API in arena/config.py: `ArenaConfig(DomainModel)` fields agents tuple of literal `random|calling_station|raise` (2–9, default random/raise), stacks strict positive int tuple (default100/100, count must match agents), small_blind=1,big_blind=2,ante=0,seed=0(nonnegative strict int),batch_size=100(positive strict int),output Path default sim-results.json. `load_config(path:Path)->ArenaConfig`, YAML safe parsing, resolve output relative to config directory. Reject unknown keys and unsafe YAML tags. PyYAML and types-PyYAML are authorized necessary YAML dependencies for this story; stdlib handles pool/progress/IO.
- Shared runner API: arena/runner.py `run_simulation(config, *, hands:int, workers:int, output:Path|None=None, progress:Callable[[int,int],None]|None=None)->dict[str,Any]`. Return keys schema_version,config,requested_hands,workers,completed_hands,status,elapsed_seconds,error,hands; status complete/interrupted/failed. On worker errors return saved failed result, IO errors raise. CLI interprets statuses as0/130/1.
- Hand records are compact JSON-compatible dicts: hand_index,worker_id,deck_seed,button,payouts(list[int]),final_stacks(list[int]),board(list[str]),deck_commitment(str),illegal_actions(int). They are summaries, not full histories. Original config includes starting stacks. Worker policy seed for each seat derived from deck_seed; rebuilding the same hand independently is supported. No secure play mode in simulation.
- Logical worker ID = batch_index % workers. Deck seed = config.seed + hand_index * workers + worker_id. Agent seed = deck_seed*(seat_count+1)+seat+1; rotate button by global hand index %seat_count. Recreate agents per hand so scheduling/batch execution order cannot affect policy streams. Results sorted by hand_index; journal ordering may reflect batch arrival. Worker count/batch size changes can change records and are persisted.
- Storage contract arena/storage.py: `ResultJournal(output:Path)` context manager with `.append(records:Sequence[Mapping[str,Any]])` flush/fsync completed batch; journal path is `output.with_suffix(output.suffix + ".jsonl")`. `write_result(output:Path, *, config:ArenaConfig, requested_hands:int, workers:int, records:Sequence[Mapping[str,Any]], status:str, elapsed_seconds:float, error:str|None=None)->dict[str,Any]` uses a same-directory temporary file + os.replace. Output parent directories may be created. Repeated runs replace the same output/journal; source config path collisions must be rejected by CLI (both paths). Journal is recovery evidence, not automatic resume support.
- Keep pool in-flight tasks bounded at workers; drain active batches on stop and retain any successfully completed ones. Avoid repeatedly rewriting the whole final JSON while running: append journal per completed batch, final snapshot once. Cancellation may leave gaps in interrupted hand indices. A failed worker cannot return an unfinished partial batch; only successfully returned batches are counted. Agent errors must not be hidden by engine fallback: workers reject result.illegal_actions.
- Prefer explicit executor lifetime rather than context-manager implicit waits; shutdown(cancel_futures=True) cancels queued jobs and joins running work. Ignore SIGINT in worker initializer, not in parent. Interruption during initialization/submission must still lead to a saved partial snapshot and cleaned resources. Additional Ctrl-C policy must avoid abandoning the last durable journal.
- Prior2.1: baseline RandomAgent uses local stdlib random; all three passed1000hands each. Existing default suite386 passed100%. Retrospective: preserve filtered observations/private audit boundary. Backend scaffold untracked; no staging unrelated changes.
- No AGENTS.md/project-context.md found. Official concurrent.futures docs confirm cancel_futures does not cancel running work, so graceful drain is necessary. Python3.12+ spawn explicit avoids platform default changes.

### References

- `_bmad-output/planning-artifacts/epics.md` Story2.2 and architecture §§1,4,6.
- `_bmad-output/implementation-artifacts/2-1-baseline-agents.md`.
- https://docs.python.org/3/library/concurrent.futures.html
- https://pyyaml.org/wiki/PyYAMLDocumentation

## Dev Agent Record

### Agent Model Used

GPT-6 Codex

### Debug Log References

- Red/green: runner tests initially failed because config/worker modules were absent. Direct worker and parent-path tests plus real spawn integration now pass; safe YAML/storage/CLI tests cover their own boundaries.
- Default regression: 439 passed, 2 slow tests deselected; 100% source coverage. Strict mypy clean across 36 source files, Ruff clean, lockfile check passed.
- Real process-group SIGINT test passes: workers ignore the terminal-style SIGINT while parent drains, exits130, and preserves exact matching completed rows in journal and final interrupted snapshot.
- Benchmarks on macOS26.6.2 arm64 / Python3.14.6 / 10 exposed CPU cores: 8 workers, random vs raise, stacks100/100, blinds1/2, seed42,batch100. 10k hands=5.567s/1796hands/s (below target with startup); 50k=19.251s/2597hands/s (target passed), including spawn, engine, IPC, journal fsync, final JSON and shutdown, progress disabled.
- Actual CLI: `PYTHONPATH=src uv run pokerbot sim --config examples/sim.yaml --hands 100000 --workers 8 --output /tmp/poker-arena.zBSd0S/results.json --no-progress` completed100000 hands, /usr/bin/time wall38.66s=2586.65hands/s. Checked unique contiguous indices, journal100000rows, zero illegal actions and chip conservation for every hand. Runtime metadata35.6907s excludes final JSON serialization; reported end-to-end benchmark uses external wall time. PYTHONPATH handles the previously documented local editable-import issue.

### Completion Notes List

- Added safe, strict YAML configuration and baseline registry fields; paths resolve relative to config with source-config alias protection for both outputs.
- Added bounded spawn-process batches and deterministic logical worker/hand/agent seed derivation, independent of scheduling; recreated baseline agents per hand and reset stacks deliberately.
- Added parent-only progress, signal-safe graceful stopping, queued cancellation and active-batch draining. Worker failures produce failed partial results; IO errors surface after cleanup.
- Added flushed/fsynced completed-hand journal and atomic sorted final JSON snapshot, compact public summaries, CLI statuses and example config/benchmark/docs.
- No changes to betting, settlement or observation rules. PyYAML and type stubs are the only new declared dependencies (PyYAML was already installed transitively).

- Story context and explicit APIs recorded; dependencies and independent-hand semantics scoped.

### File List

- backend/pyproject.toml
- backend/uv.lock
- backend/src/pokerbot/cli.py
- backend/src/pokerbot/arena/config.py (new)
- backend/src/pokerbot/arena/runner.py (new)
- backend/src/pokerbot/arena/storage.py (new)
- backend/tests/arena/__init__.py (new)
- backend/tests/arena/test_config.py (new)
- backend/tests/arena/test_runner.py (new)
- backend/tests/arena/test_storage.py (new)
- backend/tests/arena/test_interrupt_cli.py (new)
- backend/tests/test_sim_cli.py (new)
- backend/examples/sim.yaml (new)
- backend/scripts/benchmark_arena.py (new)
- backend/README.md
- _bmad-output/implementation-artifacts/2-2-headless-arena-runner-parallel.md (new)
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-11-11: Created context for next epic2 story.

- 2026-11-11: Implementation, real100k CLI/interrupt checks and quantitative throughput gates passed; status → review.

## Focused Review (2026-11-11)

- Edge Case Hunter found one concrete failure-persistence gap; no deferred issues.
- [x] [Review][Patch] Distinguish OSError raised by a worker future or pool startup/submission from parent journal/output IO failures. Worker/pool failures now become a saved failed snapshot with collected successful batches; actual parent disk failures still propagate after cleanup. Previously all OSError paths bypassed the final partial snapshot.
- Regression tests first confirmed failures for remote worker OSError, pool startup OSError and submission OSError; added cases also verify draining an existing successful batch after a submission failure.
- Review scope restricted to arena config/runner/storage, CLI, direct tests and benchmark; unrelated project changes excluded.

- Final review validation: 58 arena/CLI tests passed at100% coverage; full regression442 passed,2 slow deselected,100% coverage. Ruff and strict mypy36files pass. All review patches/tasks resolved; status → done.

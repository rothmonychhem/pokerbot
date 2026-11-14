---
baseline_commit: 09058051cef3368fe4213b811757655535c9e72e
---

# Story 2.3: Duplicate-deal mode

Status: done

## Story

As a researcher, I want duplicate poker, so that luck variance is reduced.

## Acceptance Criteria

1. ArenaConfig adds `deal_mode: Literal["standard", "duplicate", "independent_rotations"] = "duplicate"`. This follows architecture ADR4; explicit standard mode preserves prior seeded hand behavior. Duplicate generates one deck per n-hand deal group, fixes button/seat stacks within the group and replays the exact deck through all n cyclic bot-seat rotations. Slot i is a bot identity even when agent class names repeat. Keep stack conditions attached to physical seats; reset policy RNG per bot per group/rotation.
2. Results record deal_index, rotation, bot_at_seat, bot_payouts and agent_seeds, in addition to existing hand fields. Aggregate totals/rates by bot identity (not class name). Every bot occupies every seat exactly once per duplicate group. Two identical deterministic bots each net exactly zero over complete duplicate groups, with integer equality. Preserve n-way conservation and deterministic spawn execution.
3. Report observed sample standard deviation of n-hand block means expressed in bb/100 per bot. Define each block sample as `100 * sum(bot_payouts)/(n*big_blind)`, ddof1, return null for fewer than2 complete blocks, disclose block size/excluded partial data. This is not the standard deviation of literal100-hand session blocks, a confidence interval or a promise of variance reduction for every strategy.
4. `sim --duplicate` overrides mode to duplicate; YAML mode also works. `sim --compare` runs duplicate and independent-rotation control experiments with equal requested physical hand counts and positions, writes both result/journal artifacts and an atomic comparison report containing both measured stddev arrays. The control uses a fresh deck for each rotation while preserving bot rotation, button, stacks and policy seeds. Report observed ratio where defined; never assert all workloads reduce variance. CLI prints a concise per-bot comparison. On interrupted/failed first run, do not start second; persist truthful partial comparison status. Both profiles must complete for a complete comparison.
5. `--hands` always counts physical engine hands. Grouped modes/compare require positive count divisible by seat count before any output is touched. In grouped modes batch_size counts complete deal groups, so workers, journals and interruption never split a duplicate group. Parent progress still counts physical hands. Explicit standard mode remains compatible; update the prior independent example and benchmark to select it. Comparison path derivation/source-config collision protection covers report and both experiment outputs/journals.
6. Tests include fixed deck/commitment equality acrossrotations, bot mapping with duplicate names/unequal stacks, exact-zero identical policies, n-way rotations, parallel repeatability and interrupted group integrity, control deck independence, hand-count/mode validation, sample variance against hand-calculated values and real CLI comparison. Existing regressions pass and source coverage stays100%.

## Tasks / Subtasks

- [x] Task1: Extend config and batch workers/scheduling for duplicate/control groups and per-bot records; test deck/seed/rotation fairness and exact-zero invariant (AC1,2,5).
- [x] Task2: Add pure per-bot aggregation/variance summary, atomic paired comparison orchestration/report and CLI flags/output/pathvalidation with tests (AC2–5).
- [x] Task3: Add duplicate example/docs, run a real comparison with measured stddevs, full regression/coverage/types/lint and focused review (AC6).

## Dev Notes

- Current arena runner produces independent hands via spawn bounded batches; progress/SIGINT/worker-error persistence must remain. Existing CLI/storage contracts are delivered by2.2. Do not reimplement rules, expose private deck data in outputs, add full metrics or change baseline policy behavior.
- Parent implements config.py and runner.py. Shared worker rules: standard seed/button/policies unchanged. Grouped modes use n=len(agents), group g=hand_index//n, rotation r=hand_index%n; logical worker assignment is batch_index%workers. group_seed=base_seed+g*workers+worker_id; duplicate deck_seed=group_seed*n for everyrotation; control deck_seed=group_seed*n+r. Policy seed indexed bybot = group_seed*(n+1)+bot+1 in both profiles. Seat s holds bot `(s+r)%n`; button=g%n, stacks stay config.stacks. Recreate agent objects perrotation. Duplicate shuffles once and passes the same immutable deck to run_hand; control uses distinctseeded decks. Existing explicit-deck runner snapshots input.
- All records add `deal_index` (g for grouped, hand_index for standard), `rotation` (r for grouped,0 standard), `bot_at_seat: list[int]`, `bot_payouts: list[int]`, `agent_seeds: list[int]` indexedbybot. Hand_index remainsglobalphysicalindex. Include summary on all final simulation snapshots, computed on actually completed records. Summary groups analysis blocks by hand_index//n in everymode, excludes incomplete blocks; standard blocks simply contain n independent hands.
- Shared summary API in arena/duplicate.py: `summarize_records(records: Sequence[Mapping[str,Any]], *, agents:Sequence[str], big_blind:int)->dict[str,Any]`. Returns `bots` rows with bot_index,agent,hands,total_payout,bb_per_100 (null ifzero observations), plus `variance` with block_hands,complete_blocks,excluded_hands,stddev_bb_per_100_by_bot (list[float|None]). Require consistent bot mapping/vector sizes, no repeated handindices, nonnegative integer indices and meaningful positive blind. Validating rawsummaryinput is appropriate to prevent misleading reports.
- Parent passes `summary=` to extended storage.write_result optional Mapping (defaultNone preservingminimalstoragefixtures). Agent implements storage optionalparameter and extracts `write_json_atomic(output:Path,result:Mapping[str,Any])->None` for comparisonreportreuse. Existing atomic error cleanup preserved.
- `comparison_paths(output:Path)->tuple[Path,Path]` in duplicate.py returns `<stem>.duplicate<suffix>` and `<stem>.independent<suffix>` (use .json if outputhasnosuffix). `compare_simulations(config, *, hands:int, workers:int, output:Path|None=None, progress:Callable[[int,int],None]|None=None)->dict[str,Any]` lazily imports runner.run_simulation to avoidcycle; run duplicate then independent_rotations, eachconfigcopy mode; childoutputpaths derivedfromreportpath. Return/report keys status,completed_hands(totalacrossprofiles),requested_hands(perprofile),error,duplicate,independent_rotations,comparison. Progresscallbacktotal2*hands with controloffsethands. Run results carry summary. comparison includes measured stddev arrays, ratios (duplicate/control only when controlpositive and duplicateknown), block_hands and definition. Leave absent secondexperiment null whenfirstnotcomplete; no fakezero stddevs. Sourceconfigfile must be protected from all derivedoutputs/journals by CLI before runs.
- CLI preserves priorstandardcalls/mocks; imports compare function lazily only with --compare. --duplicate setsconfig.deal_mode duplicate; --compare choosespairedprofiles regardless priorconfigmode. Group divisibility is a badargument/config and shouldfail before starting work (CLI argparse error2; API ValueError).
- Existing run_simulation pendingvalidation checks physicalindexranges; grouped count/start aligned n is enforced. `batch_size*n` physicalhands perjob. No incomplete groups enterjournal because failedjobs returnnothing. Statistical pairing unitisn-handgroup; physicalhandsarecorrelated in duplicate mode. Incomplete groups in imported/ad hoc rawsummarydata excluded from stddev but included per-bottotals with countsdisclosed.
- No new dependencies. stdlib statistics.stdev sufficient; MonteCarlo/equity notneeded. Existing priorstory442defaulttests at100%, actual100k8workers2587hands/s; no newthroughputgate forduplicate because replaysmultiplyphysicalwork. Backendhasuntracked priorfiles; avoidstagingunrelatedchanges.
- NoAGENTS.md/project-context.md found. Sourceepic2.3 requiresvariancecomparison, notguaranteeduniversalreduction. Explicitmatchedcontrol makes theexperiment interpretable.

### References

- `_bmad-output/planning-artifacts/epics.md`, Story2.3; architecture §§1,6 and duplicate-poker ADR.
- `_bmad-output/implementation-artifacts/2-2-headless-arena-runner-parallel.md`.
- Existing arena config/runner/storage and engine run_hand APIs.

## Dev Agent Record

### Agent Model Used

GPT-6 Codex

### Debug Log References

- Red/green: duplicate worker tests initially failed on the missing mode field. Implemented deck reuse, complete cyclic rotations and bot mapping; 26 worker/runner tests passed with runner coverage100%.
- Exact invariants: identical CallingStationAgent and RaiseAgent pairs each net exactly0 chips over20 complete duplicate groups, including unequal seat stacks. Three-way tests verify each bot occupies every seat, common deck hash/button and policy seeds per group. Matched control uses fresh decks while preserving positions and seeds.
- Real CLI: `PYTHONPATH=src uv run pokerbot sim --config examples/duplicate.yaml --hands 10000 --workers 4 --compare --output /tmp/poker-duplicate.XNI2xf/comparison.json --no-progress` completed20000 physical hands (10000perprofile,5000two-handblocks). Verified paired positions/button/policyseeds, exact duplicate deckreuse and first-control-deckmatching, plus chip conservation across both profiles.
- Measured sample SD of normalized two-hand block means: duplicate1619.7608293831163bb/100 versus independent2208.530106885936bb/100 for each bot; observed ratio0.7334112513716219. These are actual sampled workload results, not a universal reduction claim or literal100-hand-session variance.
- Before architecture-default reconciliation: full default regression486passed,2slowdeselected,100%coverage. After selecting duplicate as architecture-default and making legacy independent tests/examples explicit standard:100arena/CLI tests passed. Full final regression recorded below.

### Completion Notes List

- Added complete duplicate/control deal groups, immutable shared-deck replay, deterministic per-bot RNG reset and additive bot-mapping metadata; standard hand streams remain unchanged when explicitly selected.
- Added identity-based totals/rates and sample block SD, with nulls for insufficient data and excluded-hand counts; repeated class names remain separate configured bots.
- Added paired comparison orchestration, preserved child result/journal files, atomic report, truthful partial status and suppressed ratios unless both profiles complete.
- Added CLI flags/source-path protection, example config and precise documentation of physical hand budgets, analysis units and measured results. No new dependencies.

- Final architecture reconciliation: ADR4 specifies duplicate as the default arena mode. Set default duplicate and keep prior independent experiment/benchmark explicitly standard. This supersedes the initial compatibility assumption of a standard default; existing standard seed behavior remains unchanged when selected.

- Recorded duplicate/control pairing semantics, physicalhandcount meaning and statistical analysis unit beforeimplementation.

### File List

- backend/src/pokerbot/arena/config.py
- backend/src/pokerbot/arena/runner.py
- backend/src/pokerbot/arena/storage.py
- backend/src/pokerbot/arena/duplicate.py (new)
- backend/src/pokerbot/cli.py
- backend/tests/arena/test_duplicate.py (new)
- backend/tests/arena/test_duplicate_runner.py (new)
- backend/tests/arena/test_config.py
- backend/tests/arena/test_runner.py
- backend/tests/arena/test_storage.py
- backend/tests/test_duplicate_cli.py (new)
- backend/examples/duplicate.yaml (new)
- backend/examples/sim.yaml
- backend/scripts/benchmark_arena.py
- backend/README.md
- _bmad-output/implementation-artifacts/2-3-duplicate-deal-mode.md (new)
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-11-11: Created story context forduplicate-deal mode.

- 2026-11-11: Duplicate/control execution, variance reporting and real comparison validated; status → review.

## Focused Review (2026-11-11)

- Edge Case Hunter found one concrete numeric persistence gap; no deferred issues.
- [x] [Review][Patch] Preserve arbitrary-size integer bot totals when float rate/SD conversion overflows. Summary now emits null with an explicit numeric-range reason instead of raising and losing final output. Guard unrepresentable comparison ratios too. Tests cover true huge-integer rate overflow, finite block samples whose true SD overflows, ratio overflow/underflow, and JSON persistence of preserved integer totals.
- Review scope: duplicate/control worker changes, mode configuration, mapping/statistics/comparison logic, CLI/output integration and directly affected tests. Prior unrelated work excluded.
- Initial review validation: 486 default tests passed at100% source coverage; Ruff and strict mypy across37source files passed. Numeric regression and final full-suite evidence follow below.

- Final review validation: 489 default tests passed, 2 slow tests deselected, 100% source coverage. Ruff and strict mypy across37source files passed; touched-file formatting checked. All tasks and the numeric review patch resolved; status → done.

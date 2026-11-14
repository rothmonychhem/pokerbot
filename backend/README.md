# pokerbot (backend)

```bash
uv sync
uv run pytest
uv run uvicorn pokerbot.api.app:app --reload
```

### Shuffling and deck audit

`run_hand(config, agents)` securely shuffles a fresh 52-card deck using
`secrets.SystemRandom`. For reproducible simulations use
`run_hand(config, agents, mode="sim", seed=42)`: each hand gets a fresh NumPy
`Generator(PCG64(seed))`. Sim mode requires a non-negative integer seed; play mode
rejects seeds. There is no global RNG state. For a sequence of simulated hands,
assign a separate seed to each hand.

The first public `HandStarted` event contains `deck_commitment`, a lowercase
SHA-256 digest. Its input is the concatenation of the initial deck's two-character
card codes in draw order, encoded as ASCII (no separators). Only the digest is
broadcast. Observations and public events contain neither seed nor deck order.

The completed **private** `HandResult.deck_audit` retains that initial deck and
commitment, including unused and burn cards. It validates the hash and unique
cards on JSON reload. Keep this private history separate from agent events:
it includes every player's private cards, including mucked hands.

To replay, keep the original `HandConfig` and effective voluntary action log
(`PlayerActed` events whose kind is `ActionType`), then feed those actions to each
seat in order. CALL uses `Action.call()`; its public amount is a street total,
not an argument to the action. Use the same sim seed in the locked environment,
or pass the saved `result.deck_audit.deck` as the third argument to `run_hand`.
The latter also replays secure play hands and survives shuffle-library changes.
An explicit deck cannot be combined with sim mode or a seed. Existing valid
partial fixture decks remain supported and are committed exactly as supplied.

Seed reproducibility requires the same NumPy environment (`uv sync --locked`);
NumPy's `Generator` does not guarantee compatibility across versions. Preserve
the deck for durable replay. Replaying effective actions reproduces game events
and payouts; reproducing diagnostics for an illegal/exceptional agent requires
reproducing its original invalid return or exception as well.

### Ranking, ranges and equity

```python
from pokerbot.domain import parse_cards
from pokerbot.eval import equity_vs_hand, equity_vs_range, parse_range, rank_hand

rank = rank_hand(parse_cards("AsKsQsJsTs"))  # 1 (strongest); lower ranks win
hero = parse_cards("AsAh")
fixed = equity_vs_hand(hero, parse_cards("KcKh"), samples=50_000, seed=42)
versus_kings = equity_vs_range(hero, parse_range("KK"), samples=50_000, seed=42)
range_ = parse_range("AKs, TT+, A5s-A2s, KQo")
```

`rank_hand` accepts 5–7 distinct domain cards. `rank_hands` validates and evaluates
a batch of hands with the same card count. Both use PH Evaluator's native ranking.
Ranks range from 1 (royal flush) to 7462 (weakest high card).

Equity functions return a heads-up pot share in [0, 1], with ties worth one half.
The board can contain 0, 3, 4 or 5 cards. Both functions use a fresh local PCG64 RNG
(default seed 0, default 10,000 samples); they never alter engine or global RNGs.
`WeightedCombo(cards=(card1, card2), weight=...)` supplies a finite non-negative
relative weight. Blocked combos and zero weights are removed before normalization;
duplicate/reversed combo weights add. An empty or wholly blocked range is an error.
Numba compiles weighted selection, uniform runout sampling without replacement,
native ranking and tie scoring into a single-thread loop.

Range notation supports pairs (`TT`), suited/offsuit classes (`AKs`, `KQo`), bare
nonpairs (`AK`, all 16 suit combinations), concrete combos (`AsKd`), pair plus
(`TT+` through AA), fixed-first-rank nonpair plus (`ATs+` through AKs), and inclusive
intervals (`A5s-A2s`, `99-JJ`). Nonpair intervals must share their first rank and
suitedness; write higher ranks first within each class. Comma-separated overlaps
deduplicate with weight 1. Supply weights through `WeightedCombo`, rather than
through notation. Malformed tokens, duplicate cards and invalid weights are rejected.

The approximate 81.9% AA-vs-KK fixture averages all six KK suit combinations;
specific suits change flush blockers. At 50,000 samples, seed 42 produces 0.82236
for `AsAh` versus `KK`, within the required ±0.005 tolerance.

Run the warmed single-core benchmark with:

```bash
PYTHONPATH=src uv run python scripts/benchmark_eval.py
```

It measures 200,000 distinct-card seven-card hands after JIT warmup and reports
the encoded kernel and the public batch (including validation/encoding) separately.
Preparation of input objects and first-call compilation are excluded. On macOS
26.6.2 arm64, Python 3.14.6, NumPy 2.5.4, Numba 0.67.0 and phevaluator 0.6.0,
the final run measured 26.8 million encoded evaluations/s and 412,000 public
batch evaluations/s. Timings vary by machine; the script checks both against
200,000 evaluations/s. The first equity/evaluation batch call compiles its kernel.

The compiled kernels call the exported C evaluator functions in phevaluator 0.6's
native extension through ctypes. The dependency is constrained to that minor
version; tests check all hand sizes against the public library API. A library
upgrade must verify this ABI. Native addresses are never persisted in a Numba
disk cache. Seed reproducibility requires the locked dependency environment.

### Table sessions and private hand history

```python
from pokerbot.engine.table import TableConfig, TableSession
from pokerbot.engine.history import HandHistory, parse_text_actions

# Supply one Agent per physical seat, in seat order.
session = TableSession(
    TableConfig(table_id="practice", stacks=(100, 100, 100), mode="sim", seed=42),
    agents,
)
hands = session.play(10)  # newly completed histories; stops if fewer than two can play
session.sit_out(1)       # between hands only; sit_in(1) resumes that seat

history = hands[0]
restored = HandHistory.from_json(history.to_json())
assert restored == history
assert parse_text_actions(history.to_text()) == history.actions
```

The synchronous session carries stacks forward and uses a moving button: the
initial configured seat acts as button if eligible, otherwise the next eligible
clockwise seat; each later hand advances to the next eligible seat. Busted and
sitting-out seats are skipped. Heads-up, the button posts the small blind.
Dead-button and missed-blind accounting are outside this policy. Blinds/antes
and all-in/side-pot rules remain handled by the existing PokerKit hand runner.

Physical seats remain stable for agents, observations and public events. Internally,
each hand compacts participating players into dense engine seats; private history
records the `seats` mapping, full pre-hand `table_stacks`, dense `config` and dense
`result`. `history.events` and `history.actions` apply the physical mapping. Every
original agent, including sitting-out/busted agents, receives each public event
once and in order; only participating agents are asked to decide. Observer
exceptions are logged and isolated. A standalone `run_hand` can also take an
optional `on_event` callback; its existing agent notifications remain unchanged.

`rebuy_policy="none"` (default) excludes busted seats and disables rebuys.
`"manual"` permits `session.rebuy(seat, amount)` between hands. `"auto"` requires
`rebuy_to=<positive chips>` and refills only busted players who are not sitting out;
it also permits manual rebuys. Positive nonzero stacks are not auto-topped-up.
Additional chips are recorded in `session.rebuy_totals`. Sitting out preserves a
seat's balance. No-hand attempts or failed hands do not commit staged rebuys,
stacks, button position, histories or hand numbers. Agent callbacks already
delivered during a failed hand cannot be rolled back. Session balance properties
reflect completed hands. Mutating policies or starting reentrant play during a
hand is rejected; the session is intended for serial use.

Default sessions use secure play shuffles. A simulated hand uses base seed plus
its completed-hand index, so repeated `play` calls continue the same deterministic
sequence. IDs are `<table_id>-<one-based hand number>`; choose distinct table IDs
for separate sessions. `play_hand(deck=...)` accepts a fixture/replay deck directly
and deliberately bypasses that hand's shuffle settings. Secure/seed replay and
deck commitment guarantees remain those documented above.

**Full JSON and text histories are private.** They include the initial deck audit,
which discloses all cards, including unused cards and mucked hands. Do not send
them to agents or use them as public table-state messages. Only mapped public
events preserve showdown reveal rules.

Text is a deterministic PokerStars-style **PokerBot generated subset v1**, not a
general PokerStars importer. It uses integer chips, `Player<physical-seat>` labels,
hole-card/street/summary markers, forced posts, call deltas, raise increments and
raise-to totals, all-in suffixes, public shows, net payouts and a private audit
section. `parse_text_actions` accepts that generated subset and restores forced
and voluntary `PublicAction` values, including street-total call amounts and
all-in flags. JSON preserves the complete configuration/result/seat mapping;
text parsing returns the action list rather than reconstructing a whole history.

### Baseline reference agents

```python
from pokerbot.agents import CallingStationAgent, RandomAgent, RaiseAgent
from pokerbot.engine.table import TableConfig, TableSession

agents = [RandomAgent(seed=7), CallingStationAgent(), RaiseAgent()]
session = TableSession(
    TableConfig(stacks=(100, 100, 100), mode="sim", seed=42,
                rebuy_policy="auto", rebuy_to=100),
    agents,
)
histories = session.play(10)
```

These are deliberately simple arena reference policies. `RandomAgent` samples
uniformly over legal action types, then uniformly over inclusive integer bet/raise
bounds. Its optional nonnegative integer seed controls a private `random.Random`
stream; it does not change global RNG state or the secure/PCG64 deck stream.
Use fresh agents with the same seeds and the same decision sequence to repeat a
run in the same Python environment. Reusing an agent continues its stream; no
cross-Python-version decision-stream guarantee is made. Agent randomness is for
policy sampling, not secure shuffling.

`CallingStationAgent` checks when possible and otherwise calls. `RaiseAgent`
chooses the minimum legal raise when available, otherwise an opening bet equal
to the observed pot, clamped to min/max bounds; when aggression is unavailable
it checks/calls. For restricted views lacking either passive option, both use a
legal fold, or the minimum legal aggressive action if that is the only option.
CALL actions have no amount; bet/raise amounts are street totals. `observe` is a
no-op: none of these agents stores public events or receives private history.

Run the explicit longer acceptance workload with:

```bash
uv run pytest tests/agents/test_baselines.py -m slow
```

It seats all three reference agents on every one of 1,000 seeded hands, varies
3–9 seats and table parameters, and verifies no agent error/fallback warnings,
illegal-action records or chip loss. The default suite separately exercises
policy branches and seeded multi-hand session integration. The parallel runner is documented below; duplicate deals, detailed statistics
and leaderboards remain later epic 2 stories.

### Parallel headless simulations

```bash
uv run pokerbot sim --config examples/sim.yaml --hands 100000 --workers 8
# Optional: --output /path/to/results.json --no-progress
```

The YAML example configures `agents: [random, raise]`, `stacks: [100, 100]`,
blinds 1/2, ante 0, seed 42, batch size 100, and an output path. Agent names are
`random`, `calling_station`, and `raise`. Config accepts 2–9 agents with one
positive integer stack per seat. Unknown keys, unsafe YAML tags, invalid seeds,
blinds, counts and names are rejected. YAML output paths resolve relative to the
config directory; `--output` resolves relative to the current directory. Output
and journal paths cannot replace the source YAML, including file aliases.

In explicit `standard` mode, each hand is independent: starting stacks reset,
and the button rotates by hand
index. This runner does not eliminate busted players or carry bankrolls forward;
use `TableSession` when that behavior is needed. It uses a spawn-based process
pool with at most one in-flight batch per configured worker. Logical worker IDs
are assigned by batch index modulo worker count, independently of actual process
scheduling. Hand `i` uses deck seed `base_seed + i * workers + worker_id`, and
seat `s` uses baseline decision seed `deck_seed * (seat_count + 1) + s + 1`.
Agents are recreated per hand. Equal config, hand count, worker count, batch size
and locked environment reproduce the same hand records; changing worker count
or batch size can change records. Elapsed time is runtime metadata, not part of
deterministic replay.

The parent shows a progress bar on stderr. Completed batches append to
`<output>.jsonl`, flushed and fsynced per batch. Final JSON is written through a
same-directory temporary file and atomic replacement, with schema version,
config, requested/completed counts, worker count, run status/error, elapsed time
and hand records sorted by hand index. Records contain index, logical worker,
deck seed, button, payouts, final stacks, board, deck commitment and illegal-action
count. They contain no hole cards or full private deck/history. Per-seat statistics,
duplicate deals and leaderboard persistence remain later stories.

Ctrl-C requests a graceful stop rather than interrupting a journal commit. The
parent stops scheduling, cancels unstarted work, drains active batches and writes
an `interrupted` result; CLI exit code is 130. A second Ctrl-C keeps requesting the
same graceful stop. Stop latency depends on the configured batch size and hand
duration. Worker errors produce saved `failed` results and exit 1; successful runs
exit 0, bad configuration exits 2. Output IO failures surface as errors, with the
last successfully flushed journal available when possible. An unfinished or failed
batch is not counted; partial hand indices can have gaps. This is batch-level
recovery, not automatic resume. Repeating a run replaces that output and journal;
choose distinct paths to preserve previous runs. Retain the original config and
CLI settings alongside a journal for recovery. No durability promise is made for
force-killing the process or machine failure before a flush.

Run the end-to-end benchmark with:

```bash
PYTHONPATH=src uv run python scripts/benchmark_arena.py --hands 50000 --workers 8
```

Recorded on macOS 26.6.2 arm64, Python 3.14.6, a machine exposing 10 CPU cores:
eight workers, random versus raise, 100 chips per seat, blinds 1/2, seed 42 and
batch size 100 completed 50,000 hands in 19.251s (**2,597 hands/s**).
The real 100,000-hand CLI invocation took 38.66s (**2,587 hands/s**) including
command startup, engine work, IPC, journal flushes, final JSON and shutdown.
The shorter 10,000-hand benchmark measured 1,796 hands/s; process startup is not
amortized as well. These are workload-specific measurements, not a guarantee for
all seat counts or policies. Progress display was disabled for these measurements.
The runner's `elapsed_seconds` is captured before final JSON serialization;
use the benchmark's external timer for end-to-end throughput.

### Duplicate deals and matched variance comparison

```bash
# Replay every deck through all cyclic bot-seat rotations.
uv run pokerbot sim --config examples/duplicate.yaml --hands 10000 --workers 4
# Or override a standard config with --duplicate.

# Compare equal-cost duplicate and independent-rotation experiments.
uv run pokerbot sim --config examples/duplicate.yaml --hands 10000 --workers 4 \
  --compare --output comparison.json
```

`deal_mode` is `duplicate` (default), `standard`, or `independent_rotations`.
The earlier `examples/sim.yaml` and independent-hand benchmark explicitly select
`standard` to preserve that experiment.
Duplicate mode shuffles one deck per deal group, then replays that same deck for
every cyclic assignment of bots to seats. A group's button and seat stacks stay
fixed. Bot identities are their configured list indices, so two `calling_station`
entries remain two distinct bots. Each bot occupies every seat exactly once.
Policies reset for every rotation; a bot's policy seed stays fixed within a group.
Outputs keep seat payouts and add `deal_index`, `rotation`, `bot_at_seat`,
`bot_payouts` and per-bot `agent_seeds`. Summary totals and rates use bot identity.

`--hands` always counts physical engine hands. Grouped modes require it to be
divisible by the number of bots, before creating any output. In these modes
`batch_size` counts whole deal groups, and progress counts physical hands.
Workers and interruption handling never split a group into saved partial rotations.
Every hand still starts with the configured seat stacks; this is independent-hand
research, not a bankroll-carrying session.

For grouped modes with n bots, group g uses
`group_seed = base_seed + g * workers + worker_id`. Duplicate deck seed is
`group_seed * n`; the independent-rotation control uses `group_seed * n + rotation`.
Both profiles use bot seed `group_seed * (n + 1) + bot_index + 1` and button `g % n`.
Seat s holds bot `(s + rotation) % n`. Thus the control preserves positions, stacks,
button and policy seeds while using a fresh deck for each rotation; its first
rotation shares the duplicate group's deck. Standard-mode seed behavior stays
as documented above. Changing worker/batch layout can change the generated deals.

`--compare` runs duplicate first and then the independent-rotation control with
the same requested physical hand count, regardless of the config's initial mode.
For `comparison.json` it writes `comparison.duplicate.json` and
`comparison.independent.json`, their `.jsonl` journals, and the atomic comparison
report. The combined progress total is twice `--hands`. On a failed/interrupted
first profile, the second does not start. Partial reports retain observed counts
and measurements, and do not report a matched ratio unless both profiles complete.
Derived artifact paths are also checked against the source config before work.
As with standard runs, use distinct output paths to retain previous experiments.

The variance field has a precise analysis unit: for each complete n-hand block,
take `100 * sum(bot_payouts) / (n * big_blind)`, then compute sample standard
deviation across those block samples with ddof=1. Values are expressed in bb/100.
They are **not** the standard deviation of literal 100-hand sessions, a confidence
interval, or a guarantee that duplicate play lowers variance for every policy.
Fewer than two complete blocks yields `null`, not a fabricated zero; excluded
partial hands are disclosed. Zero control deviation makes a ratio undefined.
Standard-mode summaries use n independent hands per analysis block as well.
If arbitrary-size integer payouts exceed floating-point metric range, integer
totals remain intact and rates/deviations are `null`, with an unavailable reason
in the summary. Numerically unrepresentable comparison ratios are also `null`.

A recorded real CLI comparison used random versus raise, stacks 100/100,
blinds 1/2, seed 42, four workers and 100 deal groups per batch. Each profile
completed 10,000 physical hands (5,000 two-hand blocks). Both bots' observed
block-rate standard deviation was **1,619.761 bb/100** in duplicate mode versus
**2,208.530 bb/100** in the control, ratio **0.733**. This experiment showed lower
observed variability; other lineups can differ. Separate exact-equality tests
verify zero net chips per bot for identical deterministic policies over complete
duplicate groups, including unequal seat stacks.

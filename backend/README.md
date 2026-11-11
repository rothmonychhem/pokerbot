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
policy branches and seeded multi-hand session integration. Arena parallelism,
CLI configuration and performance reporting belong to later epic 2 stories.

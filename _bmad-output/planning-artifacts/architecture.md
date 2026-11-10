# Architecture — Poker Bot Arena

Version 1.0 · 2026-11-10

## 1. Repository layout (monorepo)

```
poker/
├── backend/
│   ├── pyproject.toml            # uv-managed
│   ├── src/pokerbot/
│   │   ├── engine/               # PokerKit wrapper, table, hand history, RNG
│   │   ├── eval/                 # phevaluator wrapper, equity (Monte Carlo, Numba), ranges
│   │   ├── agents/
│   │   │   ├── base.py           # Agent protocol, Observation, Action
│   │   │   ├── heuristic/        # preflop charts, postflop logic, bluffing
│   │   │   ├── gto/              # abstraction, MCCFR, blueprint, action translation, search
│   │   │   ├── modeling/         # stats tracker, classifier, range narrowing, exploitation
│   │   │   ├── personality/      # schema, presets, shaper, tilt, humanizer
│   │   │   └── factory.py        # (difficulty, personality) -> Agent
│   │   ├── arena/                # headless sim runner, duplicate mode, metrics, Elo
│   │   ├── api/                  # FastAPI routes + WebSocket protocol
│   │   ├── persistence/          # SQLModel models, repositories
│   │   └── cli.py                # `pokerbot sim ...`, `pokerbot train ...`
│   ├── training/                 # blueprint training configs & scripts
│   ├── artifacts/                # trained blueprints (git-lfs / gitignored)
│   └── tests/
├── frontend/                     # React + TS + Vite
│   └── src/{components,features/{lobby,table,history,stats},store,ws}
├── docker-compose.yml
└── _bmad-output/
```

## 2. Core abstractions

```python
class Observation(BaseModel):          # an information set — NEVER contains others' hole cards
    hand_id: str; seat: int; hole_cards: tuple[Card, Card]
    board: list[Card]; street: Street; pot: int; stacks: list[int]
    to_call: int; min_raise: int; max_raise: int
    action_history: list[PublicAction]; button: int; big_blind: int
    legal_actions: list[ActionType]

class Agent(Protocol):
    def decide(self, obs: Observation) -> Action: ...
    def observe(self, event: PublicEvent) -> None: ...      # showdowns, others' actions (for modeling/tilt)
```

The engine builds `Observation` from PokerKit state per seat. A hypothesis property test asserts no other seat's hole cards are reachable from any observation.

## 3. Decision pipeline (every bot)

```
Observation
   │
   ▼
StrategyCore (by difficulty) ──► distribution over abstract actions
   │        {fold, check/call, bet 33%, 66%, 100%, 150%, all-in}
   ▼
OpponentModel adjust (Advanced/Expert) ──► exploit-shifted distribution
   ▼
PersonalityShaper ──► style-skewed distribution
   ▼
MistakeNoise (by difficulty ε) ──► final distribution
   ▼
Sampler (seeded RNG) → abstract action → concrete legal Action (sizing clamp/round)
   ▼
Humanizer (think time, chat line) → Action
```

### 3.1 Difficulty tiers

| Tier | StrategyCore | Opponent model | Mistake ε | Personality budget |
|---|---|---|---|---|
| Beginner | Heuristic-lite (hand strength only, no bluff balance) | no | 0.25 | unlimited |
| Intermediate | Heuristic full (equity + pot odds + texture bluffs) | no | 0.10 | unlimited |
| Advanced | Heuristic full | yes (stats + type) | 0.03 | unlimited |
| Expert | GTO blueprint (+ search) | yes (safe exploit) | 0 | KL ≤ 0.15 nats |

### 3.2 Personality shaping

Personality params (all 0..1 unless noted): `looseness, aggression, bluff_freq, stickiness, fold_to_pressure, sizing_bias(-1..1), slowplay, tilt_sensitivity, chattiness, think_speed`.

```
π'(a | ctx) ∝ π(a | ctx) · exp( β · w(a, ctx, params) )
```
`w` scores each abstract action, e.g. aggression raises bet/raise weights, looseness raises call/raise weights preflop for weak hands, stickiness lowers fold weight facing bets, bluff_freq raises bet weight when hand strength is low and fold equity is high, sizing_bias shifts mass between small/large sizes. For Expert, β is bisected so KL(π'‖π) ≤ budget.

### 3.3 Tilt

`tilt ∈ [0,1]`, increases on: bad beat (lost with ≥80% equity all-in), losing pot > 40 BB, being bluffed at showdown; scaled by `tilt_sensitivity`; decays ×0.9 per hand. Effective params: `looseness += 0.4·tilt`, `aggression += 0.3·tilt`, `bluff_freq += 0.3·tilt`.

### 3.4 Heuristic core
- Preflop: position-based range charts (UTG..BB, open/3-bet/4-bet/call vs open), stored as JSON 13×13 grids with frequencies.
- Postflop: hand strength bucket via equity vs estimated range (Monte Carlo, phevaluator, Numba, 1–5k samples) + draws; board texture classifier (dry/wet/paired/monotone); decision tables: value bet / bluff / semi-bluff / check-call / check-fold using pot odds, MDF and the `b/(1+2b)` bluff ratio; blocker bonus for nut blockers.

### 3.5 GTO core
- **Card abstraction:** preflop lossless (169); flop/turn/river k-means on equity distributions (EMD for flop/turn, EHS/OCHS for river), default 200 buckets/street; precomputed lookup tables.
- **Action abstraction:** fold, call, {0.33, 0.66, 1.0, 1.5}×pot, all-in; max 3 raises/street.
- **Training:** external-sampling MCCFR with Linear CFR weighting + negative-regret pruning; heads-up first, then 6-max (Pluribus-style). Checkpoints to `artifacts/` as compressed NumPy (regret-free average strategy only for serving).
- **Action translation:** pseudo-harmonic mapping for off-tree bet sizes.
- **Search (stretch):** depth-limited subgame re-solve on turn/river with blueprint leaf values, time-boxed to 1 s.
- **Validation:** same CFR code solves Kuhn & Leduc; exploitability checked against OpenSpiel.
- **Multiway caveat:** no equilibrium guarantee for >2 players; evaluate empirically in arena.

### 3.6 Opponent modeling
Per (bot, opponent) stats with Bayesian priors (Beta) for VPIP, PFR, 3bet, fold-to-cbet, AF, WTSD. Classifier maps stats → {Nit, Rock, TAG, LAG, Maniac, Station, Unknown}. Range narrowing: start from position range, weight combos by likelihood of observed actions. Safe exploitation: blend `π = (1−λ)·π_base + λ·π_BR(model)`, λ grows with sample size, capped (0.3 Expert).

## 4. Backend services
- **TableManager:** asyncio task per table; drives engine; awaits human action with timeout (auto-fold/check); calls bots in a process pool (CPU-bound).
- **WebSocket protocol** (JSON, versioned): server → `table_state`, `hand_started`, `action_required`, `player_acted`, `street_dealt`, `showdown`, `hand_ended`, `chat`; client → `join`, `act {type, amount}`, `sit_out`, `leave`. State messages are per-seat-filtered (same Observation rule).
- **REST:** `/presets`, `/tables` (create with seat configs), `/hands/{id}`, `/sessions/{id}/stats`, `/sim` (launch/job status).
- **Persistence:** SQLite (SQLModel): Player, Session, Table, Hand, HandAction, BotConfig, SimRun.

## 5. Frontend
Lobby (seat picker cards: avatar, personality, difficulty) → Table (oval felt, seats, animated cards/chips, pot, action bar with slider + ⅓/½/⅔/pot/all-in presets, timer, chat bubbles) → History (replay with step controls) → Stats (profit graph, HUD numbers). Zustand store fed by a typed WS client; reconnect with state resync.

## 6. Testing strategy
- Engine: property tests (chip conservation, legal-action correctness, side pots) + golden hand histories.
- Eval: known equity fixtures (AA vs KK ≈ 81.9%).
- Agents: scenario tests (must fold 72o UTG; must value-bet nuts on river), stat-band tests per preset (20k-hand sims, CI-tagged `slow`).
- GTO: Kuhn exploitability → 0, Leduc < 1 mbb/g within budget.
- API: WS contract tests; frontend: Vitest + Playwright happy path.

## 7. Key decisions (ADRs)
1. PokerKit for rules instead of a custom engine — correctness over control.
2. Python + Numba first; Rust only after profiling.
3. Difficulty and personality are orthogonal layers over a shared abstract-action space.
4. Duplicate poker is the default arena mode.
5. Blueprint artifacts are not committed; training is reproducible from configs + seeds.

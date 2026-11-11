# Epics & Stories — Poker Bot Arena

Source docs: `prd.md`, `architecture.md`, `research.md`. MVP = Epics 1–6.

## FR coverage map

| FR | Epic |
|---|---|
| FR1–FR4 | 1 |
| FR5, FR7 | 1, 3 |
| FR6 | 4 |
| FR8 | 7 |
| FR9 | 8 |
| FR10–FR13 | 4 |
| FR14–FR17 | 2 |
| FR18–FR21 | 5, 6 |
| FR22 | 9 |

---

## Epic 1: Foundation & Game Engine
Goal: a correct, fair, deterministic NLHE engine with hand evaluation and equity, exposing information-set observations to agents.

**Delivered (2026-11-11):** All seven stories complete: typed contracts, hand/session execution, filtered observations and showdown rules, secure/seeded shuffles with private audit history, ranking/equity and JSON/generated-text exports. Final recorded backend validation: 362 tests passed, 100% source coverage.

**Retrospective:** [Epic 1 — Foundation & Game Engine](../implementation-artifacts/epic-1-retro-2026-11-11.md).

### Story 1.1: Monorepo scaffold & tooling
As a developer, I want the backend/frontend skeleton with tooling, so that every later story has a consistent base.
**Acceptance Criteria:**
- Given a clean clone, when I run `uv sync && uv run pytest`, then the backend test suite runs green (placeholder test).
- Given the frontend, when I run `pnpm i && pnpm test`, then Vitest passes.
- ruff, mypy (strict on `src/`), pre-commit, and a GitHub Actions CI workflow are configured.
- `docker compose up` starts backend (FastAPI health endpoint) and frontend dev server.

### Story 1.2: Cards, actions and Observation models
As a bot author, I want typed domain models, so that agents and engine share one contract.
**Acceptance Criteria:**
- `Card`, `Street`, `ActionType`, `Action`, `PublicAction`, `Observation`, `PublicEvent` defined as Pydantic models per architecture §2.
- `Agent` Protocol with `decide` and `observe`.
- Serialization round-trips (JSON) are tested.

### Story 1.3: PokerKit engine wrapper (HandRunner)
As the system, I want to run a full NLHE hand through PokerKit, so that rules (min-raise, all-in, side pots) are correct.
**Acceptance Criteria:**
- Given 2–9 seats with stacks/blinds/ante, when agents act, then the hand completes and payouts are returned.
- Property test (hypothesis): total chips are conserved across 10k random hands with random legal actions.
- Illegal actions from an agent are rejected and converted to check/fold with a logged warning.
- Golden tests cover split pot, 3-way all-in with two side pots, and walk (everyone folds to BB).

### Story 1.4: Information-set observation builder
As a fair game, I want each agent to receive only its own information set, so that no bot can cheat.
**Acceptance Criteria:**
- `build_observation(state, seat)` returns legal actions, to_call, min/max raise, pot, history.
- Property test: no opponent hole cards appear anywhere in serialized observations before showdown.
- Showdown `PublicEvent` reveals only cards that were shown per rules.

### Story 1.5: RNG & shuffling
As a player and researcher, I want secure shuffles in play mode and seeded shuffles in sim mode, so that games are fair and reproducible.
**Acceptance Criteria:**
- Play mode uses `secrets.SystemRandom`; sim mode uses `numpy.random.Generator(PCG64(seed))`.
- Given the same seed and action log, a hand replays bit-identically.
- Deck is committed as a SHA-256 hash at hand start and revealed in history (audit trail).

### Story 1.6: Hand evaluator & equity calculator
As a bot, I want fast hand ranking and equity, so that I can reason about hand strength.
**Acceptance Criteria:**
- phevaluator wrapper ranks 5–7 card hands; fixtures for all hand categories.
- Monte Carlo equity hand-vs-hand and hand-vs-range (weighted combos), Numba-accelerated, card-removal aware.
- AA vs KK preflop ≈ 81.9% ±0.5% at 50k samples; ≥ 200k evals/s on one core benchmark.
- Range parser supports notation like `AKs, TT+, A5s-A2s, KQo`.

### Story 1.7: Table session loop & hand history
As the system, I want a table that plays consecutive hands and records them, so that sessions and sims can run.
**Acceptance Criteria:**
- Button rotation, blind posting, bust/rebuy policy (configurable), sitting out.
- Each hand exported as JSON and PokerStars-style text; text parses back to the same action list.
- `observe()` is called on all agents for every public event.

---

## Epic 2: Simulation Arena
Goal: run bots against each other at scale with statistically meaningful results.

### Story 2.1: Baseline agents
As a researcher, I want trivial reference bots, so that I can sanity-check the arena.
**Acceptance Criteria:**
- `RandomAgent`, `CallingStationAgent` (always call/check), `RaiseAgent` (always min-raise/bet pot).
- Each plays 1k hands without errors.

### Story 2.2: Headless arena runner (parallel)
As a researcher, I want to run N hands between configured bots in parallel, so that sims finish fast.
**Acceptance Criteria:**
- `pokerbot sim --config sim.yaml --hands 100000 --workers 8` runs and writes results.
- Process-pool parallelism with deterministic per-worker seeds; ≥ 2,000 hands/s with baseline agents on 8 cores.
- Progress bar and graceful Ctrl-C with partial results saved.

### Story 2.3: Duplicate-deal mode
As a researcher, I want duplicate poker, so that luck variance is reduced.
**Acceptance Criteria:**
- Each deck is replayed with every seat rotation; results aggregated per bot.
- Test: two identical deterministic bots in duplicate mode net exactly 0.
- Measured std-dev of bb/100 is reported vs non-duplicate for comparison.

### Story 2.4: Metrics & reporting
As a researcher, I want standard poker stats with confidence intervals, so that I can compare bots.
**Acceptance Criteria:**
- Per bot: bb/100 ± 95% CI, mbb/hand, VPIP, PFR, 3bet, AF, WTSD, W$SD, fold-to-cbet.
- Outputs: console table, JSON, CSV; optional matplotlib profit curve PNG.

### Story 2.5: Elo/TrueSkill leaderboard
As a researcher, I want a persistent leaderboard of bot configs, so that I can track progress over time.
**Acceptance Criteria:**
- Round-robin tournament command across N configs; ratings persisted in SQLite.
- `pokerbot leaderboard` prints ratings with match counts.

---

## Epic 3: Heuristic Strategy Core (Beginner–Advanced engine)
Goal: a strategically sound rule/equity-based bot that value-bets, bluffs and sizes sensibly.

### Story 3.1: Abstract action space & sizing
As a strategy core, I want a shared abstract action space, so that personalities and cores are interchangeable.
**Acceptance Criteria:**
- Abstract actions {fold, check/call, bet 33/66/100/150% pot, all-in} with mapping to legal concrete amounts (clamp, round to chip unit, min-raise rule).
- `StrategyCore.distribution(obs) -> dict[AbstractAction, float]` interface; sampler with seeded RNG.

### Story 3.2: Preflop range charts
As a bot, I want position-aware preflop ranges, so that I enter pots correctly.
**Acceptance Criteria:**
- JSON 13×13 frequency grids for open (UTG..SB), 3-bet/call vs open by position, 4-bet/call vs 3-bet, BB defense; 6-max and HU sets.
- Scenario tests: folds 72o UTG; opens AKs everywhere; 3-bets AA vs any open.
- Chart loader validates frequencies sum ≤ 1.

### Story 3.3: Board texture & hand classification
As a bot, I want to understand the board and my holding, so that postflop decisions are contextual.
**Acceptance Criteria:**
- Texture classifier: dry/wet, paired, monotone/two-tone, connectedness, high-card.
- Hand classifier: made-hand category, top pair/kicker, overpair, sets; draws (flush, OESD, gutshot, backdoor); nut blockers.
- Fixture tests over ≥ 40 labeled spots.

### Story 3.4: Postflop value & pot-odds logic
As a bot, I want equity-vs-range based decisions, so that I value-bet and call correctly.
**Acceptance Criteria:**
- Estimates villain range from position + action (simple narrowing) and computes equity.
- Calls when equity ≥ pot-odds threshold (+ implied odds for draws); value-bets when equity vs calling range > 55%.
- Scenario tests: bets nuts on river; folds bottom pair to triple barrel from tight range.

### Story 3.5: Bluffing & semi-bluffing engine
As a bot, I want balanced, context-aware bluffs, so that I'm hard to exploit and win pots without the best hand.
**Acceptance Criteria:**
- River bluff frequency targets `b/(1+2b)` of betting range; prefers hands with blockers and no showdown value.
- Semi-bluffs draws on flop/turn; c-bets more on dry boards favoring the preflop raiser.
- Bluff EV estimate uses fold-equity input (default priors, overridable by opponent model).
- Sim test: vs CallingStation bluff rate drops when model input says fold-equity is low (hook for Epic 8).

### Story 3.6: Bet sizing strategy
As a bot, I want texture- and hand-aware sizing, so that value and bluffs are sized well.
**Acceptance Criteria:**
- Small sizes on dry boards, larger on wet/polarized spots; overbets with nuts/air on river (polar).
- Same sizing used for value and bluffs in a given spot (no sizing tells).

### Story 3.7: Heuristic agent assembly & benchmark
As a researcher, I want the full heuristic agent benchmarked, so that we know it's sound.
**Acceptance Criteria:**
- `HeuristicAgent(lite: bool)` wires 3.1–3.6; lite version = hand-strength only (Beginner).
- In 100k duplicate hands: heuristic full beats lite, Random, CallingStation, Raise bots with 95% CI.
- Avg decision time < 50 ms.

---

## Epic 4: Personalities & Difficulty
Goal: distinct, believable bot characters on top of any strategy core, with selectable difficulty.

### Story 4.1: Personality schema & presets
As a player, I want named personalities, so that opponents feel like characters.
**Acceptance Criteria:**
- Pydantic `Personality` with params from architecture §3.2, plus name, avatar, bio, chat line pool.
- 8 presets from PRD §6 in YAML; validated on load.

### Story 4.2: Personality shaper
As a bot, I want my style to skew my action distribution, so that I play like my character.
**Acceptance Criteria:**
- Implements `π' ∝ π·exp(β·w)`; unit tests show aggression increases raise mass, stickiness decreases fold mass, etc.
- KL budget mode: β bisected so KL ≤ budget.

### Story 4.3: Difficulty tiers & agent factory
As a player, I want to pick difficulty, so that challenge matches my skill.
**Acceptance Criteria:**
- `make_agent(difficulty, personality, seed)` builds the pipeline per architecture §3.1 (Expert falls back to Advanced until Epic 7 lands, with a warning).
- Mistake-noise ε per tier applied.
- Arena test: Beginner < Intermediate < Advanced ordering holds in 100k duplicate hands.

### Story 4.4: Preset stat-band calibration
As a designer, I want presets to hit target stats, so that styles are recognizable.
**Acceptance Criteria:**
- `pokerbot calibrate` runs each preset 20k hands in a 6-max mixed table and reports VPIP/PFR/AF vs PRD bands.
- All presets within bands (slow-tagged test); auto-tune script nudges params via coordinate search.

### Story 4.5: Tilt & emotion state
As a player, I want bots to tilt, so that they feel human and exploitable.
**Acceptance Criteria:**
- Tilt triggers/decay per architecture §3.3, driven by `observe()` events.
- Test: Tilt Monkey's VPIP rises above 35 for the 20 hands after a forced bad beat, then decays.
- Tilt state exposed (optionally) to UI.

### Story 4.6: Humanizer — think time & chat
As a player, I want natural timing and banter, so that the table feels alive.
**Acceptance Criteria:**
- Think time from log-normal scaled by spot difficulty and `think_speed` (disabled in sim mode).
- Chat lines triggered on events (big win, bad beat, bluff shown) with `chattiness` probability; no timing tells correlated with hand strength beyond config.

### Story 4.7: Custom personality builder (backend)
As a player, I want to create my own bot personality, so that I can design opponents.
**Acceptance Criteria:**
- CRUD for custom personalities persisted in SQLite; validation of ranges; can be used in tables and sims.

---

## Epic 5: Backend API & Real-time Tables
Goal: serve tables to a human over WebSocket and expose sims/history via REST.

### Story 5.1: Persistence layer
As the system, I want hands, sessions and configs stored, so that history and stats work.
**Acceptance Criteria:**
- SQLModel models: Player(guest), Session, Table, Hand, HandAction, BotConfig, SimRun; Alembic migrations.

### Story 5.2: Table manager & async game loop
As the system, I want each table driven asynchronously, so that humans and bots interleave smoothly.
**Acceptance Criteria:**
- asyncio task per table; bot decisions in a process pool; human action timeout → auto check/fold.
- Supports pause between hands and sit-out.

### Story 5.3: WebSocket protocol
As the frontend, I want a typed real-time protocol, so that the table renders live.
**Acceptance Criteria:**
- Messages per architecture §4, JSON schema versioned; per-seat filtering (no hidden info) contract-tested.
- Reconnect returns full current `table_state`.
- TypeScript types generated from Pydantic schemas.

### Story 5.4: Lobby & table REST API
As a player, I want to create a table with chosen bots, so that I can start a game.
**Acceptance Criteria:**
- `GET /presets`, `POST /tables` with seats: `{difficulty, personality | "random"}`, blinds, stack, seat count.
- `GET /hands/{id}`, `GET /sessions/{id}/stats`.

### Story 5.5: Sim jobs API
As a researcher, I want to launch sims from the API, so that the UI can show results.
**Acceptance Criteria:**
- `POST /sim` enqueues a background job; `GET /sim/{id}` returns status and report JSON.

---

## Epic 6: Frontend — Play UI
Goal: a polished, responsive table to play against bots.

### Story 6.1: App shell, routing, WS client & store
**Acceptance Criteria:**
- Routes: Lobby, Table, History, Stats; Zustand store; typed WS client with auto-reconnect and resync.

### Story 6.2: Lobby & seat configurator
As a player, I want to pick each opponent's difficulty and personality, so that I build my table.
**Acceptance Criteria:**
- Seat cards with avatar, name, style tags, difficulty selector; "randomize table" button; blinds/stack inputs.
- Preset tooltips show style description and expected stats.

### Story 6.3: Poker table rendering
**Acceptance Criteria:**
- Oval table, seats, stacks, dealer button, community cards, pot(s) incl. side pots, animated dealing and chip movement (Framer Motion), 60 fps on a mid laptop; responsive down to tablet.

### Story 6.4: Action controls
As a player, I want clear controls, so that I can act quickly.
**Acceptance Criteria:**
- Fold/check/call/raise buttons, bet slider with ⅓, ½, ⅔, pot, all-in presets, keyboard shortcuts (F/C/R), action timer; only legal actions enabled.

### Story 6.5: Bot presence — chat bubbles, think indicator, tilt badge
**Acceptance Criteria:**
- Chat bubbles, "thinking…" animation during think time, optional tilt badge; showdown reveals with hand name.

### Story 6.6: Hand history & replay
**Acceptance Criteria:**
- List of session hands; replay with step forward/back and auto-play; export text history.

### Story 6.7: Session stats dashboard
**Acceptance Criteria:**
- Profit graph (BB), human VPIP/PFR/AF, per-opponent results; Playwright E2E: create table → play 3 hands → view stats.

---

## Epic 7: GTO Strategy Core (Expert)
Goal: an MCCFR-trained blueprint bot with action translation and optional real-time search.

### Story 7.1: Generic CFR framework validated on Kuhn & Leduc
**Acceptance Criteria:**
- Vanilla CFR, CFR+, Linear CFR, external-sampling MCCFR over a generic game interface.
- Kuhn exploitability < 1e-3; Leduc < 1 mbb/g; numbers cross-checked with OpenSpiel.

### Story 7.2: Card abstraction (bucketing)
**Acceptance Criteria:**
- Preflop 169 classes; flop/turn EMD k-means on equity histograms; river OCHS/EHS; configurable bucket counts (default 200).
- Precomputed lookup tables saved to `artifacts/`; build script reproducible by seed; lookup < 1 µs.

### Story 7.3: NLHE abstract game & MCCFR trainer (heads-up)
**Acceptance Criteria:**
- Abstract game tree with action abstraction per architecture §3.5; external-sampling MCCFR + Linear weighting + regret pruning, Numba-accelerated, multiprocess.
- `pokerbot train --config hu_100bb.yaml` checkpoints; resumable.
- LBR exploitability estimate decreasing across checkpoints (logged).

### Story 7.4: Blueprint serving & action translation
**Acceptance Criteria:**
- Compressed average-strategy store; lookup < 5 ms; pseudo-harmonic mapping for off-tree bets.
- `GTOAgent` passes scenario tests; HU Expert beats Advanced ≥ 20 bb/100 over 200k duplicate hands.

### Story 7.5: 6-max blueprint (Pluribus-style)
**Acceptance Criteria:**
- Multiway training config; 6-max Expert beats a table of Advanced bots with 95% CI.
- Documented compute budget and training time.

### Story 7.6: Depth-limited real-time search (stretch)
**Acceptance Criteria:**
- Turn/river subgame re-solve with blueprint leaf values, 1 s time box; improves HU results vs blueprint-only with CI, or is flagged off.

### Story 7.7: Expert personality integration
**Acceptance Criteria:**
- Personality shaper in KL-budget mode on GTO core; "The Shark" stats within band; Expert+Maniac still beats Advanced.

---

## Epic 8: Opponent Modeling & Exploitation
Goal: bots that learn opponents within a session and exploit them safely.

### Story 8.1: Opponent stats tracker
**Acceptance Criteria:**
- Per-opponent counters with Beta priors (VPIP, PFR, 3bet, fold-to-cbet, AF, WTSD); updated via `observe()`; persisted per session.

### Story 8.2: Player-type classifier
**Acceptance Criteria:**
- Maps stats → {Nit, Rock, TAG, LAG, Maniac, Station, Unknown} with confidence; ≥ 85% accuracy identifying presets after 300 hands in sims.

### Story 8.3: Bayesian range narrowing
**Acceptance Criteria:**
- Combo weights updated by action likelihoods given opponent type; equity computed vs narrowed range; tests show tighter ranges after 3-bet + river raise.

### Story 8.4: Safe exploitation layer
**Acceptance Criteria:**
- Blend `(1−λ)·π_base + λ·π_exploit`, λ by confidence, capped; feeds fold-equity into bluff engine (3.5).
- Advanced-with-modeling beats Advanced-without by > 0 bb/100 vs Station and Maniac presets; doesn't lose vs TAG (CI).

---

## Epic 9: Coach & Analysis (v1.1)
Goal: help the human improve.

### Story 9.1: Post-hand coach
**Acceptance Criteria:**
- For each human decision, show Expert's action distribution and EV deltas; flag top 3 mistakes per session.

### Story 9.2: Equity & odds overlay
**Acceptance Criteria:**
- Toggleable HUD with human equity vs revealed-at-showdown / estimated range, pot odds and MDF.

### Story 9.3: Bot-reasoning explainer
**Acceptance Criteria:**
- After a hand, view a bot's decision trace (hand class, equity, range estimate, personality skew, bluff/value label).

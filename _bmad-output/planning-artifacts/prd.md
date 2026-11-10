# PRD — Poker Bot Arena

Version 1.0 · 2026-11-10 · Status: Draft for implementation

## 1. Product brief

A No-Limit Texas Hold'em platform with strategic AI opponents. Two modes:
1. **Simulation Arena** — bots play each other headlessly at scale to measure strength, tune strategies and research.
2. **Play Mode** — a human sits at a table against bots, choosing difficulty and personalities per seat.

Bots must play strategically: value-bet, bluff and semi-bluff, size bets sensibly, adapt to opponents, and feel like distinct characters.

## 2. Goals & success metrics

| Goal | Metric |
|---|---|
| Strength ordering is real | Each difficulty tier beats the tier below by > 0 bb/100 with 95% CI in 100k duplicate hands |
| Expert is genuinely strong | HU Expert beats Advanced by ≥ 20 bb/100; LBR exploitability trending down per training run |
| Personalities feel distinct | Each preset's VPIP/PFR/AF over 20k hands lands within its target band (see §6) |
| Play feels good | Bot decision latency p95 < 1.5 s (Expert, incl. search) ; UI 60 fps |
| Fair | Zero hidden-information leaks (property-tested); auditable shuffles |

## 3. Users

- **Player** — wants a fun, challenging game, picks opponents.
- **Researcher/Developer (you)** — runs tournaments between bot configs, tunes parameters, trains blueprints.

## 4. Functional requirements

### Engine
- FR1 Support NLHE cash games, 2–9 seats, configurable blinds/ante/stacks.
- FR2 Correct betting rules, min-raise, all-in, side pots, split pots, showdown order.
- FR3 Cryptographically secure shuffle in play mode; seedable RNG in sim mode.
- FR4 Full hand history recording (PokerStars-like text + JSON).

### Bots
- FR5 Common `Agent` interface receiving only the agent's information set.
- FR6 Four difficulty tiers: Beginner, Intermediate, Advanced, Expert.
- FR7 Heuristic strategy: position-aware preflop ranges, postflop hand-strength + equity + pot odds, board-texture-aware bluffing/semi-bluffing, sizing.
- FR8 GTO strategy: MCCFR-trained blueprint with card/action abstraction and action translation; optional depth-limited real-time search.
- FR9 Opponent modeling: per-opponent stats, player-type classification, Bayesian range narrowing, safe exploitation.
- FR10 Personality layer: parameterized style (looseness, aggression, bluff frequency, stickiness, tilt, sizing bias, slowplay) applied to any strategy core.
- FR11 ≥ 8 personality presets with names/avatars and custom personality editor.
- FR12 Tilt/emotion state that evolves with results.
- FR13 Humanization: variable think time, optional table chat lines tied to personality.

### Simulation
- FR14 Headless arena: run N hands between any configs, parallelized.
- FR15 Duplicate-deal mode for variance reduction.
- FR16 Reports: bb/100 with CI, VPIP/PFR/AF/WTSD per bot, Elo leaderboard, CSV/JSON export.
- FR17 CLI and API to launch sims.

### Play mode
- FR18 Lobby: choose seats, difficulty and personality per bot (or "random"), blinds, stack.
- FR19 Real-time table over WebSocket with action controls (fold/check/call/bet slider/presets/all-in).
- FR20 Hand history viewer and replay.
- FR21 Session stats (profit graph, VPIP/PFR for the human).
- FR22 (Stretch) Coach mode: after a hand, show what the Expert bot would have done and equities.

## 5. Non-functional requirements
- NFR1 Bots never access hidden info (engine-enforced, property tests).
- NFR2 Sim throughput ≥ 2,000 hands/s for heuristic bots on 8 cores.
- NFR3 Blueprint lookup < 5 ms; Expert search < 1.5 s p95.
- NFR4 Deterministic replays given seed + action log.
- NFR5 Test coverage ≥ 85% on engine & strategy packages.
- NFR6 Runs locally with one `docker compose up`.

## 6. Personality presets (target stat bands, 6-max)

| Preset | Style | VPIP | PFR | AF | Notes |
|---|---|---|---|---|---|
| The Rock | Tight-passive | 10–15 | 7–11 | 1.5–2.5 | Rarely bluffs |
| TAG Pro | Tight-aggressive | 18–24 | 15–20 | 2.5–3.5 | Solid baseline |
| LAG Hustler | Loose-aggressive | 28–35 | 22–28 | 3–4.5 | Frequent 3-bets, barrels |
| Maniac | Hyper-aggressive | 45–65 | 30–45 | 4–7 | Overbets, bluffs a lot |
| Calling Station | Loose-passive | 40–55 | 5–10 | 0.5–1 | Calls down light |
| Nit | Ultra-tight | 7–11 | 5–9 | 1.5–2.5 | Folds to pressure |
| Tilt Monkey | TAG that tilts | 18–24 → 35+ on tilt | — | — | Emotion-driven |
| The Shark | Balanced (Expert) | 22–27 | 18–23 | 2.5–3.5 | Near-GTO + exploits |

## 7. Out of scope (v1)
Real-money play, online multiplayer between humans, tournaments (MTT/ICM), non-NLHE variants (PokerKit makes them a later add).

## 8. Release plan
- **MVP (Epics 1–6):** engine, arena, heuristic bots, personalities, API, UI → playable vs Beginner–Advanced.
- **v1.0 (Epics 7–8):** GTO Expert, opponent modeling.
- **v1.1 (Epic 9):** coach & analysis.

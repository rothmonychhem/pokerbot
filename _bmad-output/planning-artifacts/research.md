# Research — Poker AI Bot (No-Limit Texas Hold'em)

Date: 2026-11-10

## 1. State of the art (what actually works)

| System | Year | Game | Core technique | Takeaway for us |
|---|---|---|---|---|
| CFR / CFR+ (Zinkevich, Tammelin) | 2007/2014 | Any imperfect-info game | Iterative regret minimization → converges to Nash equilibrium (2-player zero-sum) | The foundation. Average strategy = GTO. |
| MCCFR (external / outcome sampling) | 2009 | Large games | Samples parts of the tree per iteration | Only practical way to train NLHE on a single machine. |
| Linear / Discounted CFR | 2019 | — | Weight later iterations more | 2–10× faster convergence; free win. |
| DeepStack | 2017 | HU NLHE | Depth-limited re-solving + learned value net | Real-time search beats a fixed blueprint. |
| Libratus | 2017 | HU NLHE | Blueprint (MCCFR) + nested subgame solving + self-improvement | Blueprint + search is the winning recipe. |
| Pluribus | 2019 | 6-max NLHE | MCCFR blueprint (8 days, 64 cores) + depth-limited search; no equilibrium guarantee multiway but works empirically | Multiway is feasible with the same machinery; compute is modest. |
| ReBeL | 2020 | HU NLHE | RL + search over public belief states | Elegant, but heavy (GPU, NN training). Out of scope for v1. |
| Embedding/learned abstractions (AAAI 2026), parallel CFR preprints (2026) | 2026 | HU NLHE | Better info-set abstraction, faster solving | Optional upgrades for Epic 7 later. |
| "Beyond GTO" profit-maximizing agents (arXiv 2509.23747) | 2025 | NLHE | Exploit opponents rather than play pure equilibrium | Supports our Epic 8 (safe exploitation). |

**Key insight:** GTO bots *bluff automatically* — the equilibrium strategy contains the correct bluff frequency at every node. Heuristic bots need bluffing *designed in* (balanced bluff:value ratio by bet size, fold-equity estimate, blockers, scare cards).

## 2. Bluffing & sizing theory used by heuristic bots

- Pot odds for caller facing bet `b` (as fraction of pot): needs equity ≥ `b / (1 + 2b)`.
- Optimal bluff share of a river betting range for bet `b`: `b / (1 + 2b)` (e.g. pot-size bet → 1/3 bluffs, ½-pot → 1/4).
- Minimum defense frequency (MDF): `1 / (1 + b)`.
- Semi-bluffs: prefer draws (flush/OESD) and hands with blockers to the nuts.
- Fold equity estimate: `FE = P(opponent folds | bet size, opponent model)` — from stats (fold-to-cbet, fold-to-river-bet).
- Bluff EV: `FE·pot − (1−FE)·bet + (1−FE)·equity·(pot+2·bet)`.

## 3. Open-source building blocks (verified)

| Need | Choice | Why |
|---|---|---|
| Rules engine (betting, side pots, showdown, variants) | **PokerKit** (U. Toronto CPRG, MIT, Python ≥3.11, IEEE ToG paper) | Battle-tested, fine-grained state machine, NLHE built in. Don't write your own side-pot logic. |
| Hand evaluation | **phevaluator** (perfect hash, Apache-2.0, 5–7 cards) | Much faster than pure-Python `treys`; needed for Monte Carlo equity. |
| CFR validation | **OpenSpiel** (DeepMind) | Kuhn/Leduc + exploitability calculators to unit-test our CFR before scaling up. |
| Reference implementations | slumbot2019 (C++ CFR/MCCFR), robopoker (Rust MCCFR, Pluribus-parity goal), PokerRL | Read for abstraction & action-translation tricks. |

## 4. Recommended stack

- **Backend:** Python 3.12, FastAPI + WebSockets, Pydantic v2, PokerKit, phevaluator, NumPy + Numba (hot loops), SQLite via SQLModel (Postgres-ready).
- **Training:** Offline MCCFR (Linear CFR weighting) in Python+Numba first; port hot loop to Rust (PyO3) only if profiling says so.
- **Frontend:** React + TypeScript + Vite, Tailwind, Zustand, Framer Motion for card/chip animation.
- **Tooling:** uv (Python deps), pnpm, pytest + hypothesis (property tests on engine invariants), ruff, mypy, Vitest, Playwright, Docker Compose.

Why Python and not all-Rust: fastest path to a playable product, PokerKit/OpenSpiel ecosystem, and the only truly hot path (MCCFR + equity) can be accelerated in isolation.

## 5. Difficulty vs personality — two orthogonal axes

- **Difficulty = skill** (which strategy core + how much noise/mistakes).
- **Personality = style** (how the strategy distribution is skewed: tight/loose, passive/aggressive, bluff-happy, sticky, tilt-prone).
- Expert bots keep personality within a bounded deviation (KL budget) from the blueprint so they stay strong but still feel distinct.

## 6. Evaluation methodology

- Metrics: bb/100, mbb/hand, VPIP, PFR, AF, WTSD, W$SD.
- Variance reduction: **duplicate poker** (replay the same deck with seats swapped) — mandatory; NLHE variance makes 10k hands meaningless otherwise. AIVAT later.
- Exploitability: exact on Kuhn/Leduc; local best-response (LBR) estimate on NLHE.
- Leaderboard: Elo/TrueSkill across bot configs; target ordering Beginner < Intermediate < Advanced < Expert with 95% CI separation.

## 7. Scope / ethics note

This project is for offline play, simulation and learning. Running bots on real-money sites violates their terms of service and is out of scope.

## Sources

- https://pypi.org/project/pokerkit/ · https://arxiv.org/pdf/2308.07327v6.pdf · https://pokerkit.readthedocs.io/en/0.6/simulation.html
- https://www.github.com/HenryRLee/PokerHandEvaluator · https://pypi.org/project/phevaluator · https://github.com/ihendley/treys
- https://github.com/ericgjackson/slumbot2019 · https://backiee.wasmer.app/http_github_com/krukah/robopoker · https://github.com/ivng8/PokerAI
- https://arxiv.org/pdf/2509.23747 · https://ojs.aaai.org/index.php/AAAI/article/view/38736/42698 · https://arxiv.org/pdf/2605.19928
- https://backiee.wasmer.app/http_github_com/PokerBotAI/awesome-poker-ai

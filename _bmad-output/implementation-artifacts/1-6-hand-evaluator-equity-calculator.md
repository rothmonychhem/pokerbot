---
baseline_commit: cebf883ef07b0682acb44f02aa8a0b6a101e04e6
---

# Story 1.6: Hand evaluator & equity calculator

Status: done

## Story

As a bot, I want fast hand ranking and equity, so that I can reason about hand strength.

## Acceptance Criteria

1. A phevaluator wrapper ranks 5–7 distinct domain Cards; smaller rank is stronger (1–7462). Fixtures cover every category, best-five selection and wheel straights; reject wrong counts and duplicates.
2. Monte Carlo heads-up equity supports a fixed opponent hand or weighted concrete two-card combos and a known board of 0, 3, 4 or 5 cards. Sample combos proportional to positive finite weights after removing hero/board blockers; sample the missing board uniformly without replacement, excluding both hands. Wins count 1 and ties 0.5. Numba accelerates the sampling/evaluation loop. No global RNG state; explicit non-negative integer seed yields repeatable results.
3. AA vs KK preflop equity is 0.819 ± 0.005 at 50,000 samples with a fixed seed. A reproducible, warmed, single-core benchmark demonstrates at least 200,000 seven-card evaluations per second; disclose conversion/JIT boundaries and machine environment.
4. `parse_range` supports comma-separated classes, `AKs`, `KQo`, bare nonpairs (both suited/offsuit), pairs, `TT+`, `A5s-A2s`, and concrete `AsKd` combos. Expand to canonical distinct combos; overlapping tokens deduplicate with weight 1. Weighted combos are supplied through the equity API, not invented range syntax. Reject malformed input. Fixed-first-rank nonpair `+` and intervals mean varying second rank; pairs vary their paired rank.
5. Existing backend tests pass; preserve secure shuffle and replay behavior. Add deterministic correctness, blocker/weight/tie/input validation tests and a focused review. Coverage remains 100% for Python code, with Numba kernels also exercised compiled and via `.py_func` to obtain meaningful branch coverage.

## Tasks / Subtasks

- [x] Task 1: Add specified phevaluator and Numba dependencies, build typed ranking wrapper and compiled batch evaluation; validate against library fixtures and random hands (AC 1, 3).
- [x] Task 2: Implement range expansion and weighted combo model; test counts, overlaps, suit variants, intervals and invalid notation/weights (AC 2, 4).
- [x] Task 3: Implement hand-vs-hand and weighted-range equity with local PCG64 RNG, blocker filtering, partial Fisher–Yates runouts and tie shares; test boundary states and seeded sampling (AC 2, 3).
- [x] Task 4: Add documented warmed single-core benchmark and usage, run 50k accuracy fixture, regression/coverage/type/lint checks and focused review (AC 3, 5).

## Dev Notes

- Architecture §§1, 3.4, 6: put evaluator, equity and ranges under `backend/src/pokerbot/eval/`; package currently only has a docstring. Reuse immutable `Card`, `parse_cards`, `full_deck`. Card IDs follow phevaluator: `(rank-2)*4 + suit_index(c,d,h,s)`.
- Keep evaluation outside the engine and observations. This story does not implement multiway equity, range inference, session loops or UI.
- Dependencies expressly specified by source story are authorized. Current Python 3.14 / NumPy 2.5.4 are supported by Numba 0.67; phevaluator 0.6 ships a native evaluator. Constrain versions to tested minor releases and lock them.
- Prefer native PH evaluator calls from Numba using ctypes to avoid reimplementing poker ranking or copying upstream tables. Check symbol availability on this environment. The native extension handle must remain alive; compile kernels without persistent caching of native addresses. Document native ABI dependency and verify installed version in CI through tests.
- Equity must normalize finite weights safely (scale before sum), reject negative/nonfinite/all-zero or wholly blocked ranges, invalid hero/board/sample/seed inputs. Zero-weight combos are excluded. Validate duplicate hole cards even in zero-weight combos. A live combo must contain two distinct cards. Reversed duplicate combo weights are combined rather than sampled twice accidentally.
- Public API: `rank_hand(cards) -> int`, `rank_hands(hands) -> NDArray[int64]`, `WeightedCombo(cards: tuple[Card, Card], weight: float = 1.0)`, `parse_range(text) -> tuple[WeightedCombo,...]`, `equity_vs_hand(hero, villain, board=(), *, samples=..., seed=...) -> float`, `equity_vs_range(hero, combos, board=(), *, samples=..., seed=...) -> float`. Strict boundary validation before native calls is required (native evaluator trusts IDs).
- Range grammar assumptions: plus for pairs means up through AA; `ATs+` means ATs/AJs/AQs/AKs; pair intervals are inclusive in either direction; nonpair intervals require same first rank and suitedness. Ranks must be in high/low order. Concrete combo input is case-sensitive standard domain notation. WeightedCombo must validate and freeze its input.
- Previous story 1.5 added local Generator(PCG64(seed)), locked NumPy, default coverage 100%, strict mypy and audited shuffles. Seed reproducibility requires locked dependencies. Do not alter global NumPy/random state.
- Read existing pyproject/README before modifying them; preserve all existing dependencies, commands and RNG docs. Backend files are untracked against sole setup commit, so report only this story's changes.
- No AGENTS.md or project-context.md found.

### References

- `_bmad-output/planning-artifacts/epics.md` Story 1.6.
- `_bmad-output/planning-artifacts/architecture.md` §§1, 3.4, 6.
- `_bmad-output/implementation-artifacts/1-5-rng-shuffling.md`.
- https://github.com/HenryRLee/PokerHandEvaluator (installed 0.6.0 native evaluator source inspected).
- https://github.com/numba/numba/blob/main/docs/source/release/0.67.0-notes.rst

## Dev Agent Record

### Agent Model Used

GPT-6 Codex

### Debug Log References

- Red/green: missing evaluator/equity/ranges modules confirmed before implementation; new focused suite 83 passed.
- Accuracy fixture initially used AsAh vs KsKh (same suits, ~82.8%). Corrected fixture to average all six KK suit combos and separately test AsAh vs KcKh. Fixed seed 42 at 50k samples returns 0.82236 for the range, within 0.819 ± 0.005. Suit blockers explain the difference; no seed tuning.
- Full default suite: 297 passed, 1 slow test deselected; 100% coverage, including Python execution of Numba kernel bodies and compiled-path checks. Ruff and strict mypy (30 source files) passed; lockfile check passed.
- Benchmark (macOS 26.6.2 arm64, Python 3.14.6, NumPy 2.5.4, Numba 0.67.0, phevaluator 0.6.0): 27,682,140 encoded seven-card evals/s; public batch including validation/encoding 538,191 evals/s. JIT and object preparation excluded; one thread, 200k encoded / 10k public hands. 50k equity samples in 0.0185s after warmup.

### Completion Notes List

- Implemented typed PH ranking wrappers and compiled batch ranking via pinned native ABI; no hand-ranking rules reimplemented.
- Implemented deterministic range grammar and frozen weighted combos, with zero/invalid weight handling and canonical duplicate semantics.
- Added Numba sampling/equity loop with local PCG64, blocker filtering, safe finite weight normalization, uniform runouts and tie shares. All inputs validated before native evaluation.
- Added package exports, usage and benchmark documentation. New dependencies are those explicitly specified by the story.

- Source requirements and current package inspected; assumptions and API boundaries recorded.

### File List

- backend/pyproject.toml
- backend/uv.lock
- backend/README.md
- backend/src/pokerbot/eval/__init__.py
- backend/src/pokerbot/eval/evaluator.py (new)
- backend/src/pokerbot/eval/equity.py (new)
- backend/src/pokerbot/eval/ranges.py (new)
- backend/tests/eval/__init__.py (new)
- backend/tests/eval/test_evaluator.py (new)
- backend/tests/eval/test_equity.py (new)
- backend/tests/eval/test_ranges.py (new)
- backend/scripts/benchmark_eval.py (new)
- _bmad-output/implementation-artifacts/1-6-hand-evaluator-equity-calculator.md (new)
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-11-10: Created story context for next pending epic 1 story.

- 2026-11-10: Implementation, accuracy, performance and regression checks completed; status → review.

## Focused Review (2026-11-10)

- Edge Case Hunter: one concrete patch finding, no deferred issues.
- [x] [Review][Patch] Add an explicit 0–51 card-ID bounds check before all native evaluation. Ordinary Cards validate ranks, but a caller using `Card.model_construct` can bypass that validation; native table lookups must remain safe. Regression tests cover negative, oversized and extremely large rank values through both ranking APIs.
- Isolated Python 3.12.15 validation: all 83 eval tests passed before the bounds-only review patch; compiled ABI and sampling paths work on the CI Python version.
- Repeated warmed benchmark: 31,046,460 encoded evals/s and 506,493 public batch evals/s; both exceed 200k. Fixed checksum 818264973; AA-vs-KK equity unchanged at 0.82236.
- Review scope limited to the new eval package, its tests, dependency changes and benchmark; the untracked scaffold was not treated as this story's diff.

- Final validation after bounds patch: 300 default tests passed, 1 slow test deselected; 100% source coverage. Ruff, format checks and strict mypy passed. Final benchmark: 26,818,340 encoded / 412,254 public batch evals/s; 50k equity samples in 0.0183s, unchanged equity 0.82236. All tasks and review patches resolved; status → done.

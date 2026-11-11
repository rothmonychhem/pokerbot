---
baseline_commit: cebf883ef07b0682acb44f02aa8a0b6a101e04e6
---

# Story 2.1: Baseline agents

Status: done

## Story

As a researcher, I want trivial reference bots, so that I can sanity-check the arena.

## Acceptance Criteria

1. `RandomAgent`, `CallingStationAgent` and `RaiseAgent` implement the existing Agent protocol and are importable from `pokerbot.agents` and `pokerbot.agents.baselines`.
2. RandomAgent samples legal action types uniformly and, for bet/raise, an integer uniformly inside inclusive min/max raise-to bounds. Each instance owns a local `random.Random` stream, optionally seeded by a nonnegative integer (bool/noninteger/negative rejected). Equal seed and observation sequence yields equal decisions; instances, deck RNG and global random state stay independent. Python's arbitrary-size chip integers remain supported.
3. CallingStationAgent chooses check when legal, otherwise call. RaiseAgent chooses minimum legal raise when available, otherwise a pot-sized opening bet clamped to min/max. If aggression is unavailable it checks/calls. For unusual validated views without check/call, both choose fold when available; a view offering only aggression uses its minimum legal amount. No agent returns an action outside `legal_actions`.
4. All three accept public events via a no-op observe method, retain no event/history/private engine references, and use only the supplied Observation. They are reference policies, not strategic difficulty/personality agents.
5. Each plays 1,000 complete hands without agent exceptions or illegal-action fallback. A seeded mixed-lineup test seats all three on every hand, varies 3–9 seats/stacks/blinds/antes/button, and asserts no illegal actions and chip conservation. Mark this longer workload slow, run it explicitly for acceptance; default tests cover policy branches, legal boundaries, repeatability and TableSession integration.
6. Existing regressions pass and source coverage remains 100%. No new dependencies or changes to engine contracts. Document policy semantics and replay scope.

## Tasks / Subtasks

- [x] Task 1: Add baseline module, shared legal fallback, package exports and unit tests for policies, bounds, seeds and stateless event observation (AC 1–4).
- [x] Task 2: Add default real-session integration and explicit 1,000-hand mixed-lineup acceptance test; verify no fallback, exceptions or chip loss (AC 5).
- [x] Task 3: Document baseline behavior and RNG scope; run default regressions/coverage/lint/types plus targeted slow acceptance, then focused review (AC 6).

## Dev Notes

- Architecture §§1–2 places bots in `backend/src/pokerbot/agents/`; base.py already defines runtime-checkable Agent with decide/observe. Current __init__.py is docstring-only: extend exports without altering the protocol.
- Existing test-only RecordingAgent/RandomLegalAgent in tests/engine/helpers.py demonstrate legal-action use but are not production agents. New baselines must not import test helpers; tests may reuse helpers/configs.
- Domain actions use bet/raise street-total sizing. CALL should be `Action.call()` with no amount (public call events instead record street totals). `Observation.pot` already includes live bets; opening pot bet means clamp that field, no extra to_call adjustment. Legal RAISE takes precedence over BET (the model forbids both together).
- No strategy range/equity/personality work, factory registry, arena workers/CLI or metrics in this story; those belong to later stories.
- Use stdlib random.Random per baseline instance for arbitrary-size inclusive randint. This agent-decision RNG is distinct from secure/PCG64 deck RNG implemented in epic 1. Record seed-repeatability within the same locked Python environment; no cross-Python-version policy-stream promise.
- Validated Observation can expose a fold-only or aggression-only set; handle these safely rather than rely on runner fallback. No defensive public input parser is needed for bypassed-invalid Observation models.
- Prior epic delivered TableSession with physical observations and private history. Its retrospective requires filtered observations and deliberate physical seat semantics; baseline code only consumes observed legal actions/pot/bounds and ignores observe events.
- Prior suite: 362 default tests, 100% coverage. Mixed-lineup slow workload should inspect result.illegal_actions and logs, since runner intentionally swallows faulty agent exceptions. Use independent seeded agents/decks and positive starting stacks for every hand so each baseline participates 1,000 times.
- No AGENTS.md or project-context.md found. Backend/scaffold remain untracked against sole setup commit; do not stage unrelated files. No new dependency/API research required: stdlib APIs and current local contracts suffice.

### References

- `_bmad-output/planning-artifacts/epics.md`, Epic 2 / Story 2.1.
- `_bmad-output/planning-artifacts/architecture.md`, §§1–2.
- `_bmad-output/implementation-artifacts/epic-1-retro-2026-11-11.md`, risks/actions/readiness.
- `backend/src/pokerbot/agents/base.py`, domain actions/observation, engine/table.py.

## Dev Agent Record

### Agent Model Used

GPT-6 Codex

### Debug Log References

- Red: new baseline tests initially failed import because package exports did not exist. Green: all 24 default policy/integration tests pass, baseline module coverage 100%.
- Explicit acceptance: `uv run pytest tests/agents/test_baselines.py -m slow` passed (1,000 mixed-lineup hands; each of the three baseline agents participates on every hand), no warning/error logs or illegal-action records, chip conservation checked for each hand; 6.97s on this environment.
- Default full suite: 386 passed, 2 slow tests deselected; 100% source coverage. Ruff and formatting checks pass; strict mypy clean across 33 source files.

### Completion Notes List

- Added legal-action RandomAgent, CallingStationAgent and RaiseAgent plus package exports; no engine changes or dependencies.
- Added explicit conservative fallbacks for restricted legal-action sets; pot opening bets clamp to bounds and raises use minimum totals, including short all-ins.
- RandomAgent owns a seeded stdlib RNG with arbitrary-size integer sizing; unit tests verify replay, per-instance/global independence, inclusive bounds and seed validation.
- Documented reference-policy scope, RNG separation, session use and the slow acceptance command. Public events are not retained.

- Context checked against source ACs and existing legal-action/session contracts; policy fallback and RNG assumptions recorded.

### File List

- backend/src/pokerbot/agents/baselines.py (new)
- backend/src/pokerbot/agents/__init__.py
- backend/tests/agents/__init__.py (new)
- backend/tests/agents/test_baselines.py (new)
- backend/README.md
- _bmad-output/implementation-artifacts/2-1-baseline-agents.md (new)
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-11-11: Created context for first epic 2 story.

- 2026-11-11: Implementation, 1,000-hand acceptance and regression checks complete; status → review.

## Focused Review (2026-11-11)

- Edge Case Hunter: no concrete actionable findings; no deferred issues.
- Scope limited to new baseline policies, exports, tests and directly affected action/observation contracts. No broad review of the untracked scaffold.
- Verified legal fallbacks, clamped pot bets, minimum raises, seeded random bounds and independence, no-op event observation and explicit 1,000-hand acceptance coverage.
- Final validation: 386 default tests passed, two slow tests deselected, 100% source coverage; targeted slow baseline test passed separately (each reference baseline on all 1,000 hands), no warnings/errors/illegal actions or chip loss. Ruff, touched-file formatting and strict mypy passed.
- All tasks and acceptance criteria complete. Status → done.

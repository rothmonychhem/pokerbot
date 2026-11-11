---
baseline_commit: cebf883ef07b0682acb44f02aa8a0b6a101e04e6
---

# Story 1.5: RNG & shuffling

Status: done

## Story

As a player and researcher, I want secure shuffles in play mode and seeded shuffles in sim mode, so that games are fair and reproducible.

## Acceptance Criteria

1. `shuffled_deck(mode="play")` uses `secrets.SystemRandom`; `shuffled_deck(mode="sim", seed=...)` uses `numpy.random.Generator(PCG64(seed))`. Both return a permutation of all 52 domain cards. Sim requires a non-negative integer seed; play rejects a seed; invalid modes fail explicitly.
2. Given the same seed, configuration and effective action log, the complete hand result serializes byte-for-byte identically. Verify replay from both a regenerated seeded deck and the saved deck. Reproducibility from seed is within the locked NumPy environment; saved deck order is the durable replay input.
3. Every hand's first `HandStarted` carries a SHA-256 deck commitment before actions/dealing. Completed private `HandResult` includes the full initial deck order and matching commitment as an audit record. Canonical bytes are the concatenated two-character card codes in draw order, ASCII encoded. Reordering or replacing a card invalidates verification.
4. Deck order and simulation seed never enter observations or public events; only the commitment is broadcast. Keep showdown reveal rules unchanged. Audit JSON round-trips and validates its commitment.
5. Existing explicitly supplied decks remain supported, including valid partial decks accepted by HandRunner. Omitting a deck securely shuffles by default; sim is explicit. Invalid or ambiguous deck/mode/seed combinations fail before agents are notified. Existing regressions pass and default coverage remains 100%.

## Tasks / Subtasks

- [x] Task 1: Add specified NumPy dependency and `engine/rng.py` with secure/seeded shuffles and canonical deck commitment helper; test determinism, permutations, backend selection, input validation and tamper detection (AC 1, 3).
- [x] Task 2: Extend `HandStarted` with optional validated commitment for backwards model compatibility; add private `DeckAudit` and optional audit on legacy `HandResult` (always populated by runner); validate deck uniqueness and hash (AC 3, 4).
- [x] Task 3: Integrate optional deck generation into `run_hand`, snapshot the deck before callbacks, emit its commitment first, retain initial order only in completed private history; preserve explicit decks and reject ambiguous options (AC 3–5).
- [x] Task 4: Add replay and privacy integration tests using recorded effective actions, including a multiway side pot; document usage, hash encoding and replay environment requirements; run regression, coverage, ruff and mypy (AC 2–5).

## Dev Notes

- Architecture §1 places RNG under `backend/src/pokerbot/engine/`. Reuse `full_deck`, frozen domain models and the existing engine; no new dealing rules.
- Current `run_hand(config, agents, deck)` requires an explicit deck. `_HandDriver` already copies it and enforces unique cards / at least `2*n + 8`. Add keyword-only mode/seed while preserving positional deck compatibility. Reject sim/seed alongside an explicit deck rather than silently ignoring them.
- `HandStarted` currently has table metadata only. Add optional hash with a lowercase 64-hex pattern; never put the deck in `HandEnded` or another public event. `HandResult` is already private and includes all hole cards, so is the correct history boundary for the revealed deck. Story 1.7 owns history export and session policies.
- `HandResult` and `HandStarted` are constructed directly in existing model tests: additive optional fields preserve compatibility; runner always sets both audit and commitment.
- Story 1.4 established explicit showdown rules, frozen observations, JSON/Python dump privacy checks. Its regex currently matches card-like substrings inside arbitrary strings; update it to match card tokens rather than accidental pairs inside hash metadata, and guard both real-card detection and digest handling.
- No RNG singleton or module-global seeding. Use fresh Generator(PCG64(seed)) per seeded deck; NumPy is explicitly specified by the epic and authorized in this scope.
- NumPy Generator does not promise version compatibility: retain the deck in audit history and use `uv.lock` for seed replay. Do not claim seed portability across versions. Secure play must never fall back to seeded random.
- Codebase files are untracked against the sole setup commit; record targeted file changes rather than staging unrelated work.
- No project-context.md or AGENTS.md found. No frontend or UX changes needed.

### References

- `_bmad-output/planning-artifacts/epics.md`, Story 1.5 and Epic 1.
- `_bmad-output/planning-artifacts/architecture.md`, §§1, 2, 6.
- `_bmad-output/implementation-artifacts/1-4-information-set-observation-builder.md`.
- https://numpy.org/doc/stable/reference/random/generator.html
- https://numpy.org/doc/2.0/reference/random/compatibility.html
- https://docs.python.org/3/library/secrets.html

## Dev Agent Record

### Agent Model Used

GPT-6 Codex

### Debug Log References

- Red/green: RNG tests first failed on missing module, audit tests on missing model, runner tests on missing mode/audit; each phase then passed.
- Validation: 213 default tests passed, one slow test deselected, 100% source coverage. Ruff, strict mypy (27 files), and `uv lock --check` passed.

### Completion Notes List

- Added secure default and explicit PCG64 seeded deck generation; no shared RNG state. NumPy 2.5.4 is locked.
- Added public SHA-256 commitment and private validated initial-deck audit, preserving explicitly supplied fixture decks and legacy model construction.
- Replay tests compare complete JSON bytes using both seeded regeneration and saved decks; side pots, callback mutation, invalid options and privacy regression checks pass.
- Updated card leak scanner to recognize standalone card tokens, avoiding hash-substring false positives while checking actual serialized cards.

- Story context validated against source ACs and current models/runner; assumptions and compatibility boundaries documented.

### File List

- backend/pyproject.toml
- backend/uv.lock
- backend/README.md
- backend/src/pokerbot/engine/rng.py (new)
- backend/src/pokerbot/engine/models.py
- backend/src/pokerbot/engine/hand_runner.py
- backend/src/pokerbot/domain/events.py
- backend/tests/engine/test_rng.py (new)
- backend/tests/engine/test_deck_audit.py (new)
- backend/tests/engine/test_shuffle_runner.py (new)
- backend/tests/engine/test_observation.py
- _bmad-output/implementation-artifacts/1-5-rng-shuffling.md (new)
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-11-10: Created story context for the next pending epic 1 story.

- 2026-11-10: Implementation and regression validation complete; status → review.

## Focused Review (2026-11-10)

- Edge Case Hunter: one concrete patch finding, no deferred issues.
- [x] [Review][Patch] Cross-check the private audit commitment against the first public `HandStarted` event when validating completed history. Previously an independently valid replacement audit could contradict the broadcast commitment. Histories with audits now reject missing start events, missing start hashes, and mismatched hashes.
- Regression test confirmed the original gap before the fix and passes after it. Closest audit/replay suite: 18 passed. Ruff and mypy passed.
- Scope: active story's new files and additive changes in runner, events, models and privacy tests; no broad review of the untracked scaffold.

- Final validation after review fix: 214 passed, 1 slow test deselected; 100% coverage. All tasks and review patches resolved. Status → done.

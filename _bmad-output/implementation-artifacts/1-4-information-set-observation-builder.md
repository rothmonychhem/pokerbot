---
baseline_commit: cebf883
---

# Story 1.4: Information-set observation builder

Status: done

## Story

As a fair game,
I want each agent to receive only its own information set,
so that no bot can cheat.

## Acceptance Criteria

1. `build_observation(state, seat)` takes a read-only hand snapshot (`HandView`: PokerKit state, `HandConfig`, dealt hole cards, board and public history) and the acting seat. It returns an `Observation` with legal actions, `to_call`, min/max raise, pot, stacks and public action history. It reads only the hole cards of `seat`. It raises `EngineError` if `seat` is not the current actor or has not been dealt two cards.
2. Property test (hypothesis, 2–9 seats, random stacks/blinds/antes, random legal and illegal agents): no opponent hole card appears anywhere in any serialized observation (JSON and Python dumps), or in any public event an agent receives before the first `ShowdownRevealed`.
3. Showdown reveal rules live in the engine (`engine/showdown.py`), not in an implicit PokerKit default:
   - an uncontested pot (everyone else folded) reveals nothing;
   - in an all-in situation (at most one live player still has chips, so no more betting was possible), every live hand is revealed, before the remaining board is dealt if the all-in happened before the river;
   - otherwise, players show in PokerKit's showdown order (last aggressor first, else first live seat after the button). A player shows only if their hand can still win or tie at least one pot they are eligible for. Otherwise they muck;
   - folded hands are never revealed.
4. Every `ShowdownRevealed` event carries exactly the seat's dealt hole cards, only for a live seat, at most once per seat.
5. Existing behavior and tests from stories 1.2 and 1.3 still pass. The default suite stays at 100% coverage.

## Tasks / Subtasks

- [x] Task 1: `EngineError` to `engine/errors.py`, re-exported from `hand_runner` (AC: 1, 5)
- [x] Task 2: `HandView` and `build_observation(view, seat)` in `engine/observation.py` (AC: 1)
  - [x] 2.1 Frozen dataclass `HandView(state, config, hole_cards: Mapping[int, Sequence[Card]], board, history)` with a `street` property
  - [x] 2.2 Validate seat == actor (mapped via `seat_of`) and two hole cards dealt, else `EngineError`
  - [x] 2.3 `_HandDriver.act` builds a `HandView` and calls `build_observation(view, seat)`
- [x] Task 3: `engine/showdown.py` with `should_show(state, pk_index) -> bool` (`all_in_status or can_win_now`). The driver calls `show_or_muck_hole_cards(bool)` explicitly (AC: 3, 4)
- [x] Task 4: Tests (AC: 1–4)
  - [x] 4.1 `tests/engine/test_observation.py`: field correctness, non-actor / finished hand / missing holes raise
  - [x] 4.2 Leak property test: hypothesis + a seeded 300-hand loop, scanning every card-like string in JSON and Python dumps
  - [x] 4.3 Showdown goldens: uncontested, all-in reveals before runout, side-pot winner shows after losing the main pot, beaten hand mucks, tie both show, river aggressor shows first
  - [x] 4.4 Reveal invariant property: revealed cards == dealt cards, live seats only, at most once each

## Dev Notes

- **Current state (story 1.3):** `build_observation(state, *, config, seat, hole_cards, board, street, history)` takes the actor's hole cards from the caller. `_HandDriver.show_or_muck` calls `show_or_muck_hole_cards()` with no argument (PokerKit default).
- **What this story changes:** the signature becomes `build_observation(view, seat)` to match the epic AC. The builder selects the seat's own cards itself, so the leak guarantee is local to one function. Showdown decisions move to our code.
- **What must be preserved:** event order, `IllegalActionRecord` behavior, CALL street-total semantics, mucked hands not emitted, all existing goldens.
- **Verified PokerKit 0.7.7 behavior:**
  - `show_or_muck_hole_cards(None)` shows iff `state.all_in_status or state.can_win_now(i)`. `can_win_now` checks every pot the player is eligible for, and ties count (`max_hand <= hand`).
  - The showdown order starts at `opener_index` (the last aggressor), else at PokerKit index 0 (first seat after the button).
  - In an all-in situation, show/muck is requested before the remaining burn/deal, so `ShowdownRevealed` precedes the runout `StreetDealt` events.
- No new dependencies.

### Previous story intelligence (1-3)
- Seat ↔ PokerKit index: `seat_of(i, button, n)` / `pk_index_of`. Tests use `stacked_deck(button, holes, board)` and `cfg(...)` helpers in `tests/engine/`.
- `pytest` addopts deselect `slow`. Coverage must stay at 100%.
- `Observation` validators cross-check legal-action mapping (check vs `to_call`, etc.).

### References
- [Source: _bmad-output/planning-artifacts/epics.md#story-14-information-set-observation-builder]
- [Source: _bmad-output/planning-artifacts/architecture.md#2-core-abstractions]
- [Source: _bmad-output/implementation-artifacts/1-3-pokerkit-engine-wrapper-handrunner.md]

## Dev Agent Record

### Agent Model Used

Claude Opus 5.5 (claude-opus-5-5)

### Debug Log References

- Red phase: `test_observation.py` failed at import (`pokerbot.engine.errors` missing).
- The side-pot golden exposed a PokerKit quirk. `_end_betting` sets `all_in_status = True` at the river whenever any stack is 0, so the default show/muck tabled QQ, which had lost both pots. The engine now computes the all-in situation itself (at most one live player with chips). It computes it once per showdown, because mucking clears PokerKit statuses mid-showdown.
- The first leak scanner walked `model_dump()`, but `Card` serializes to a string there, so it found nothing. The scanner now walks the live object graph (`_reachable_cards`), and `test_leak_scanner_detects_a_leak` guards against a vacuous scanner.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created
- `build_observation(view: HandView, seat)` reads only `view.hole_cards[seat]`. It raises `EngineError` for a non-actor, a finished hand, or missing hole cards.
- `engine/showdown.py`: explicit reveal rules (`is_all_in_situation`, `should_show`). The driver passes an explicit bool to `show_or_muck_hole_cards`.
- `EngineError` moved to `engine/errors.py`, still importable from `engine.hand_runner`.
- Tests: 14 new in `tests/engine/test_observation.py`. They cover builder unit tests, a leak property (hypothesis, 150 examples, 2–9 seats, antes, 10% illegal actions) plus 300 seeded hands scanning JSON and the object graph, a reveal-invariant property, and showdown goldens (uncontested, all-in before runout, river aggressor first with the beaten caller mucking, beaten aggressor, tie, side-pot winner shows after losing the main pot, river shove-call). 183 tests pass, 100% coverage; the slow 10k-hand test passes; ruff and mypy are clean.

### File List

- backend/src/pokerbot/engine/errors.py (new)
- backend/src/pokerbot/engine/showdown.py (new)
- backend/src/pokerbot/engine/observation.py
- backend/src/pokerbot/engine/hand_runner.py
- backend/tests/engine/test_observation.py (new)
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-11-10: Story 1.4 implemented: `HandView` + `build_observation(view, seat)`, explicit showdown reveal rules, leak and reveal property tests. Status → review.

## Focused Review (2026-11-10)

- Edge Case Hunter: no concrete runtime findings in the active story files and directly affected code.
- [x] [Review][Patch] Add explicit Python `model_dump()` privacy assertions alongside JSON and live-object checks for observations, and Python dump assertions for public events before showdown. Guard the Python dump scanner against vacuous success.
- Validation: default backend suite 183 passed, 1 slow test deselected, 100% coverage; ruff and mypy passed. After the test-only patch, all 14 observation tests and targeted ruff passed.
- Review scope: story file list and directly affected code; backend files are untracked, so reviewed current contents rather than treating the entire scaffold as this story's diff.
- Outcome: all acceptance criteria satisfied; story done. No deferred issues.

### Review Change Log

- 2026-11-10: Focused review completed, Python dump privacy coverage strengthened, story and sprint status marked done.

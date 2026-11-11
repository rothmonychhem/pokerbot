---
baseline_commit: NO_VCS
---

# Story 1.3: PokerKit engine wrapper (HandRunner)

Status: done

## Story

As the system,
I want to run a full NLHE hand through PokerKit,
so that rules (min-raise, all-in, side pots) are correct.

## Acceptance Criteria

1. Given 2–9 seats with stacks/blinds/ante and a pre-ordered deck, when agents act, then the hand completes and a `HandResult` with net payouts per seat, final stacks, board, hole cards and the public event log is returned.
2. Property test: total chips are conserved across 10k random hands with random legal actions (`slow`-marked; a faster hypothesis-driven variant runs in the default suite).
3. Illegal actions from an agent (including an agent raising an exception) are rejected and converted to check if legal, otherwise fold, with a logged warning recorded in the result.
4. Golden tests cover split pot, 3-way all-in with two side pots, and a walk (everyone folds to the BB).
5. Every agent receives every public event via `observe()` in order; the acting agent receives an `Observation` (story 1.2 model) with correct legal actions, `to_call` and raise bounds.

## Tasks / Subtasks

- [x] Task 1: Configuration and result models (AC: 1)
  - [x] 1.1 `engine/models.py`: `HandConfig(hand_id, stacks: tuple[int, ...], button, small_blind, big_blind, ante=0)` as a `DomainModel` with validators (2–9 seats, button in range, all stacks > 0, SB ≤ BB)
  - [x] 1.2 `HandResult(hand_id, starting_stacks, final_stacks, payouts, board, hole_cards: tuple[tuple[Card, Card], ...], events: tuple[PublicEvent, ...], illegal_actions: tuple[IllegalActionRecord, ...])` with invariant `sum(payouts) == 0`
- [x] Task 2: Seat ↔ PokerKit index mapping and card conversion (AC: 1)
  - [x] 2.1 `engine/seating.py`: PokerKit index `i` ↔ seat `(button + 1 + i) % n` (index 0 is the first seat after the button; last index is the button; heads-up the button posts the SB, which PokerKit handles)
  - [x] 2.2 Card conversion domain `Card` ↔ PokerKit card string (`"As"`)
- [x] Task 3: HandRunner (AC: 1, 3, 5)
  - [x] 3.1 `engine/hand_runner.py`: `run_hand(config, agents: Sequence[Agent], deck: Sequence[Card]) -> HandResult`. Deck must have ≥ 2n + 8 unique cards. Deal hole cards one card at a time in PokerKit dealee order, then burn + flop(3), burn + turn, burn + river, all from the deck in order
  - [x] 3.2 PokerKit automations: ante posting, blind posting, bet collection, hand killing, chips pushing, chips pulling. Dealing, burning, runout selection (always 1) and show/muck are driven manually so cards come from our deck and reveals are observable
  - [x] 3.3 Build `Observation` for the actor (`engine/observation.py`, `build_observation`): legal actions = FOLD only if `to_call > 0`; CHECK/CALL by call amount; BET if no bet is faced on this street (all `bets` are 0), otherwise RAISE, when `can_complete_bet_or_raise_to()`; `pot = total_pot_amount`
  - [x] 3.4 Apply the action: validate type against legal actions and bet/raise amount against `[min, max]`; on any violation or agent exception, log a warning, record an `IllegalActionRecord`, and apply check if legal, else fold
  - [x] 3.5 Emit public events to all agents in order: `HandStarted`, forced bets as `PlayerActed` (blinds, antes), each decision as `PlayerActed` (with `all_in` when the stack hits 0), `StreetDealt` per street, `ShowdownRevealed` for each shown (not mucked) hand, `HandEnded`
- [x] Task 4: Tests (AC: 2, 4, 5)
  - [x] 4.1 Golden: split pot, 3-way all-in with two side pots (short stack wins main pot, middle stack wins side pot 1, big stack gets the uncalled/side remainder back), walk to the BB, heads-up blind order
  - [x] 4.2 Illegal action cases: check when facing a bet → fold; raise below min → check/fold; bet when RAISE is legal; agent exception
  - [x] 4.3 Chip conservation: hypothesis (seed, seat count 2–9, random stacks/blinds/ante) running random-legal agents; plus `@pytest.mark.slow` 10k-hand loop
  - [x] 4.4 Event-order test: every agent sees an identical event sequence; the actor's observation matches PokerKit state

### Review Findings

- [x] [Review][Patch] CALL amounts were chips-added while BET/RAISE are street totals [engine/hand_runner.py:207] — CALL now records the street total after calling; semantics documented on `PublicAction.amount`; goldens for a limped SB completion (2) and an all-in call (50, all_in)
- [x] [Review][Patch] `HandConfig` coerced `True` / `100.0` / `"100"` [engine/models.py:20] — strict ints, matching `Action.amount`
- [x] [Review][Patch] `pokerkit>=0.6` was wider than the verified version [backend/pyproject.toml:11] — pinned `>=0.7.7,<0.8`
- [x] [Review][Patch] (test gap) Muck and short-all-in-does-not-reopen were only covered by random tests — golden tests added

Reviewer also fuzzed 30k edge-heavy hands (tiny stacks, antes, sb == bb, min-raise/all-in agents) with no exceptions, validation failures or false illegal-action records. Noted, not a finding: a PokerKit exception inside `apply()` would surface as a raw `ValueError` after a partial event stream. It was never reached, so revisit when story 1.7 adds the table loop.

## Dev Notes

- **New dependency:** `pokerkit>=0.6` (installed: 0.7.7, MIT, Python ≥3.11). User approved by starting this story. Approved in the architecture (ADR 1).
- **Verified PokerKit 0.7.7 behavior (probe):**
  - `NoLimitTexasHoldem.create_state(automations, ante_trimming_status=True, raw_antes=ante, raw_blinds_or_straddles=(sb, bb), min_bet=bb, raw_starting_stacks, player_count, mode=Mode.CASH_GAME)`
  - Heads-up `(1, 2)` blinds give `bets == [2, 1]`: index 0 = BB, index 1 = button/SB. With 3 or more players, `bets == [1, 2, 0, ...]`.
  - After all-in with no actor left, `can_select_runout_count()` must be answered (`select_runout_count()`) before burning or dealing.
  - `show_or_muck_hole_cards()` returns an operation whose `hole_cards` is `()` when mucked.
  - `can_fold()` is True even when checking is free, so the wrapper must not offer FOLD when `to_call == 0`.
  - `max_completion_betting_or_raising_to_amount` is capped by the actor's stack.
- `build_observation` here is the minimal builder needed to drive agents. Story 1.4 hardens it (leak property tests, showdown reveal rules), so keep it in its own module.
- RNG/shuffling is story 1.5: `run_hand` takes an explicit pre-ordered deck. Tests build decks deterministically.
- Use domain models from `pokerbot.domain` and never construct invalid ones (they validate). `Observation` validators (check vs `to_call`, etc.) act as a cross-check on the mapping.
- Logging: `logging.getLogger(__name__)`; no prints.

### Previous story intelligence (1-2)
- Domain collections are tuples; `HandEnded.payouts` is a per-seat tuple. Use `DomainModel` for new models.
- `Street.order` exists (do not use `.index`; it shadows `str.index`).
- `PublicAction` validator: forced bets are preflop only and need an amount; fold/check must have amount `None`; bet/raise need an amount > 0.
- `tests/strategies.py` has `observations()` and `public_actions()`. Tests import as `from tests.strategies import ...`; pytest uses `pythonpath = ["src", "."]`.

### References
- [Source: _bmad-output/planning-artifacts/architecture.md#2-core-abstractions]
- [Source: _bmad-output/planning-artifacts/architecture.md#7-key-decisions-adrs]
- [Source: _bmad-output/planning-artifacts/epics.md#story-13-pokerkit-engine-wrapper-handrunner]
- [Source: _bmad-output/implementation-artifacts/1-2-cards-actions-and-observation-models.md]
- PokerKit docs: https://pokerkit.readthedocs.io/

## Dev Agent Record

### Agent Model Used

Claude Opus 5.5 (claude-opus-5-5)

### Debug Log References

- Probed PokerKit 0.7.7 before writing code (see Dev Notes): heads-up blind order, runout selection after all-ins, mucks returned as `()`, `can_fold()` true when check is free, ante posting before blinds (a short stack can be all-in on the ante, so its BB posts 0 and is not emitted), `total_pot_amount` includes live bets.
- Red phase: engine tests failed at import before the modules existed.
- The first full run took about 50 s because the `slow` 10k-hand test was not deselected. Fixed with `-m 'not slow'` in pytest `addopts` (CI already passes `-m "not slow"`). Profiling: about 3.4 ms/hand, dominated by PokerKit showdown evaluation, not by our wrapper.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created
- `engine/models.py`: `HandConfig`, `IllegalActionRecord`, `HandResult` (invariants: per-seat lengths, payouts = final - starting, sum = 0).
- `engine/seating.py`: seat ↔ PokerKit index mapping; card conversion.
- `engine/observation.py`: `legal_actions()` and minimal `build_observation()` (story 1.4 hardens it).
- `engine/hand_runner.py`: `run_hand(config, agents, deck)`. Deals from the given deck (hole round-robin, burn + board), drives agents, contains illegal actions and agent exceptions (fallback check else fold, warning logged and recorded), contains `observe()` failures, emits HandStarted, forced bets, decisions, StreetDealt, ShowdownRevealed (shown hands only), HandEnded to all agents.
- Tests: 44 new engine tests (161 total in the default suite, 100% coverage). Goldens: split pot, 3-way all-in with two side pots and an uncalled-bet return, walk, heads-up blind order, antes with all-in on the ante, BB option, observation fields. Illegal-action matrix. Chip conservation over 500 seeded hands, a hypothesis property (150 examples, 10% illegal actions), and a 10k-hand `slow` test (passed, 42 s; run with `uv run pytest -m slow`).
- New dependency: `pokerkit` 0.7.7 (`pokerkit>=0.6`).

### File List

- backend/pyproject.toml (pokerkit dependency; `-m 'not slow'` addopts)
- backend/uv.lock
- backend/src/pokerbot/engine/models.py
- backend/src/pokerbot/domain/actions.py (PublicAction.amount docs)
- backend/src/pokerbot/engine/seating.py
- backend/src/pokerbot/engine/observation.py
- backend/src/pokerbot/engine/hand_runner.py
- backend/tests/engine/__init__.py
- backend/tests/engine/helpers.py
- backend/tests/engine/test_seating.py
- backend/tests/engine/test_models.py
- backend/tests/engine/test_hand_runner.py
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-11-10: Story 1.3 implemented — PokerKit HandRunner, seating, observation builder, goldens and chip-conservation tests. Status → review.
- 2026-11-10: Code review (Edge Case Hunter): 3 patch findings plus 1 test gap fixed (CALL total-to semantics, strict HandConfig, pokerkit pin `>=0.7.7,<0.8`, muck and non-reopening goldens). 169 tests, 100% coverage. Status → done.

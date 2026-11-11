---
baseline_commit: cebf883ef07b0682acb44f02aa8a0b6a101e04e6
---

# Story 1.7: Table session loop & hand history

Status: done

## Story

As the system, I want a table that plays consecutive hands and records them, so that sessions and sims can run.

## Acceptance Criteria

1. `TableSession` plays consecutive existing `run_hand` hands, carries stacks forward, rotates a moving button clockwise among eligible seats, and posts correct blinds/antes through PokerKit. Physical seats remain stable even when busted/sitting out; dense engine seats are mapped at the session boundary. Fewer than two eligible players stops play without creating a hand.
2. A validated immutable `TableConfig` supports 2–9 physical seats, initial nonnegative integer stacks, positive blinds/optional ante, an initial button, sitting-out seats, `rebuy_policy` none/manual/auto and optional positive `rebuy_to` (required for auto). Auto rebuys only busted, participating players to the target between hands. Manual `rebuy(seat, amount)` adds chips between hands under manual/auto policy. Track additional chips separately; sitting-out stacks are preserved. Sitting in/out/rebuy/reentrant play are rejected while a hand is running.
3. Each completed hand is stored as validated `HandHistory(config, result, seats, table_stacks)`, where config/result use dense engine indexing, seats maps dense to physical seats, and table_stacks records the full pre-hand physical stacks. Its mapped `events` and `actions` use physical seats. JSON round-trips the full private history, including deck audit, without losing config, seat mapping or results.
4. Each history exports PokerStars-style text; `parse_text_actions(text)` reproduces the exact physical `PublicAction` list including forced bets, street, street-total call/raise amounts and all-in flags. Support only the documented generated subset, not an arbitrary third-party importer. Clearly identify full history/deck audit as private; never broadcast hidden cards or audit deck to agents.
5. Every public event is delivered exactly once, in order, to every original table agent, including busted/sitting-out agents; only active agents decide and receive observations with physical seat/button/stacks/action history. An observer exception does not prevent other agents receiving the event or stop the hand. Standalone `run_hand` behavior remains compatible. Optional `on_event` callback enables a session to broadcast once while compact adapters' observe methods do nothing.
6. Default play securely shuffles; seeded sessions derive distinct per-hand seeds using base seed plus completed-hand index. Explicit deck injection remains available per `play_hand` for goldens/replay (session deliberately bypasses shuffle options for this input). Histories include unique deterministic table/hand IDs. Failed runs must not commit staged rebuys, stacks, button, hand count or history. Tests cover rotation with gaps/heads-up, side pots/all-in/busts, sitting out/in, rebuys, deterministic sessions, exports and broadcast/privacy. Existing regression tests pass, default Python coverage stays 100%.

## Tasks / Subtasks

- [x] Task 1: Add history model, physical-seat event/action mapping, JSON/text export and generated-text action parser with strict boundary checks and round-trip tests (AC 3, 4).
- [x] Task 2: Add optional public-event callback to HandRunner with isolated failures, preserving standalone broadcasts; test the hook (AC 5).
- [x] Task 3: Add TableConfig/TableSession, compact-to-physical observation adapters, policies, stack carry-forward and deterministic loop; tests for all stated policies, invalid/reentrant/failed boundaries and event delivery (AC 1, 2, 5, 6).
- [x] Task 4: Document policies, private history and supported text syntax; run focused and full regression/coverage/lint/type checks, then focused review (AC 1–6).

## Dev Notes

- Architecture §§1,2,4,6: engine/table.py and engine/history.py own the synchronous session and private records. Async TableManager, REST/WS, persistence and UI are later epics. No new dependencies.
- Current HandConfig requires all seated stacks positive and 2–9 seats. Compact only eligible players in clockwise physical seat order; HandConfig.button is `seats.index(physical_button)`. PokerKit already handles heads-up blind rules. Use a moving-button policy (skip inactive seats); dead-button/missed-blind accounting is out of scope and documented.
- Existing run_hand(config, agents, deck=None, *, mode="play", seed=None) emits events only to its agents. Add optional `on_event: Callable[[PublicEvent], None] | None` to `_HandDriver` and run_hand; isolate callback exceptions. Do not change action/reveal/commit ordering. Session compact adapters forward decide with mapped observations but observe is a no-op; the callback maps and broadcasts each event exactly once to all original agents.
- Physical observations contain full table stacks (including inactive balances), own seat/hole cards and physical history/button. Map compact current stacks into pre-hand full table balances. HandStarted/HandEnded vectors map the same way (inactive payouts zero). Showdown reveals and actions map seat IDs; board events pass unchanged.
- Shared contract in history.py: `map_event(event, seats: tuple[int,...], table_stacks: tuple[int,...]) -> PublicEvent`; `HandHistory` fields `config: HandConfig`, `result: HandResult`, `seats: tuple[int,...]`, `table_stacks: tuple[int,...]`; properties `events: tuple[PublicEvent,...]` and `actions: tuple[PublicAction,...]`; `to_json()`, `from_json(text)`, `to_text()`, standalone `parse_text_actions(text) -> tuple[PublicAction,...]`.
- Validate history mapping count/unique/range; full stack count 2–9 and nonnegative strict ints; config stacks equal mapped full stacks; result ID/start stacks match config and first event is matching HandStarted. Preserve deck-audit validation on JSON reload.
- Text uses deterministic Player<physical-seat> labels (no arbitrary player names). PokerStars-style header, table/seat lines, street markers, actions with chip deltas and raise-to totals, all-in suffix, public reveals and summary. Parser reconstructs street totals, not merely displayed call deltas. Include private deck audit only after the hand summary; generated subset documented. Not a general PokerStars importer or authenticated audit proof.
- TableConfig defaults: `table_id="table"`, `stacks` required, button=0, blinds 1/2, ante=0, `sitting_out=()`, rebuy_policy="none", rebuy_to=None, mode="play", seed=None. Validate sim seed nonnegative integer (bool rejected) / play no seed. TableSession(config, agents); read-only tuple properties stacks/history/rebuy_totals/sitting_out; `sit_out(seat)`, `sit_in(seat)`, `rebuy(seat, amount)`, `play_hand(deck=None) -> HandHistory | None`, `play(hands:int) -> tuple[HandHistory,...]` returns newly played histories and stops when fewer than2 eligible.
- Stage all state updates until success. Guard mutations for entire hand with try/finally; choose button initially at configured eligible seat or next eligible clockwise, then next eligible after last actual button. Failed hand leaves session state unchanged; agent-side effects cannot be rolled back. Skipped/no-hand attempt does not consume seed/hand ID or apply staged auto rebuys.
- Prior story 1.6 passed 300 default tests at 100% coverage. Prior 1.5 added private deck audit with commitment tied to first HandStarted. Preserve that. All backend files are untracked against sole setup commit; do not stage unrelated files. No AGENTS.md or project-context.md found.

### References

- `_bmad-output/planning-artifacts/epics.md` Story 1.7.
- `_bmad-output/planning-artifacts/architecture.md` §§1,2,4,6.
- `_bmad-output/implementation-artifacts/1-6-hand-evaluator-equity-calculator.md`.
- Existing `engine/hand_runner.py`, `engine/models.py`, `domain/observation.py`, `domain/events.py` and test helpers.

## Dev Agent Record

### Agent Model Used

GPT-6 Codex

### Debug Log References

- Red/green: new event hook and table tests confirmed missing API/module before implementation. History tests similarly confirmed missing module.
- Focused validation: 36 table/session tests, 24 history tests, 2 public-event hook tests; randomized integration covers 20 configurations × 3 hands, 2–9 physical seats, sitting out, auto rebuys, public delivery, private observations, and both export formats.
- Full backend default suite: 362 passed, 1 slow test deselected, 100% coverage. Strict mypy clean across 32 source files; Ruff and formatting checks clean after combining one nested test context manager.

### Completion Notes List

- Added synchronous sessions with stable physical seats, dense engine adapters, clockwise moving button, stack carry-forward, sitting out/in, none/manual/auto rebuy policies, and separate rebuy totals.
- Added transactional session bookkeeping and reentrancy guard; agent effects from failed hands remain observable as documented.
- Added public-event callback while retaining standalone runner delivery. Sessions map/broadcast once to all original agents, isolating observer failures.
- Added validated private HandHistory, full JSON round-trips, and generated PokerStars-style text/action parsing with street-total call reconstruction, raises, forced posts, all-ins, showdown cards and private deck audit.
- Documented policy scope, secure/seeded session behavior, physical/dense indexing and private-history boundaries. No new dependencies.

- Source ACs and current engine inspected; seat mapping, moving button, history privacy, rebuy and text-parser assumptions recorded.

### File List

- backend/src/pokerbot/engine/hand_runner.py
- backend/src/pokerbot/engine/history.py (new)
- backend/src/pokerbot/engine/table.py (new)
- backend/tests/engine/test_event_hook.py (new)
- backend/tests/engine/test_history.py (new)
- backend/tests/engine/test_table.py (new)
- backend/README.md
- _bmad-output/implementation-artifacts/1-7-table-session-loop-hand-history.md (new)
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-11-11: Created story context for last pending epic 1 story.

- 2026-11-11: Implemented and validated the session/history story; status → review.

## Focused Review (2026-11-11)

- Edge Case Hunter: no concrete actionable findings in the session/history implementation, event hook or directly affected tests. No deferred issues.
- Scope: new engine/table.py and engine/history.py, additive callback changes in hand_runner.py, associated tests and story ACs. Unrelated untracked scaffold excluded.
- Validation: 362 default tests passed, 1 slow test deselected, 100% coverage. Ruff, touched-file formatting checks, and strict mypy across 32 source files passed. Randomized session/export/privacy integration covers 20 configurations × 3 hands.
- All tasks and acceptance criteria complete. Story status → done.

### Review Change Log

- 2026-11-11: Focused review completed with no actionable findings; story marked done. Epic 1 now has all seven stories done.

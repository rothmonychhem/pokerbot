---
baseline_commit: NO_VCS
---

# Story 1.2: Cards, actions and Observation models

Status: done

## Story

As a bot author,
I want typed domain models,
so that agents and engine share one contract.

## Acceptance Criteria

1. `Card`, `Street`, `ActionType`, `Action`, `PublicAction`, `Observation`, `PublicEvent` are defined as Pydantic v2 models/enums per architecture §2 (fields at minimum as listed there), immutable (frozen) and validated.
2. `Agent` is a `typing.Protocol` (runtime-checkable) with `decide(obs: Observation) -> Action` and `observe(event: PublicEvent) -> None`.
3. JSON serialization round-trips are tested for every model, including every `PublicEvent` variant, with property-based (hypothesis) tests for `Card` and `Observation`.
4. Invalid states are rejected at construction (bad card strings, duplicate cards, board size not matching street, seat out of range, negative chips, bet/raise without amount).

## Tasks / Subtasks

- [x] Task 1: Cards (AC: 1, 3, 4)
  - [x] 1.1 `Rank` (IntEnum 2..14, symbol `23456789TJQKA`) and `Suit` (StrEnum `c d h s`)
  - [x] 1.2 `Card` frozen model `(rank, suit)`; parses from and serializes to the 2-char string `"As"`; `__str__` → `"As"`; hashable; ordering by (rank, suit)
  - [x] 1.3 Helpers: `parse_cards("AsKd Th")` (accepts space-separated or concatenated), `full_deck()` → 52 unique cards in canonical order
- [x] Task 2: Actions (AC: 1, 3, 4)
  - [x] 2.1 `Street` StrEnum `preflop, flop, turn, river`, with `board_size` property (0/3/4/5)
  - [x] 2.2 `ActionType` StrEnum `fold, check, call, bet, raise` (decision actions only)
  - [x] 2.3 `ForcedBetType` StrEnum `ante, small_blind, big_blind`
  - [x] 2.4 `Action(type, amount: int | None)` — `amount` is the **total bet-to** for bet/raise (PokerKit "raise to" semantics), required and > 0; must be `None` for fold/check; call amount optional (engine computes). Constructors `Action.fold()`, `.check()`, `.call()`, `.bet(to)`, `.raise_to(to)`
  - [x] 2.5 `PublicAction(seat, street, kind: ActionType | ForcedBetType, amount: int | None, all_in: bool = False)`
- [x] Task 3: Observation (AC: 1, 3, 4)
  - [x] 3.1 Fields exactly per architecture §2 plus `small_blind`
  - [x] 3.2 Validators: 0 ≤ seat, button < len(stacks); 2 ≤ len(stacks) ≤ 9; hole cards distinct; `len(board) == street.board_size`; no card in both hole and board; all chip fields ≥ 0; if bet/raise is legal then 0 < min_raise ≤ max_raise; `legal_actions` non-empty and unique
- [x] Task 4: Public events (AC: 1, 3)
  - [x] 4.1 Discriminated union on `kind`: `HandStarted(hand_id, button, stacks, small_blind, big_blind, ante)`, `PlayerActed(action: PublicAction)`, `StreetDealt(street, cards)`, `ShowdownRevealed(seat, cards)`, `HandEnded(hand_id, payouts: dict[int, int])` (net chips won per seat)
  - [x] 4.2 `PublicEvent` type alias + module-level `PUBLIC_EVENT_ADAPTER = TypeAdapter(PublicEvent)` for parsing
- [x] Task 5: Agent protocol (AC: 2)
  - [x] 5.1 `pokerbot/agents/base.py`: `@runtime_checkable class Agent(Protocol)`; re-export the domain models used by agents
  - [x] 5.2 Test that a minimal class satisfies `isinstance(x, Agent)` and that one missing `observe` does not

### Review Findings

- [x] [Review][Patch] Frozen models held mutable lists/dict (validators bypassable via `obs.board.append`, unhashable) [domain/observation.py, domain/events.py] — all collections now tuples; `HandEnded.payouts` is a per-seat tuple
- [x] [Review][Patch] `Action.amount` coerced `true`/`1.0`/`"100"` [domain/actions.py] — `strict=True`
- [x] [Review][Patch] `PublicAction` accepted bet/raise without amount and forced bets after preflop [domain/actions.py] — kind/amount/street validator
- [x] [Review][Patch] `HandStarted` lacked table checks (button range, negative stacks, SB > BB) [domain/events.py] — validator added
- [x] [Review][Patch] `Observation` accepted contradictory legal actions vs `to_call`, off-table/future-street history, SB > BB [domain/observation.py] — validators added
- [x] [Review][Patch] Hypothesis `observations()` produced non-engine states and skipped ForcedBetType/None/all_in branches [tests/strategies.py] — rewritten (legal derived from to_call, new `public_actions` strategy, varied blinds)
- [x] [Review][Patch] `Card` input JSON schema was an object while wire format is a string [domain/cards.py] — string+pattern schema in both modes
- [x] [Review][Patch] `model_copy(update=...)` skipped validation [domain/*.py] — new `DomainModel` base re-validates updates

## Dev Notes

- **Location (variance from architecture §1, intentional):** domain models go in a new package `backend/src/pokerbot/domain/` (`cards.py`, `actions.py`, `observation.py`, `events.py`, `__init__.py` re-exports). Reason: `engine`, `eval` and `agents` all depend on them; putting them in `agents/base.py` would make `engine` import from `agents`, and putting cards in `engine` would make `eval` depend on `engine`. `agents/base.py` holds only the `Agent` protocol and re-exports.
- Chips are `int` in the smallest unit everywhere (never floats).
- Use Pydantic v2: `model_config = ConfigDict(frozen=True, extra="forbid")`. For `Card` string serialization use `@model_serializer` plus `@model_validator(mode="before")` accepting `str`. Check that `Card` inside `tuple[Card, Card]` and `list[Card]` serializes as strings in `model_dump_json()`.
- `PublicEvent` must stay public-only: no event carries hole cards except `ShowdownRevealed` (cards shown by rule). Story 1.4 adds the property test on leaks; keep the models so that such a test is possible.
- No new runtime dependencies (pydantic is already present; hypothesis is already in the dev group).
- mypy strict must pass; the `pydantic.mypy` plugin is enabled.

### Previous story intelligence (1-1)
- Run tests with `cd backend && uv run --no-sync pytest`. On this Mac, if `ModuleNotFoundError: pokerbot` appears outside pytest, run `chflags nohidden backend/.venv/lib/python3.*/site-packages/*.pth`.
- Quality gates: `ruff check`, `ruff format --check`, `mypy` (strict, `src/`). `tests/test_package.py` imports every subpackage, so add `pokerbot.domain` to its list.
- Pytest filters the Starlette `httpx` deprecation warning; leave it as is.

### Testing standards
- Tests in `backend/tests/domain/` mirroring modules; hypothesis strategies in `tests/strategies.py`, reused by later stories (1.3, 1.4).
- Cover every validator with a failing-construction test.

### References
- [Source: _bmad-output/planning-artifacts/architecture.md#2-core-abstractions]
- [Source: _bmad-output/planning-artifacts/architecture.md#3-decision-pipeline-every-bot] (abstract actions come later, in story 3.1)
- [Source: _bmad-output/planning-artifacts/epics.md#story-12-cards-actions-and-observation-models]
- [Source: _bmad-output/implementation-artifacts/1-1-monorepo-scaffold-tooling.md]

## Dev Agent Record

### Agent Model Used

Claude Opus 5.5 (claude-opus-5-5)

### Debug Log References

- Red phase: all new test modules failed at import before `pokerbot.domain` existed.
- After adding `tests/__init__.py` (needed for `from tests.strategies import ...`), pytest stopped finding `pokerbot`: macOS keeps re-applying the `hidden` flag to `.venv` and its `.pth` files, and Python 3.14 skips hidden `.pth` files. Fixed durably for tests with `pythonpath = ["src", "."]` in `[tool.pytest.ini_options]`, so tests no longer depend on the editable-install `.pth`. Running the app locally (uvicorn) can still hit it; the README troubleshooting note covers that, and Python ≤3.13 or Linux/CI/Docker are unaffected.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created
- New package `pokerbot.domain` (intentional variance from architecture §1, see Dev Notes): `cards.py` (Rank, Suit, Card as "As" string in JSON, parse_cards, full_deck), `actions.py` (Street with board_size, ActionType, ForcedBetType, Action with bet-to semantics and constructors, PublicAction), `observation.py` (Observation per architecture §2 plus `small_blind`, with all consistency validators), `events.py` (discriminated `PublicEvent` union of HandStarted, PlayerActed, StreetDealt, ShowdownRevealed, HandEnded, plus `PUBLIC_EVENT_ADAPTER`).
- `pokerbot.agents.base.Agent`: runtime-checkable Protocol (`decide`, `observe`) and re-exports.
- All models are frozen with `extra="forbid"`.
- Tests: 73 new (90 total), including hypothesis round-trips for Card and Observation and parametrized invalid-construction cases for every validator. Reusable strategies are in `tests/strategies.py` for stories 1.3 and 1.4. Coverage 100%; ruff, ruff format and mypy strict clean.

### File List

- backend/pyproject.toml (pytest `pythonpath`)
- backend/src/pokerbot/domain/__init__.py
- backend/src/pokerbot/domain/base.py
- backend/src/pokerbot/domain/cards.py
- backend/src/pokerbot/domain/actions.py
- backend/src/pokerbot/domain/observation.py
- backend/src/pokerbot/domain/events.py
- backend/src/pokerbot/agents/base.py
- backend/tests/__init__.py
- backend/tests/strategies.py
- backend/tests/test_package.py (modified)
- backend/tests/test_agent_protocol.py
- backend/tests/domain/__init__.py
- backend/tests/domain/test_cards.py
- backend/tests/domain/test_actions.py
- backend/tests/domain/test_observation.py
- backend/tests/domain/test_events.py
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-11-10: Story 1.2 implemented — domain models, Agent protocol, round-trip and validation tests. Status → review.
- 2026-11-10: Code review (Edge Case Hunter): 8 patch findings applied (immutability, strict amounts, extra validators, schema, re-validating copies); `Street.order` added (not `index`, which would shadow `str.index`). 117 tests, 100% coverage. Status → done.

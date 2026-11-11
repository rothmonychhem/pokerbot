---
baseline_commit: NO_VCS
---

# Story 1.1: Monorepo scaffold & tooling

Status: done

## Story

As a developer,
I want the backend/frontend skeleton with tooling,
so that every later story has a consistent base.

## Acceptance Criteria

1. Given a clean clone, when I run `cd backend && uv sync && uv run pytest`, then the backend test suite runs green (includes a health-endpoint test, not just a placeholder).
2. Given the frontend, when I run `cd frontend && pnpm i && pnpm test`, then Vitest passes (at least one component test).
3. ruff (lint + format), mypy (`strict = true` on `src/`), pre-commit hooks, and a GitHub Actions CI workflow (backend + frontend jobs) are configured.
4. `docker compose up` starts the backend (FastAPI `GET /health` → `{"status":"ok"}`) and the frontend dev server.

## Tasks / Subtasks

- [x] Task 1: Backend package (AC: 1, 3)
  - [x] 1.1 `backend/pyproject.toml` (uv, hatchling build, `src/` layout, package `pokerbot`, `requires-python = ">=3.12"`)
  - [x] 1.2 Runtime deps: `fastapi`, `uvicorn[standard]`, `pydantic>=2`. Dev deps (dependency-group `dev`): `pytest`, `pytest-cov`, `httpx`, `hypothesis`, `ruff`, `mypy`, `pre-commit`
  - [x] 1.3 Create package skeleton dirs from architecture §1 with `__init__.py`: `engine, eval, agents (+ heuristic, gto, modeling, personality), arena, api, persistence`; `cli.py` stub; `py.typed`
  - [x] 1.4 `pokerbot/api/app.py`: `create_app()` factory + `GET /health`; `pokerbot/__init__.py` exposes `__version__`
  - [x] 1.5 `tests/test_health.py` using FastAPI `TestClient`; `tests/test_package.py` imports every subpackage
  - [x] 1.6 ruff config (line-length 100, rules `E,F,I,B,UP,N,SIM,RUF`), mypy strict on `src`, pytest config (`testpaths`, `--strict-markers`, register `slow` marker)
- [x] Task 2: Frontend (AC: 2, 3)
  - [x] 2.1 Vite + React + TypeScript (`strict`) in `frontend/`, package manager pnpm (pin via `packageManager` field)
  - [x] 2.2 Tailwind CSS v4 via `@tailwindcss/vite`; Zustand dependency added (unused until 6.1)
  - [x] 2.3 Vitest + @testing-library/react + jsdom; `App.test.tsx` renders title
  - [x] 2.4 Scripts: `dev`, `build`, `test`, `lint` (eslint flat config), `typecheck`
  - [x] 2.5 Vite dev proxy `/api` → `http://localhost:8000` (backend) for later stories
- [x] Task 3: Repo tooling (AC: 3)
  - [x] 3.1 `.pre-commit-config.yaml`: ruff (check + format) on `backend/`, trailing-whitespace, end-of-file-fixer, check-yaml
  - [x] 3.2 `.github/workflows/ci.yml`: job `backend` (uv setup, sync, ruff check, ruff format --check, mypy, pytest) + job `frontend` (pnpm, install --frozen-lockfile, lint, typecheck, test, build)
  - [x] 3.3 Root `README.md` with quickstart; `.editorconfig`
- [x] Task 4: Docker (AC: 4)
  - [x] 4.1 `backend/Dockerfile` (python:3.12-slim + uv, `uvicorn pokerbot.api.app:app --host 0.0.0.0`)
  - [x] 4.2 `frontend/Dockerfile` (node:22-alpine + corepack pnpm, `pnpm dev --host`)
  - [x] 4.3 `docker-compose.yml` with services `backend` (8000) and `frontend` (5173), healthcheck on `/health`; proxy target via `VITE_API_TARGET` env

### Review Findings

- [x] [Review][Patch] pre-commit `check-yaml` rejects pnpm 12 multi-document lockfile, blocking every commit touching it [.pre-commit-config.yaml:7] — fixed with `--allow-multiple-documents`
- [x] [Review][Patch] Vite proxy key `/api` prefix-matched `/apidocs`, `/api-client.js` etc. and sent them to the backend [frontend/vite.config.ts:15] — fixed with anchored `^/api(/|$)` and `|| '/'` rewrite fallback; verified `/api/health` proxied, `/apidocs` served by Vite

## Dev Notes

- This is the first story: no existing code. Everything is NEW. Repo root is `poker/` (git initialized, remote `origin` = github.com/rothmonychhem/pokerbot, empty).
- Follow the layout in [Source: _bmad-output/planning-artifacts/architecture.md#1-repository-layout-monorepo] exactly — later stories assume `backend/src/pokerbot/...` and `frontend/src/...`.
- Do NOT add PokerKit, phevaluator, numba, SQLModel yet — those belong to stories 1.3, 1.6, 5.1. Keep dependencies minimal to avoid unapproved scope.
- `uvicorn pokerbot.api.app:app` requires a module-level `app = create_app()`.
- Local environment: uv 0.12 and Python 3.14 present; pnpm not installed (use `corepack pnpm`); Docker not installed locally → AC4 can only be validated by `docker compose config`-equivalent review/CI, record this in completion notes.
- Python version: target `>=3.12`; CI uses 3.12. Local 3.14 is acceptable.

### Testing standards
- pytest with `TestClient` for API; tests mirror package paths under `backend/tests/`.
- Coverage target ≥85% applies to engine/strategy packages (NFR5); scaffold has trivial coverage.
- Frontend: Vitest + Testing Library, jsdom environment.

### Project Structure Notes
- Matches architecture §1. Variance: `backend/training/` and `backend/artifacts/` created later (Epic 7); `artifacts/` already gitignored.

### References
- [Source: _bmad-output/planning-artifacts/architecture.md#1-repository-layout-monorepo]
- [Source: _bmad-output/planning-artifacts/research.md#4-recommended-stack]
- [Source: _bmad-output/planning-artifacts/prd.md#5-non-functional-requirements] (NFR5, NFR6)
- [Source: _bmad-output/planning-artifacts/epics.md#story-11-monorepo-scaffold--tooling]

## Dev Agent Record

### Agent Model Used

Claude Opus 5.5 (claude-opus-5-5)

### Debug Log References

- Red phase confirmed: backend tests failed on import before package existed; frontend test failed before `App.tsx` existed.
- `tsc` TS2882 on `import './index.css'` → fixed by adding `vite/client` to `types` in `tsconfig.app.json`.
- Runtime `ModuleNotFoundError: pokerbot` under uvicorn while pytest passed: macOS set the `hidden` flag on venv `.pth` files and Python 3.14 skips hidden `.pth` files. Local fix `chflags nohidden backend/.venv/lib/python3.*/site-packages/*.pth`; documented in README Troubleshooting. Not reproducible in CI/Docker (Linux).

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created
- Backend: uv/hatchling `src/` package `pokerbot` with all architecture §1 subpackages, `create_app()` + module-level `app`, `GET /health`, `pokerbot` CLI stub (`--version`). 17 tests, 100% coverage; ruff + ruff format + mypy strict clean.
- Frontend: Vite 8 + React 19 + TS 6.0 (strict, `noUncheckedIndexedAccess`) + Tailwind v4 + Zustand; Vitest 5 + Testing Library; ESLint 10 flat config. test/lint/typecheck/build all green. `/api` proxy (incl. ws) → `VITE_API_TARGET` (default `http://localhost:8000`).
- Version decisions: TypeScript pinned `~6.0.3` (TS 7 not supported by typescript-eslint `<6.1.0`). pnpm 12.18.0 pinned via `packageManager` (corepack).
- Kept `httpx` for TestClient; current Starlette warns it prefers `httpx2` — switching was blocked pending user approval, so the specific deprecation warning is filtered in pytest config with a comment. Follow-up: switch to `httpx2` once approved.
- Tooling: pre-commit (hygiene hooks + local ruff via `uv run` so hooks match pinned ruff; config validated), GitHub Actions CI with backend and frontend jobs, README, .editorconfig.
- Docker: backend (python:3.12-slim + uv, locked sync) and frontend (node:22 + corepack pnpm) Dockerfiles, compose with backend healthcheck and `service_healthy` dependency. Docker is not installed locally, so `docker compose up` (AC4) was NOT executed; YAML validated, and the equivalent runtime path was verified locally: uvicorn `/health` → `{"status":"ok"}` both directly and through the Vite proxy (`/api/health`).

### File List

- .editorconfig
- .github/workflows/ci.yml
- .pre-commit-config.yaml
- README.md
- docker-compose.yml
- backend/.dockerignore
- backend/Dockerfile
- backend/README.md
- backend/pyproject.toml
- backend/uv.lock
- backend/src/pokerbot/__init__.py
- backend/src/pokerbot/py.typed
- backend/src/pokerbot/cli.py
- backend/src/pokerbot/api/__init__.py
- backend/src/pokerbot/api/app.py
- backend/src/pokerbot/engine/__init__.py
- backend/src/pokerbot/eval/__init__.py
- backend/src/pokerbot/agents/__init__.py
- backend/src/pokerbot/agents/heuristic/__init__.py
- backend/src/pokerbot/agents/gto/__init__.py
- backend/src/pokerbot/agents/modeling/__init__.py
- backend/src/pokerbot/agents/personality/__init__.py
- backend/src/pokerbot/arena/__init__.py
- backend/src/pokerbot/persistence/__init__.py
- backend/tests/test_health.py
- backend/tests/test_package.py
- backend/tests/test_cli.py
- frontend/.dockerignore
- frontend/Dockerfile
- frontend/eslint.config.js
- frontend/index.html
- frontend/package.json
- frontend/pnpm-lock.yaml
- frontend/tsconfig.json
- frontend/tsconfig.app.json
- frontend/tsconfig.node.json
- frontend/vite.config.ts
- frontend/src/App.tsx
- frontend/src/App.test.tsx
- frontend/src/index.css
- frontend/src/main.tsx
- frontend/src/setupTests.ts
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-11-10: Story 1.1 implemented — monorepo scaffold, backend/frontend tooling, CI, Docker. Status → review.
- 2026-11-10: Code review (Edge Case Hunter): 2 patch findings applied, 0 deferred, 0 dismissed. Status → done.

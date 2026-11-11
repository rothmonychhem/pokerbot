# Poker Bot Arena

No-Limit Texas Hold'em with strategic AI opponents (difficulty tiers + personalities) and a headless simulation arena.

Planning docs: [`_bmad-output/planning-artifacts/`](_bmad-output/planning-artifacts/) · Sprint: [`sprint-status.yaml`](_bmad-output/implementation-artifacts/sprint-status.yaml)

## Requirements
- [uv](https://docs.astral.sh/uv/) (Python ≥ 3.12)
- Node 22+ with pnpm (`corepack enable pnpm`)
- Docker (optional, for `docker compose`)

## Quickstart

```bash
# backend → http://localhost:8000/health
cd backend && uv sync && uv run pytest && uv run uvicorn pokerbot.api.app:app --reload

# frontend → http://localhost:5173  (proxies /api → backend)
cd frontend && pnpm i && pnpm test && pnpm dev

# or both
docker compose up
```

## Quality gates
- Backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
- Frontend: `pnpm lint && pnpm typecheck && pnpm test && pnpm build`
- Hooks: `uv run --directory backend pre-commit install`

## Layout
```
backend/   Python package `pokerbot` (engine, eval, agents, arena, api, persistence)
frontend/  React + TypeScript + Vite + Tailwind
```

## Troubleshooting
- **`ModuleNotFoundError: No module named 'pokerbot'` outside pytest (macOS + Python 3.14):** macOS can flag the venv's `.pth` files as hidden, and Python 3.14 skips hidden `.pth` files. Fix: `chflags nohidden backend/.venv/lib/python3.*/site-packages/*.pth`.

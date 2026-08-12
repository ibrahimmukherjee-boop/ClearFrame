# AGENTS.md

## Cursor Cloud specific instructions

### Repo layout

Monorepo with three parts:

- `platform/` — the main product ("Erasys ClearFrame Stack"): React 19 + Vite SPA (`platform/src`) plus a FastAPI backend (`platform/backend`, entry `run.py`). SQLite by default (auto-created under `platform/backend/data/`); Postgres/Redis/Ollama are optional and NOT needed for dev. See `platform/README.md` for the API reference.
- `clearframe/` — the standalone Python library (pytest suite in `clearframe/tests`). Note: the backend uses a vendored copy at `platform/backend/vendor/clearframe`, installed editable via `platform/backend/requirements.txt`. Changes to top-level `clearframe/` do NOT affect the backend unless mirrored in the vendored copy.
- `nexus-sandbox/` — a separate demo product; its unified app also binds :8080, so don't run it at the same time as the platform backend.

### Running the platform (dev)

- `cd platform && npm run dev:all` starts both the API (:8080) and Vite UI (:5173). Backend requires the venv at `platform/backend/.venv` (created by the startup script). The backend also spawns the ClearFrame AgentOps server on :7477.
- The Vite dev server binds IPv6 only: use `http://localhost:5173`, not `http://127.0.0.1:5173` (curl to 127.0.0.1:5173 gets connection refused). The API on :8080 is reachable via 127.0.0.1.
- Dev login seeded automatically: `admin@erasys.local` / `admin`. The login API response field is `accessToken` (not `token`).
- Health checks: `GET http://127.0.0.1:8080/api/health` and `GET http://127.0.0.1:7477/health`.

### Lint / tests

- Frontend lint: `cd platform && npm run lint` (oxlint; exits 0, warnings mostly from built assets in `docs/`).
- Backend tests: `cd platform/backend && .venv/bin/pytest tests` — `tests/test_stress.py` is an integration suite that requires the API to be RUNNING on :8080 (it fails with URLError otherwise). Start the backend first.
- Library tests: `cd clearframe && .venv/bin/pytest` (all pass). `ruff check .` currently reports ~264 pre-existing style errors (mostly import ordering); don't treat those as regressions.
- pip editable installs in `requirements.txt` use paths relative to the CURRENT working directory, so run `pip install -r requirements.txt` from inside `platform/backend`, not from the repo root.

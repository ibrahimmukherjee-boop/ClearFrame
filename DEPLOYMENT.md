# ClearFrame platform — deployment guide

Two ways to run the platform:

| Mode | What runs | Use for |
|---|---|---|
| **Instant demo** | GitHub Pages only — the console simulates the API in the browser (localStorage) | Demos, emails, evaluation. No accounts, no servers. |
| **Live** | GitHub Pages console + FastAPI/Postgres backend | Real persistent state, multi-user auth, audit trails |

## Architecture

```mermaid
flowchart LR
  browser[Browser] --> pages[GitHub Pages console docs/]
  pages -->|Bearer JWT| api[FastAPI service services/api/]
  api --> pg[(PostgreSQL)]
  api --> ops[ClearFrame AgentOps runtime]
```

- `docs/` — static paper/ink console (sign-in `index.html`, operator console `app.html`). Served by GitHub Pages from `main:/docs` (also deployable by the `.github/workflows/pages.yml` Actions workflow).
- `services/api/` — Dockerised FastAPI service: agents, sessions, Aegis HITL, SafePulse, TrustRegistry, Sonar, policies, governance/evidence, workflows, vault, JWT auth. Vendored copy of the `clearframe` runtime under `services/api/vendor/`.
- `render.yaml` — infrastructure-as-code for Render (web service + managed Postgres).
- The root `clearframe/` Python package (the OSS protocol) is untouched by any of this.

## 1. Instant demo (already live)

https://ibrahimmukherjee-boop.github.io/ClearFrame/ → **“Launch instant demo — no backend needed.”**

Every flow works in the browser: run the full pipeline, create/select/suspend agents, enroll and verify SafePulse, issue/verify/revoke trust certificates, start governed sessions, approve/block Aegis calls, scan prompts with Sonar, review policies, collect governance evidence, create and run workflows. State persists in the browser; **Sign out** resets it.

## 2. Live backend on Render (one click)

1. Open the Blueprint: https://dashboard.render.com/blueprint/new?repo=https://github.com/ibrahimmukherjee-boop/ClearFrame
2. Render reads `render.yaml` and creates:
   - `clearframe-db` — managed Postgres (basic-256mb)
   - `clearframe-api` — Docker web service (starter) with `/api/health` health check and a 1 GB disk at `/data`
3. Render generates secrets automatically: `CLEARFRAME_JWT_SECRET`, `CLEARFRAME_VAULT_PASSPHRASE`, `CLEARFRAME_AUDIT_SECRET`, `CLEARFRAME_ADMIN_PASSWORD`.
4. After deploy, copy `CLEARFRAME_ADMIN_PASSWORD` from the service **Environment** tab.
5. Verify: `https://clearframe-api.onrender.com/api/health` returns `{"status":"ok", ...}`.
6. On the Pages sign-in page, keep the default backend URL (or paste your Render URL), **Ping**, then sign in as `admin@erasys.local` with the generated password.

CORS is preconfigured for `https://ibrahimmukherjee-boop.github.io`. To serve the console from another origin, update `CLEARFRAME_CORS` (comma-separated origins, no wildcard in production).

## 3. Live backend anywhere else (Docker)

The service is a standard container — any Docker host (AWS, Fly, a VM) works:

```bash
docker build -t clearframe-api services/api
docker run -p 8080:8080 -v clearframe-data:/data \
  -e CLEARFRAME_ENV=production \
  -e DATABASE_URL=postgresql://user:pass@host:5432/clearframe \
  -e CLEARFRAME_CORS=https://your-pages-origin \
  -e CLEARFRAME_JWT_SECRET=$(openssl rand -hex 32) \
  -e CLEARFRAME_VAULT_PASSPHRASE=$(openssl rand -hex 32) \
  -e CLEARFRAME_AUDIT_SECRET=$(openssl rand -hex 32) \
  -e CLEARFRAME_ADMIN_PASSWORD='choose-a-strong-password' \
  clearframe-api
```

Production startup **refuses to boot** with missing/default secrets, wildcard CORS, or a non-Postgres `DATABASE_URL` (see `services/api/app/production.py`).

### Environment variables

| Variable | Purpose | Production requirement |
|---|---|---|
| `CLEARFRAME_ENV` | `production` or `development` | `production` |
| `DATABASE_URL` | Postgres connection string (`postgres://` accepted) | required |
| `CLEARFRAME_JWT_SECRET` | JWT signing key | unique secret |
| `CLEARFRAME_VAULT_PASSPHRASE` | Vault encryption | unique secret |
| `CLEARFRAME_AUDIT_SECRET` | HMAC audit chain | unique secret |
| `CLEARFRAME_ADMIN_PASSWORD` | Bootstrap `admin@erasys.local` | required |
| `CLEARFRAME_CORS` | Allowed origins, comma-separated | no `*` |
| `CLEARFRAME_HITL_BLOCKING` | Block HTTP on approvals vs. async Aegis queue | `false` (recommended) |
| `USE_OLLAMA` | Local LLM execution | `false` (no model runtime on PaaS) |
| `PORT` / `CLEARFRAME_API_PORT` | Listen port (Render sets `PORT`) | — |

Full template: `services/api/.env.example` (never commit real values).

## 4. Local development

```bash
cd services/api
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
CLEARFRAME_ENV=development CLEARFRAME_AUTH=true USE_OLLAMA=false USE_CLEARFRAME_OPS=false \
  CLEARFRAME_API_PORT=18080 .venv/bin/python run.py
```

Dev login: `admin@erasys.local` / `admin` (dev only; production has no default passwords). Point the Pages sign-in “Backend URL” at `http://127.0.0.1:18080`.

### Smoke test

`services/api/smoke_test.py` exercises every governance flow end-to-end (login, agent lifecycle, SafePulse, Trust, sessions, Aegis approve/block, Sonar, pipeline, policies, evidence, workflows):

```bash
API_BASE=http://127.0.0.1:18080 ADMIN_PASSWORD=admin .venv/bin/python smoke_test.py
```

## 5. GitHub Pages

Pages serves `main:/docs` (Settings → Pages), and `.github/workflows/pages.yml` also publishes on every push to `docs/`. `docs/.nojekyll` keeps Jekyll out of the way. No build step — the console is plain HTML/CSS/JS.

## Security notes

- Rotate/revoke any personal access token that was ever pasted into a chat or terminal.
- Secrets live only in the deploy platform's environment (Render dashboard, Docker `-e`, etc.). `.gitignore` excludes `.env*` and data directories.
- HSTS is off by default (`CLEARFRAME_HSTS=false`) so self-signed/demo hosts don't get permanently blocked by browsers; enable it only behind a real certificate.

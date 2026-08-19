# ClearFrame

**The governance layer for AI agents.** Create agents from any stack, police every action against a signed goal manifest, and keep humans in command — with a tamper-evident audit trail for ISO 42001 / EU AI Act evidence.

- **Operator console (GitHub Pages):** [`docs/`](docs/) — paper/ink UI with an instant in-browser demo (no backend needed)  
  Live: https://ibrahimmukherjee-boop.github.io/ClearFrame/
- **Backend API:** [`services/api/`](services/api/) — FastAPI + Postgres running Aegis (human-in-the-loop), SafePulse (operator biometrics), TrustRegistry (agent certificates), and Sonar (threat detection)  
  One-click Render Blueprint: https://dashboard.render.com/blueprint/new?repo=https://github.com/ibrahimmukherjee-boop/ClearFrame
- **Agent protocol (Python package):** [`clearframe/`](clearframe/) — unchanged, importable as before.

## Try it in 30 seconds (no install)

1. Open https://ibrahimmukherjee-boop.github.io/ClearFrame/ and click **Launch instant demo**.
2. **Agents** — create an agent from any stack (OpenAI, Anthropic, local, custom HTTP) with a goal manifest that scopes what it may do.
3. **Pipeline** — run the full governed pipeline: goal check → SafePulse operator verification → TrustRegistry certificate → policed execution → audit.
4. **Aegis** — approve or block the tool calls the policy engine escalated for human review.
5. **Sonar / Audit** — watch threat events accumulate and inspect the per-action audit trail.

The demo runs the whole platform in your browser (localStorage state, no servers, no account). **Sign out** resets it.

## Run it for real

Two paths, both documented step-by-step in [DEPLOYMENT.md](DEPLOYMENT.md):

| Path | Time | What you get |
|---|---|---|
| [Render Blueprint](https://dashboard.render.com/blueprint/new?repo=https://github.com/ibrahimmukherjee-boop/ClearFrame) | ~5 min | Managed FastAPI + Postgres, HTTPS, health checks |
| Docker (any host) | ~10 min | `services/api/Dockerfile` + Postgres; works on any cloud or on-prem |

Then open the Pages console, expand **Live sign-in**, enter your backend URL, and sign in as `admin@erasys.local` with the password you set via `CLEARFRAME_ADMIN_PASSWORD`.

Production notes (secrets, CORS, HITL blocking mode, backups) are in [DEPLOYMENT.md](DEPLOYMENT.md#security-notes). The API refuses to boot in production with unsafe configuration (missing JWT secret, default admin password, wildcard CORS).

## Develop locally

```bash
cd services/api
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8080        # SQLite by default, Postgres via DATABASE_URL
python smoke_test.py                     # end-to-end governance flow against the running API
pytest                                   # unit + integration suites
```

## Repository layout

| Path | Contents |
|---|---|
| `clearframe/` | Open-source agent protocol package (unchanged) |
| `docs/` | GitHub Pages operator console + instant demo runtime |
| `services/api/` | FastAPI operator backend: auth, agents, pipeline, Aegis, SafePulse, TrustRegistry, Sonar, audit |
| `render.yaml` | One-click Render Blueprint (web service + Postgres) |
| `DEPLOYMENT.md` | Full deployment guide: instant demo, Render, Docker, local dev, security |

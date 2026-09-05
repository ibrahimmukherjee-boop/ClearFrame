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
6. **Agents → History / Revoke / Restore** — every change is versioned; roll back to any prior version. Soft-delete (revoke) and restore without losing the audit trail.
7. **Governance → Backup & restore** — download a point-in-time JSON backup of governance state; restore is atomic and never includes credentials or vault secrets.
8. **Federation** — run governed `SELECT` across CRM + warehouse catalogs; emails are column-masked; lineage is recorded for every result.

The demo runs the whole platform in your browser (localStorage state, no servers, no account). **Sign out** resets it.

## Enterprise data & security controls

| Control | What it does |
|---|---|
| **Transactional rollback** | Every DB write runs in a transaction; exceptions roll back automatically (SQLite + Postgres) |
| **Full CRUD** | Create / Read / Update / soft-delete (revoke) / restore for agents; create / update / disable / rollback for policies |
| **Versioned history** | Append-only snapshots of every mutation; roll back to any version (rollback is itself audited) |
| **Atomic backup/restore** | Admin export of governance tables; restore is all-or-nothing and allowlisted (never touches users, tokens, or vault secrets) |
| **Federated query gateway** | Starburst-inspired SELECT across catalogs with column masking, policy gates, and lineage |
| **Multi-tenancy** | Organisation namespaces + `X-Tenant-Id` isolation |
| **Data lineage** | Provenance graph for federated results and governed actions |
| **Idempotency keys** | Safe retries via `Idempotency-Key` on federation mutations |
| **Schema migrations** | Versioned migration registry applied at boot |
| **K8s probes** | `/api/live` + `/api/ready` for cluster orchestration |
| **Login lockout** | 5 failed attempts → 429 with Retry-After; Sonar records the brute-force event |
| **Production gate** | API refuses to boot in production without JWT secret, vault passphrase, audit secret, and Postgres |
| **Security headers** | `X-Content-Type-Options`, `X-Frame-Options`, HSTS in production |

## Run it for real

| Path | Time | Manifest |
|---|---|---|
| [Render Blueprint](https://dashboard.render.com/blueprint/new?repo=https://github.com/ibrahimmukherjee-boop/ClearFrame) | ~5 min | `render.yaml` |
| Docker Compose | ~10 min | `docker-compose.yml` (API + Postgres) |
| Kubernetes | ~20 min | `deploy/kubernetes/clearframe.yaml` |

Full instructions: [DEPLOYMENT.md](DEPLOYMENT.md) · [deploy/README.md](deploy/README.md).

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
| `services/api/` | FastAPI operator backend: auth, agents, pipeline, Aegis, SafePulse, TrustRegistry, Sonar, federation, audit |
| `docker-compose.yml` | Local/VM production-shaped stack (API + Postgres) |
| `deploy/kubernetes/` | Deployment, Service, Ingress, HPA, PDB, probes |
| `render.yaml` | One-click Render Blueprint (web service + Postgres) |
| `DEPLOYMENT.md` | Full deployment guide: instant demo, Render, Docker, K8s, local dev, security |

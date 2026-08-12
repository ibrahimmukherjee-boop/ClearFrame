# Nexus Protocol Sandbox

Local and **EC2** demo environment for the full Nexus Protocol stack.

## EC2 Quick Start (recommended — single port, no login)

```bash
cd nexus-sandbox
bash scripts/ec2-start.sh
```

Open **`http://YOUR-EC2-PUBLIC-IP:8080/`** — no login required.

### EC2 Security Group

Add an inbound rule:

| Type | Port | Source |
|------|------|--------|
| Custom TCP | **8080** | Your IP (or `0.0.0.0/0` for public demo) |

Optional: use nginx on port 80 (see `deploy/nginx-nexus.conf`).

### Why you might have seen a login page before

- **Wrong port** — the old setup used ports 8001–8080 separately; many were not open in the security group
- **ClearFrame auth** — AgentOps requires a bearer token by default; EC2 unified mode disables auth
- **Cursor/cloud proxy** — some environments show their own login when forwarding ports; use the EC2 public IP directly on port **8080**

---

## Local Quick Start (multi-process)

```bash
cd nexus-sandbox
pip install -r requirements.txt
pip install -e components/trust-registry -e components/aegis -e components/sonar
bash scripts/start-all.sh
```

Open **http://localhost:8080** (unified) or run `python3 demo/unified_app.py` directly.

---

## Stack Overview

| Service | Unified path | Role |
|---------|--------------|------|
| **Dashboard** | `/` | Web UI + pipeline demo |
| **TrustRegistry** | `/trust/` | Agent PKI |
| **Sonar** | `/sonar/` | SOC threat detection |
| **Aegis** | `/aegis/` | Human-in-the-loop |
| **ClearFrame** | `/clearframe/` | AgentOps (auth off in sandbox) |

## Using your Mac Downloads copies

If you have the repos in `~/Downloads`:

```bash
bash scripts/setup-from-mac-downloads.sh
pip install -e components/trust-registry -e components/aegis -e components/sonar
bash scripts/start-all.sh
```

Expected paths:
- `/Users/ibrahimmukherjee/Downloads/TrustRegistry-main`
- `/Users/ibrahimmukherjee/Downloads/Aegis-main`
- `/Users/ibrahimmukherjee/Downloads/Sonar-main`
- `/Users/ibrahimmukherjee/Downloads/ClearFrame-main`
- `/Users/ibrahimmukherjee/Downloads/Clearframe Stack`

## Health Check

```bash
python3 scripts/healthcheck.py
```

## Integration Test

```bash
python3 tests/test_integration.py
```

## Pipeline Flow

1. **TrustRegistry** issues an Ed25519-signed agent certificate
2. **Sonar** scans user context for prompt injection / PII
3. **ClearFrame** runs the agent session (AgentOps on :7477)
4. **Aegis** queues sensitive actions for human approval
5. Operator approves via dashboard or `POST /api/pipeline/approve`

## API Endpoints

### TrustRegistry (`:8001`)
- `GET /health`
- `GET /certificates`
- `POST /certificates/issue`
- `GET /certificates/{id}/verify`
- `POST /certificates/{id}/revoke`

### Sonar (`:8002`)
- `GET /health`
- `POST /scan`
- `GET /events`

### Aegis (`:8003`)
- `GET /health`
- `GET /queue`
- `POST /queue`
- `POST /queue/{id}/approve`
- `POST /queue/{id}/reject`

### Dashboard (`:8080`)
- `GET /` — web UI
- `GET /health` — all-service health
- `POST /api/pipeline/run` — end-to-end demo
- `POST /api/pipeline/approve` — approve HITL request

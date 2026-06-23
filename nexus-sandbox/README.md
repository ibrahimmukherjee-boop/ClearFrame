# Nexus Protocol Sandbox

Local demo environment for the full Nexus Protocol stack:

| Service | Port | Role |
|---------|------|------|
| **TrustRegistry** | 8001 | Agent PKI — issue / verify / revoke certificates |
| **Sonar** | 8002 | SOC — prompt injection, PII, policy threat detection |
| **Aegis** | 8003 | Human-in-the-loop approval queue |
| **ClearFrame** | 7477 | Agent runtime + AgentOps control plane |
| **Dashboard** | 8080 | Unified sandbox UI + pipeline demo |

## Quick Start (this workspace)

```bash
cd nexus-sandbox
pip install -r requirements.txt
pip install -e components/trust-registry -e components/aegis -e components/sonar
bash scripts/start-all.sh
```

Open **http://localhost:8080** and click **Run Pipeline**.

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

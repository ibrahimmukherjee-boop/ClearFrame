# Erasys ClearFrame Stack

Enterprise-ready deployment of the Erasys **AI Governance and Safety** platform with **real ClearFrame runtime**, **AgentOps control plane**, Postgres persistence, AES-256 vault, and HMAC audit chain.

## Architecture

```
React UI (:5173)  →  FastAPI BFF (:8080)  →  ClearFrame AgentSession + SQLite
                              ↓
                    ClearFrame AgentOps (:7477)
```

| Layer | Service | What runs locally |
|-------|---------|-------------------|
| **Agent Builder** | FastAPI `/api/agents` | SQLite agent registry + presets |
| **SafePulse** | `/api/safepulse/*` | Keystroke profile enroll/verify (SQLite) |
| **TrustRegistry** | `/api/trust/*` | Certificate issue/verify/revoke (SQLite) |
| **ClearFrame** | `/api/sessions/start` | Real `AgentSession` + GoalMonitor + audit |
| **Aegis HITL** | `/api/aegis/*` | Tool call approve/block queue |
| **Sonar SOC** | `/api/sonar/*` | Threat event store + drift detection |
| **Vault** | AES-256-GCM | Encrypted credential store |
| **Audit** | HMAC chain | Tamper-evident `data/audit.log` |
| **AgentOps** | `:7477` | Session registry + approval queue |

## Quick Start (Local)

```bash
cd ~/Desktop/ClearFrame
chmod +x start-local.sh Start-ClearFrame-Stack.command
./start-local.sh
```

Or double-click **Start-ClearFrame-Stack.command**.

Open **http://localhost:5173**

API health: **http://localhost:8080/api/health**

## Test the Full Pipeline

1. **Builder** → Save an agent (or load a preset)
2. **SafePulse** → Enroll → type *"Secure the agentic future"* → Re-authenticate
3. **TrustRegistry** → Issue Certificate
4. **ClearFrame** → Run Agent
5. **Aegis** → Approve/block flagged tool calls
6. **Sonar** → View threat feed

Or click **Run Full Pipeline** on the Overview tab.

## Enterprise Docker Deploy

```bash
cp .env.example .env
# Edit CLEARFRAME_VAULT_PASSPHRASE and CLEARFRAME_AUDIT_SECRET

docker compose up --build -d
```

Open **http://localhost:8080** (API serves built frontend + all services in one container).

Data persists in Docker volume `clearframe-data`.

## Environment Variables

See `.env.example` for all options. Key production settings:

| Variable | Default | Purpose |
|----------|---------|---------|
| `CLEARFRAME_VAULT_PASSPHRASE` | `erasys-local-dev` | Vault encryption key |
| `CLEARFRAME_AUDIT_SECRET` | auto-generated | HMAC audit chain secret |
| `CLEARFRAME_DATA_DIR` | `./backend/data` | SQLite + audit + vault storage |
| `USE_CLEARFRAME_RUNTIME` | `true` | Use real ClearFrame AgentSession |
| `USE_CLEARFRAME_OPS` | `true` | Start AgentOps on :7477 |

## GitHub (Separate Repo)

This folder is self-contained and ready to push as its own repository:

```bash
cd ~/Desktop/ClearFrame
git init
git add .
git commit -m "feat: Erasys ClearFrame Stack — local enterprise deployment"
git remote add origin https://github.com/YOUR_ORG/clearframe-stack.git
git push -u origin main
```

For GitHub Pages (static demo only, no backend):

```bash
npm run build:pages
# Enable Pages: branch main, folder /docs
```

For full stack, deploy via Docker to your cloud (AWS ECS, Azure Container Apps, etc.).

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health + runtime status |
| GET | `/api/state` | Full sandbox state |
| POST | `/api/agents` | Create/save agent |
| POST | `/api/safepulse/enroll` | Enroll biometric profile |
| POST | `/api/safepulse/verify` | Verify operator |
| POST | `/api/trust/issue` | Issue trust certificate |
| POST | `/api/sessions/start` | Run ClearFrame session |
| POST | `/api/aegis/{id}/approve` | Approve tool call |
| POST | `/api/pipeline/run` | Run full pipeline |
| GET | `/api/audit/verify` | Verify HMAC audit chain |

## Optional: Gradio PoC

Legacy tabbed demo (no persistence):

```bash
pip install -r requirements.txt
python app.py   # http://localhost:7860
```

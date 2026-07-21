# ClearFrame

> Private · Secure · Accessible by default.

ClearFrame is the open-source **AI agent OS** at the heart of **Nexus Protocol**.
Every tool call is scored for alignment, every reasoning step is captured, every
credential is encrypted, and every action is logged to a tamper-evident audit trail.

| Layer | Component | Role |
|-------|-----------|------|
| 01 Runtime | **ClearFrame** | Goal manifests, audit, reader/actor isolation |
| 02 Sonar | **Sonar SOC** | Prompt injection / PII / policy detection |
| 03 Aegis | **Aegis HITL** | Human approve / reject / terminate |
| 04 Trust | **TrustRegistry** | Ed25519 agent certificates |

---

## Deploy on EC2 (one command)

```bash
git clone -b cursor/nexus-sandbox-demo-be86 https://github.com/ibrahimmukherjee-boop/ClearFrame.git
cd ClearFrame
bash clearframe/deploy/install-ec2.sh
```

Then open:

```
http://YOUR-EC2-PUBLIC-IP:8080/
```

**Login:** none (demo mode).  
**Security group:** allow inbound **TCP 8080**.

### Docker

```bash
docker compose up --build -d
# → http://YOUR-HOST:8080/
```

---

## Local run

```bash
# from repo root
pip install -e ./clearframe \
  -e ./nexus-sandbox/components/trust-registry \
  -e ./nexus-sandbox/components/aegis \
  -e ./nexus-sandbox/components/sonar

clearframe serve --host 0.0.0.0 --port 8080
```

Open **http://localhost:8080/** — branded control plane, no login.

---

## CLI

```
clearframe serve          # Full stack + UI (recommended)
clearframe start          # AgentOps API only (:7477)
clearframe ops-start      # Alias for start
clearframe audit-verify   # Verify audit HMAC chain
clearframe version
```

---

## Why ClearFrame?

| Problem with OpenClaw / MCP | ClearFrame |
|---|---|
| Prompt injection via mixed reader/actor | Reader/Actor isolation |
| Plaintext credentials | AES-256-GCM vault |
| No audit trail | HMAC-chained audit log |
| No declared goal | Goal Monitor + auto-pause |
| No operator control | Live control plane |

## License

Apache 2.0

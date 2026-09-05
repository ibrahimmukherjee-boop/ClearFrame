"""ClearFrame — open-source AI agent governance control plane.

**ClearFrame** (this repo) is the **open-source** protocol and control plane (Apache 2.0):
agents, Aegis HITL, TrustRegistry, Sonar AI SOC, policy hub, governed data access,
multi-provider LLM gateways, managed memory, and evidence export.

**Nexus Protocol** is the Erasys **commercial** product. It includes everything in
ClearFrame **plus SafePulse** (operator behavioural biometrics). SafePulse is
demonstrated in the console for evaluation but is **not** part of the OSS ClearFrame
distribution.

## Why ClearFrame vs AgentCore / Bedrock lock-in

| Capability | ClearFrame | Typical AgentCore |
|---|---|---|
| Self-hostable control plane | Yes | Managed AWS |
| Stack-agnostic agents (Ollama, OpenAI, Anthropic, Bedrock, Azure, custom) | Yes | Bedrock-centric |
| Human-in-command (Aegis) | Yes | Partial |
| Compliance evidence (ISO 42001 / EU AI Act) | Yes | Limited |
| Federated data under policy | Governance-first gateway (Trino-compatible) | Engine-dependent |
| Managed memory | Short + long-term (self-hosted) | Deeper managed Memory |
| Cedar / OPA import | Yes | Cedar-native UX |
| OpenTelemetry export | JSONL / collector-ready | Native OTEL |
| Apache Ranger-style verify | Yes | — |

Honest gaps we still close over time: deeper Memory UX, serverless scale-out, and richer Cedar authoring. Next investments: real Postgres/REST connectors behind catalogs, Cedar/OPA UX polish, and collector-shipped OTEL.

## Instant demo (no backend)

Open the GitHub Pages console — **Try demo** runs the full pipeline in the browser:

**https://ibrahimmukherjee-boop.github.io/ClearFrame/**

1. **Pipeline** — builder → SafePulse (Nexus demo) → TrustRegistry → session → Aegis → Sonar  
2. **Agents** — create agents across Ollama / OpenAI / Anthropic / Bedrock / Azure / custom  
3. **Data** — chat questions to fetch & visualize governed catalog data (no SQL console)  
4. **AI SOC** — Sonar playbooks, containment, threat dashboard  
5. **Policies** — upload PDF/TXT/DOCX/MD → NLP hierarchy → hard enforcement + Cedar import + Ranger verify  

## Production stack

- `services/api/` — FastAPI + Postgres/SQLite  
- `docs/` — GitHub Pages operator console  
- `deploy/kubernetes/` — K8s manifests  
- `docker-compose.yml` — local full stack  

See [DEPLOYMENT.md](DEPLOYMENT.md).

## Key APIs

| Area | Endpoints |
|---|---|
| Agent data (no SQL UI) | `POST /api/data/ask`, `GET /api/data/catalogs` |
| Memory | `GET /api/memory/{session}`, `POST /api/memory/long` |
| Sonar AI SOC | `GET /api/sonar/soc`, `POST /api/sonar/scan`, `POST /api/sonar/contain` |
| Providers | `GET /api/providers`, `GET /api/providers/{id}/validate` |
| Cedar/OPA | `POST /api/policies/import` |
| Ranger verify | `POST /api/verify/ranger`, `GET /api/verify/ranger/portfolio` |
| Policy NLP | `POST /api/governance/documents/upload`, `GET /api/governance/hierarchy` |
| OTEL | `GET /api/otel/status` (+ `CLEARFRAME_OTEL_PATH` JSONL) |

Federation SQL endpoints remain for admin/engine integration; operators use **Data** chat and agent tools `data_fetch` / `data_visualize`.

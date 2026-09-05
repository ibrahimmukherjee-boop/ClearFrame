"""ClearFrame — open-source AI agent governance control plane (Apache 2.0).

**ClearFrame** is the **open-source** protocol and control plane from Erasys:
agents, Aegis HITL, TrustRegistry, Sonar AI SOC, Continuum memory, Lattice
scale-out, Mandate Studio, governed data access, multi-provider LLM gateways,
and compliance evidence.

**Nexus Protocol** is Erasys’s **closed-source** commercial product. It includes
ClearFrame capabilities **plus SafePulse** (operator behavioural biometrics) and
enterprise support. SafePulse is demonstrated in the console for evaluation but
is **not** part of the ClearFrame OSS distribution.

## ClearFrame capabilities

| Layer | Product name | Role |
|---|---|---|
| Memory | **Continuum** | Working / episodic / semantic memory, namespaces, recall |
| Scale-out | **Lattice** | Self-hosted elastic worker pool for agent jobs |
| Policy authoring | **Mandate Studio** | Structured forbid/permit + DSL + OPA/Rego import |
| HITL | **Aegis** | Human-in-command tool gating |
| SOC | **Sonar** | AI security operations centre |
| Trust | **TrustRegistry** | Agent certificates |
| Data | Agent `data_fetch` / Data chat | Governed catalog access (no SQL console) |

Hybrid / self-host story: open control plane, stack-agnostic agents (Ollama, OpenAI, Anthropic, Azure, hosted OpenAI-compatible gateways), human-in-command, compliance evidence, federated data under policy — without proprietary lock-in.

## Instant demo (no backend)

**https://ibrahimmukherjee-boop.github.io/ClearFrame/**

1. **Pipeline** — builder → SafePulse (Nexus demo) → TrustRegistry → session → Aegis → Sonar  
2. **Agents** — Ollama / OpenAI / Anthropic / hosted / Azure / custom  
3. **Data** — chat to fetch & visualize governed catalog data  
4. **Continuum / Lattice** — memory browse + elastic job pool  
5. **Policies** — NLP upload + Mandate Studio + Ranger-style verify  
6. **AI SOC** — Sonar playbooks and containment  

## Production

See [DEPLOYMENT.md](DEPLOYMENT.md). Backend: `services/api/`. Console: `docs/`.

## Key APIs

| Area | Endpoints |
|---|---|
| Continuum | `GET/POST /api/continuum`, `GET /api/continuum/browse`, `GET /api/continuum/search` |
| Lattice | `GET /api/lattice`, `POST /api/lattice/scale`, `POST /api/lattice/jobs` |
| Mandate Studio | `POST /api/mandate/author`, `POST /api/mandate/preview`, `POST /api/policies/import` |
| Data | `POST /api/data/ask`, `GET /api/data/catalogs` |
| Sonar AI SOC | `GET /api/sonar/soc`, `POST /api/sonar/scan`, `POST /api/sonar/contain` |
| Providers | `GET /api/providers` |
| Verify | `POST /api/verify/ranger`, `GET /api/verify/audit-chain` |

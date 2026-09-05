# ClearFrame / Nexus Protocol — deployment

## Product split

| | **ClearFrame** (open source) | **Nexus Protocol** (Erasys commercial) |
|---|---|---|
| License | Apache 2.0 | Commercial |
| Control plane | Agents, Aegis, TrustRegistry, Sonar AI SOC, policies, data gateway | Everything in ClearFrame |
| SafePulse | Demo-only in console (labelled commercial) | Included |
| Support | Community | Enterprise |

## Instant demo (GitHub Pages)

Open https://ibrahimmukherjee-boop.github.io/ClearFrame/ and choose **Try demo**.

Every flow works in the browser: pipeline, agents (multi-provider), SafePulse (Nexus demo), TrustRegistry, sessions, Aegis, Sonar AI SOC, policies (NLP upload + Cedar), governed **Data** chat (no SQL), governance evidence, workflows.

## Backend

`services/api/` — Dockerised FastAPI: agents, sessions, Aegis HITL, SafePulse, TrustRegistry, Sonar AI SOC, policies, governance/evidence, workflows, vault, JWT auth, managed memory, OTEL export, Cedar/OPA import, Ranger-style verify, multi-provider LLM gateways.

### Provider env vars

```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
AWS_ACCESS_KEY_ID= / AWS_REGION= / AWS_BEDROCK_ENDPOINT=
AZURE_OPENAI_API_KEY= / AZURE_OPENAI_ENDPOINT=
CUSTOM_LLM_BASE_URL= / CUSTOM_LLM_API_KEY=
OLLAMA_HOST=http://127.0.0.1:11434
CLEARFRAME_OTEL=true
CLEARFRAME_OTEL_PATH=/data/otel.jsonl
```

## Smoke & stress

```bash
cd services/api
python -m pytest -q --ignore=tests/test_stress.py
python stress_test.py
python smoke_test.py   # needs running API
```

See also `docker-compose.yml`, `deploy/kubernetes/clearframe.yaml`, and `render.yaml`.

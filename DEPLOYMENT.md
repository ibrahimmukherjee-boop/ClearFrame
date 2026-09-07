# ClearFrame / Nexus Protocol — deployment

## Product split

| | **ClearFrame** | **Nexus Protocol** |
|---|---|---|
| Source | **Open source** (Apache 2.0) | **Closed source** (Erasys commercial) |
| Includes | Continuum, Lattice, Mandate Studio, Aegis, TrustRegistry, Sonar AI SOC, governed data, multi-provider LLMs | ClearFrame capabilities **+ SafePulse** + enterprise support |
| SafePulse | Demo-labelled only (not OSS) | Included |

## Instant demo

https://ibrahimmukherjee-boop.github.io/ClearFrame/ — **Try demo**.

## Backend

`services/api/` — FastAPI control plane.

### Provider env vars

```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
HOSTED_LLM_ENDPOINT= / HOSTED_LLM_API_KEY=
AZURE_OPENAI_API_KEY= / AZURE_OPENAI_ENDPOINT=
CUSTOM_LLM_BASE_URL= / CUSTOM_LLM_API_KEY=
OLLAMA_HOST=http://127.0.0.1:11434
CLEARFRAME_OTEL=true
CLEARFRAME_OTEL_PATH=/data/otel.jsonl
CLEARFRAME_LATTICE_WORKERS=4
CLEARFRAME_LATTICE_MAX_WORKERS=32
```

### SOC / integration env vars (live playbooks)

```
SLACK_BOT_TOKEN=          # or SLACK_WEBHOOK_URL=
SLACK_SOC_CHANNEL=#soc-tier1
JIRA_BASE_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=SOC
OKTA_DOMAIN=
OKTA_API_TOKEN=
SOC_WEBHOOK_URL=
CLEARFRAME_INTEGRATIONS_REQUIRE_LIVE=false   # true = fail if connectors missing
```

Inbound SOC webhooks (normalize → SocEvent → correlate):

- `POST /api/soc/webhooks/okta`
- `POST /api/soc/webhooks/crowdstrike` (Falcon DetectionSummary-style payloads)
- `POST /api/soc/webhooks/defender` (Microsoft Defender)

Without Slack/Jira/Okta secrets, playbooks still run: ClearFrame contain/revoke are real; Slack/Jira/Okta are clearly **simulated**.

## Smoke & stress

```bash
cd services/api
.venv/bin/python -m pytest -q --ignore=tests/test_stress.py
.venv/bin/python bic_smoke_test.py
.venv/bin/python stress_test.py
```

See `docker-compose.yml`, `deploy/kubernetes/clearframe.yaml`, `render.yaml`.

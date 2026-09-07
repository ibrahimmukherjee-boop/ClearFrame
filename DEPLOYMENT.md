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
# Notify / ticketing / IdP
SLACK_BOT_TOKEN=          # or SLACK_WEBHOOK_URL=
SLACK_SOC_CHANNEL=#soc-tier1
JIRA_BASE_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=SOC
OKTA_DOMAIN=
OKTA_API_TOKEN=
SOC_WEBHOOK_URL=
PAGERDUTY_ROUTING_KEY=
SPLUNK_HEC_URL=
SPLUNK_HEC_TOKEN=

# CrowdStrike Falcon (AI SOC EDR)
FALCON_CLIENT_ID=
FALCON_CLIENT_SECRET=
FALCON_BASE_URL=https://api.crowdstrike.com

# Microsoft Defender for Endpoint
DEFENDER_TENANT_ID=
DEFENDER_CLIENT_ID=
DEFENDER_CLIENT_SECRET=

# SentinelOne
S1_BASE_URL=
S1_API_TOKEN=

CLEARFRAME_INTEGRATIONS_REQUIRE_LIVE=false   # true = fail if connectors missing
```

Inbound SOC webhooks (normalize → SocEvent → correlate):

- `POST /api/soc/webhooks/okta`
- `POST /api/soc/webhooks/crowdstrike` (Falcon DetectionSummary-style payloads)
- `POST /api/soc/webhooks/defender` (Microsoft Defender)

Outbound EDR response (live when Falcon/Defender/S1 secrets set):

- `POST /api/connectors/crowdstrike/sync` — pull detections into the AI SOC bus
- `POST /api/connectors/crowdstrike/isolate` — Falcon network contain
- `POST /api/connectors/defender/isolate` — Defender isolate

Without Slack/Jira/Okta/Falcon secrets, playbooks still run: ClearFrame contain/revoke are real; enterprise connectors are clearly **simulated**.

## Smoke & stress

```bash
cd services/api
.venv/bin/python -m pytest -q --ignore=tests/test_stress.py
.venv/bin/python bic_smoke_test.py
.venv/bin/python stress_test.py
```

See `docker-compose.yml`, `deploy/kubernetes/clearframe.yaml`, `render.yaml`.

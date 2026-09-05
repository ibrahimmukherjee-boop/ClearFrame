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

## Smoke & stress

```bash
cd services/api
python -m pytest -q --ignore=tests/test_stress.py
python stress_test.py
```

See `docker-compose.yml`, `deploy/kubernetes/clearframe.yaml`, `render.yaml`.

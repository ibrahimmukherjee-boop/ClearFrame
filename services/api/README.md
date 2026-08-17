# ClearFrame API (Render)

Docker FastAPI service for the Pages console. Keeps the OSS `clearframe/` package at the repo root untouched; this service lives under `services/api/` with a vendored runtime copy.

## Deploy on Render

1. Open the Blueprint link: https://dashboard.render.com/blueprint/new?repo=https://github.com/ibrahimmukherjee-boop/ClearFrame
2. Confirm `render.yaml` creates:
   - Postgres `clearframe-db` (basic-256mb)
   - Web service `clearframe-api` (Docker, starter)
3. Apply. Render generates `CLEARFRAME_JWT_SECRET`, vault/audit secrets, and `CLEARFRAME_ADMIN_PASSWORD`.
4. Copy the generated admin password from the service **Environment** tab.
5. Health check: `https://clearframe-api.onrender.com/api/health`
6. Sign in on Pages with `admin@erasys.local` and that password. Backend URL defaults to the Render host.

CORS is set to `https://ibrahimmukherjee-boop.github.io`. Ollama is disabled in production; tool/session governance still runs.

## Local smoke

```bash
cd services/api
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
CLEARFRAME_ENV=development CLEARFRAME_AUTH=true USE_OLLAMA=false USE_CLEARFRAME_OPS=false \
  CLEARFRAME_API_PORT=18080 .venv/bin/python run.py
# other terminal
API_BASE=http://127.0.0.1:18080 ADMIN_PASSWORD=admin .venv/bin/python smoke_test.py
```

Dev login defaults: `admin@erasys.local` / `admin`.

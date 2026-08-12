# Deploy NexusProtocol / ClearFrame

The **main application** lives in [`platform/`](platform/) — the enterprise
build: a React frontend and a FastAPI backend (25+ governance services, OIDC/JWT
auth, ISO 42001 / EU AI Act / NIST / OWASP compliance, Aegis HITL, Sonar, Trust
Registry, audit chain) compiled into **one container**. The backend serves the
SPA at `/` and the API at `/api` — one service, one URL, no AWS.

## Fastest path — Render (free-tier capable, permanent HTTPS)

1. Push this repo to GitHub.
2. Render → New → **Blueprint** → pick the repo (reads [`render.yaml`](render.yaml)).
   It builds `platform/Dockerfile` and runs the whole stack, generating secure
   secrets and an admin password automatically.
3. Open the URL, sign in as `admin@erasys.local` with the generated
   `CLEARFRAME_ADMIN_PASSWORD` (Render dashboard → Environment).

## Local / any VPS (Docker)

```bash
CLEARFRAME_ADMIN_PASSWORD=choose-a-strong-password docker compose up --build -d
# → http://localhost:8080   (sign in: admin@erasys.local / that password)
```

## Local (no Docker)

```bash
cd platform
npm install && npm run build          # builds the SPA
cp -r dist backend/static
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
CLEARFRAME_ADMIN_PASSWORD=choose-a-strong-password CLEARFRAME_RELOAD=false python run.py
# → http://localhost:8080
```

## Other no-AWS options

| Platform | Notes |
|----------|-------|
| Fly.io | `cd platform && fly launch --dockerfile Dockerfile` |
| Hugging Face Spaces | Docker SDK space from `platform/`, `app_port: 8080` |
| Railway | Deploy from GitHub, root `platform/`, injects `$PORT` |

## Login

- Local dev with no `CLEARFRAME_ADMIN_PASSWORD`: seeds `admin@erasys.local` / `admin`.
- Any deploy with `CLEARFRAME_ADMIN_PASSWORD` set: that password is used (never admin/admin).
- Production (`CLEARFRAME_ENV=production`): requires unique secrets + PostgreSQL `DATABASE_URL`.

## Health

```bash
curl -s https://YOUR-URL/api/health | python3 -m json.tool
```

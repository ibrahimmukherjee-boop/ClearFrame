# Hosting NexusProtocol / ClearFrame

The product is **two deployable parts**. Pick the split that suits you.

```
   ┌─────────────────────────────┐        ┌──────────────────────────────┐
   │  Frontend (static SPA)      │  HTTPS │  Backend (FastAPI, one image) │
   │  GitHub Pages  or  Vercel   │ ─────▶ │  Render / Fly / Railway       │
   │  (I host this — permanent)  │  /api  │  (your account — one click)   │
   └─────────────────────────────┘        └──────────────────────────────┘
                     │                                    │
        connect field / VITE_API_URL          SQLite on a persistent disk
```

Or run **everything in one container** (backend also serves the SPA) — simplest.

---

## Option A — Single container (simplest, one URL)

Render Blueprint (permanent HTTPS, free-tier capable):

1. Push this repo to GitHub.
2. Render → New → **Blueprint** → pick the repo (reads [`render.yaml`](render.yaml)).
   It builds `platform/Dockerfile`, generates secrets + an admin password, and
   serves the SPA and API from one service.
3. Open the URL, sign in as `admin@erasys.local` (password in Render →
   Environment → `CLEARFRAME_ADMIN_PASSWORD`).

Local equivalent:

```bash
CLEARFRAME_ADMIN_PASSWORD=strong-pw docker compose up --build -d   # → http://localhost:8080
```

## Option B — Split: GitHub Pages (frontend) + Render (backend)

**Frontend on GitHub Pages** is deployed automatically by
[`.github/workflows/pages.yml`](.github/workflows/pages.yml) on every push
(and is mirrored to `docs/` for the legacy Pages source). Live at:

```
https://ibrahimmukherjee-boop.github.io/ClearFrame/
```

**Backend on Render** — Option A's blueprint. Then connect them one of two ways:

- On the Pages login screen, paste your backend URL into the **Connect a
  backend** field (saved in your browser), or
- Set a repo **variable** `VITE_API_URL = https://your-backend.onrender.com/api`
  so the Pages build hardwires it (no per-user step).

## Option C — Vercel (frontend) + Render (backend)

Import the repo in Vercel, set **Root Directory = `platform`** (uses
[`platform/vercel.json`](platform/vercel.json)), and add env
`VITE_API_URL = https://your-backend.onrender.com/api`.

---

## Why not the backend on Pages/Vercel-serverless?

The backend keeps a tamper-evident SQLite audit chain (WAL), a background
ClearFrame ops server, and long-lived session/governance state. That needs a
persistent container, not ephemeral serverless — so the backend runs on a
container PaaS (Render/Fly/Railway) while the static SPA can live anywhere.

## Login

- With `CLEARFRAME_ADMIN_PASSWORD` set (any deploy): that password is used.
- Local dev without it: seeds `admin@erasys.local` / `admin`.
- Production (`CLEARFRAME_ENV=production`): unique secrets + PostgreSQL required.

## Health

```bash
curl -s https://YOUR-BACKEND/api/health | python3 -m json.tool
```

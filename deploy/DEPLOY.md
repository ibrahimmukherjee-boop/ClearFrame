# Deploying NexusProtocol — the full stack, no AWS

NexusProtocol is **one service**: the `clearframe serve` gateway runs the
runtime, mounts TrustRegistry / Sonar / Aegis, and serves the operator console
at `/`. Everything is same-origin, so there are no cross-service or CORS
mistakes to make — you deploy a single container and get a working URL.

```
                    ┌──────────────────────────────────────────┐
   HTTPS  ───────▶  │  NexusProtocol gateway (one container)     │
                    │                                            │
                    │   /            operator console (UI)       │
                    │   /api/loop    autonomous governed loop     │
                    │   /api/agents  agent creation               │
                    │   /trust /api/trust   TrustRegistry (Ed25519)│
                    │   /sonar /api/sonar   Sonar SOC             │
                    │   /aegis /api/aegis   Aegis HITL            │
                    │   /api/policies       policy packs          │
                    │   /api/bench          governance benchmark  │
                    │   /health             all-service health    │
                    └──────────────────────────────────────────┘
                              persists to /data/nexus
```

The container reads `$PORT` (injected by every PaaS below) and falls back to
8080. Demo mode (`CLEARFRAME_DEMO=1`) means no login; set it to `0` to require a
bearer token (written to `~/.clearframe/gateway-token`).

## Recommended: Render (free, permanent HTTPS, one click)

1. Push this repo to GitHub (see "Get the code up" below).
2. Render → **New** → **Blueprint** → select the repo. Render reads
   [`render.yaml`](../render.yaml), builds the Dockerfile, and deploys.
3. Open the service URL — the full console loads and works.

No CLI, no AWS, no servers to manage. Free instances sleep when idle and wake on
the next request; add a paid instance or a cron ping to keep it always-on.

## Alternative: Hugging Face Spaces (free, always-on-ish)

See [`deploy/huggingface-space-README.md`](huggingface-space-README.md). Docker
SDK Space, `app_port: 8080`. Good for a permanent public demo at no cost.

## Alternative: Fly.io (global edge, tiny always-on VM)

```bash
fly launch --no-deploy --copy-config --name nexusprotocol
fly volumes create nexus_data --size 1
fly deploy
```

Config is in [`fly.toml`](../fly.toml).

## Alternative: Railway

Railway auto-detects the `Dockerfile`. New Project → Deploy from GitHub repo →
it builds and runs. Set `CLEARFRAME_DEMO=1`. Railway injects `$PORT`.

## Any VPS or your own machine (Docker)

```bash
docker compose up --build -d      # → http://localhost:8080
```

Or without Docker:

```bash
pip install -e ./clearframe \
  -e ./nexus-sandbox/components/trust-registry \
  -e ./nexus-sandbox/components/aegis \
  -e ./nexus-sandbox/components/sonar
clearframe serve --host 0.0.0.0 --port 8080
```

## Get the code up (from your Desktop copy)

This repo already contains the full working stack. If your local Desktop copy
has changes you want deployed, push them first:

```bash
cd ~/Desktop/ClearFrame
git init 2>/dev/null; git add -A
git commit -m "sync desktop working copy"
git branch -M main
git remote add origin https://github.com/ibrahimmukherjee-boop/ClearFrame.git 2>/dev/null \
  || git remote set-url origin https://github.com/ibrahimmukherjee-boop/ClearFrame.git
git push -u origin main            # or push to a branch and open a PR
```

Then deploy with any option above. The deployed URL is the real product — the
GitHub Pages site is only a login/front-end that can point at it.

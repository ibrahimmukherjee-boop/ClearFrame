# Deploy NexusProtocol

**One container, one URL, the whole stack — no AWS.**

The `clearframe serve` gateway runs the runtime and serves the operator console
plus TrustRegistry, Sonar, Aegis, agent creation, policies, and the governance
benchmark — all same-origin, so nothing to misconfigure.

## Fastest path — Render (free, permanent HTTPS)

1. Push this repo to GitHub.
2. Render → New → **Blueprint** → pick the repo (it reads `render.yaml`).
3. Open the URL. Done — login is off in demo mode.

## Other no-AWS options

| Platform | Config | Notes |
|----------|--------|-------|
| Hugging Face Spaces | `deploy/huggingface-space-README.md` | free, Docker SDK, `app_port: 8080` |
| Fly.io | `fly.toml` | global edge, tiny always-on VM |
| Railway | auto-detects `Dockerfile` | injects `$PORT` |
| Any VPS / laptop | `docker compose up --build -d` | → http://localhost:8080 |

Full walkthrough and architecture diagram: [`deploy/DEPLOY.md`](deploy/DEPLOY.md).

## Login

Demo mode (default) has **no login**. Set `CLEARFRAME_DEMO=0` to require a
bearer token (written to `~/.clearframe/gateway-token`).

## Health check

```bash
curl -s https://YOUR-URL/health | python3 -m json.tool
```

Expect `"status": "ok"` with all four services `"ok": true`.

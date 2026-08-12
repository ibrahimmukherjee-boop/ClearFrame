# Hosting NexusProtocol / ClearFrame — all on GitHub

Everything runs from this GitHub repository. No Vercel, no Render, no AWS
required.

```
 ┌───────────────────────────────────────────────────────────────────────┐
 │                              GitHub                                   │
 │                                                                       │
 │  GitHub Pages ── docs/ console, fully working (in-browser engine)     │
 │  GitHub Actions ─ CI (tests + lint) and the Pages deploy              │
 │  GitHub Codespaces ─ one-click full stack (API + SPA in a container)  │
 └───────────────────────────────────────────────────────────────────────┘
```

## 1. GitHub Pages — the working console (zero setup)

[`.github/workflows/pages.yml`](.github/workflows/pages.yml) deploys the
static console in [`docs/`](docs/) on every push to `main`. Live at:

```
https://ibrahimmukherjee-boop.github.io/ClearFrame/
```

One-time repo setting: **Settings → Pages → Source → GitHub Actions.**

The console is *fully functional on Pages alone*: the demo runtime
(`docs/engine.js`) is a real policy engine that runs in the browser —
policy packs evaluate actions, sensitive actions sink into the
human-approval dip, and everything lands in a hash-chained audit log.
Sign in, or press **Enter the live demo**.

## 2. GitHub Codespaces — the full stack (Docker on GitHub)

GitHub Pages cannot run containers, but GitHub Codespaces can — it is
GitHub's hosted Docker. [`.devcontainer/devcontainer.json`](.devcontainer/devcontainer.json)
sets everything up:

1. Repo page → **Code → Codespaces → Create codespace on main**.
2. When it finishes building: `cd platform && npm run dev:all`
3. Open the forwarded port **5173**. Login: `admin@erasys.local` / `admin`.

To drive the Pages console with this backend: make port **8080** public
(Ports panel → right-click → Port visibility → Public), then paste the
forwarded 8080 URL into the console's **Live gateway** connection bar.

## 3. GitHub Actions — CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push
and pull request:

- `clearframe` library test suite (pytest)
- `platform/backend` ISO 42001 unit suite (pytest)
- `platform` frontend lint + production build

## Local development

```bash
cd platform && ./start-local.sh    # or: npm run dev:all
# UI  → http://localhost:5173   (login admin@erasys.local / admin)
# API → http://127.0.0.1:8080/api/health
```

Single container (self-hosting anywhere Docker runs):

```bash
CLEARFRAME_ADMIN_PASSWORD=strong-pw docker compose up --build -d   # → http://localhost:8080
```

## Health

```bash
curl -s http://127.0.0.1:8080/api/health | python3 -m json.tool
```

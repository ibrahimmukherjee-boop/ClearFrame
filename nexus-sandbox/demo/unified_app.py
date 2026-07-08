#!/usr/bin/env python3
"""
Nexus Protocol — unified EC2 gateway.

Single process, single port, no login. All stack services mounted under one host:
  /              Dashboard UI
  /trust/        TrustRegistry
  /sonar/        Sonar SOC
  /aegis/        Aegis HITL
  /clearframe/   ClearFrame AgentOps (auth disabled in sandbox mode)
  /health        Aggregated health check
  /api/pipeline  End-to-end demo
"""

from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Ensure component packages are importable when run directly
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [
    str(ROOT / "components" / "trust-registry"),
    str(ROOT / "components" / "aegis"),
    str(ROOT / "components" / "sonar"),
    str(ROOT.parent / "clearframe" / "clearframe"),
]

from aegis.server import create_app as create_aegis_app
from sonar.server import create_app as create_sonar_app
from trust_registry.server import create_app as create_trust_app

NEXUS_HOME = Path(os.getenv("NEXUS_HOME", Path.home() / ".nexus"))
NEXUS_PORT = int(os.getenv("NEXUS_PORT", "8080"))
PUBLIC_HOST = os.getenv("NEXUS_PUBLIC_HOST", "")


def _detect_public_host() -> str:
    if PUBLIC_HOST:
        return PUBLIC_HOST
    try:
        resp = httpx.get("http://169.254.169.254/latest/meta-data/public-ipv4", timeout=1.0)
        if resp.status_code == 200 and resp.text.strip():
            return resp.text.strip()
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        host = s.getsockname()[0]
        s.close()
        return host
    except Exception:
        return "127.0.0.1"


def _create_clearframe_app() -> FastAPI:
    try:
        from clearframe.core.config import OpsConfig
        from clearframe.ops.server import create_ops_app

        ops = OpsConfig(
            host="0.0.0.0",
            port=NEXUS_PORT,
            require_auth=False,
            cors_origins=["*"],
        )
        app, _token = create_ops_app(ops)
        return app
    except Exception:
        fallback = FastAPI(title="ClearFrame Sandbox")

        @fallback.get("/")
        def root() -> dict[str, str]:
            return {"service": "ClearFrame AgentOps", "version": "sandbox", "auth": "disabled"}

        @fallback.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok", "service": "clearframe", "auth": "disabled"}

        return fallback


def _loopback_base() -> str:
    port_suffix = "" if NEXUS_PORT in (80, 443) else f":{NEXUS_PORT}"
    return f"http://127.0.0.1{port_suffix}"


def _public_url(request: Request) -> str:
    host = request.headers.get("host", f"localhost:{NEXUS_PORT}")
    scheme = request.headers.get("x-forwarded-proto", "http")
    return f"{scheme}://{host}"


# ── Build unified application ─────────────────────────────────────────────────

app = FastAPI(title="Nexus Protocol", version="0.1.0", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

NEXUS_HOME.mkdir(parents=True, exist_ok=True)
app.mount("/trust", create_trust_app(NEXUS_HOME / "trust-registry.json"))
app.mount("/sonar", create_sonar_app(NEXUS_HOME / "sonar.json"))
app.mount("/aegis", create_aegis_app(NEXUS_HOME / "aegis.json"))
app.mount("/clearframe", _create_clearframe_app())


class PipelineRequest(BaseModel):
    agent_name: str = "SupportBot v2"
    goal: str = "Process customer support tickets with 95% accuracy"
    user_prompt: str = "Customer asks for refund status on order #4291"
    sensitive_action: str = 'Draft response: "Your refund of $499.99 has been processed."'


class ApproveBody(BaseModel):
    request_id: str
    approved: bool = True
    note: str = ""


@app.get("/health")
async def health(request: Request) -> dict:
    base = _loopback_base()
    services = {
        "trust_registry": f"{base}/trust/health",
        "sonar": f"{base}/sonar/health",
        "aegis": f"{base}/aegis/health",
        "clearframe": f"{base}/clearframe/",
    }
    results: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in services.items():
            try:
                r = await client.get(url)
                results[name] = {"ok": r.status_code == 200, "detail": r.json()}
            except Exception as exc:
                results[name] = {"ok": False, "detail": str(exc)}
    all_ok = all(v["ok"] for v in results.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "mode": "ec2-unified",
        "auth_required": False,
        "public_url": _public_url(request),
        "services": results,
    }


@app.post("/api/pipeline/run")
async def run_pipeline(body: PipelineRequest, request: Request) -> dict:
    base = _loopback_base()
    async with httpx.AsyncClient(timeout=15.0) as client:
        cert_resp = await client.post(f"{base}/trust/certificates/issue", json={
            "name": body.agent_name,
            "version": "1.0.0",
            "owner": "Nexus Sandbox",
            "trust_level": "STANDARD",
            "validity_days": 1,
            "capabilities": {
                "can_make_http_requests": True,
                "allowed_tools": ["web_search", "send_email"],
            },
        })
        if cert_resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"TrustRegistry: {cert_resp.text}")
        cert = cert_resp.json()

        sonar = (await client.post(f"{base}/sonar/scan", json={
            "agent": body.agent_name,
            "prompt": body.user_prompt,
            "model": "gpt-4o",
        })).json()
        if sonar.get("blocked"):
            return {"status": "blocked_by_sonar", "certificate": cert, "sonar": sonar}

        action_scan = (await client.post(f"{base}/sonar/scan", json={
            "agent": body.agent_name,
            "prompt": body.sensitive_action,
            "response": body.sensitive_action,
            "model": "gpt-4o",
        })).json()

        hitl = (await client.post(f"{base}/aegis/queue", json={
            "agent_id": cert.get("certificate_id", "agent-1"),
            "agent_name": body.agent_name,
            "session_id": f"sess-{int(time.time())}",
            "type": "approval",
            "payload": body.sensitive_action,
            "timeout_seconds": 3600,
        })).json()

        return {
            "status": "awaiting_hitl",
            "goal": body.goal,
            "certificate": cert,
            "sonar_context_scan": sonar,
            "sonar_action_scan": action_scan,
            "hitl_request": hitl,
        }


@app.post("/api/pipeline/approve")
async def approve_hitl(body: ApproveBody, request: Request) -> dict:
    base = _loopback_base()
    endpoint = "approve" if body.approved else "reject"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(f"{base}/aegis/queue/{body.request_id}/{endpoint}", json={
            "approved": body.approved,
            "reviewer": "ec2-operator",
            "note": body.note,
        })
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return {"status": "decided", "result": r.json()}


@app.get("/api/stack")
async def stack_status(request: Request) -> dict:
    base = _loopback_base()
    async with httpx.AsyncClient(timeout=10.0) as client:
        trust = (await client.get(f"{base}/trust/certificates")).json()
        sonar = (await client.get(f"{base}/sonar/events?limit=10")).json()
        aegis = (await client.get(f"{base}/aegis/queue")).json()
    return {"trust_entries": trust, "sonar_events": sonar, "hitl_queue": aegis}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> str:
    return DASHBOARD_HTML.replace("{{PUBLIC_URL}}", _public_url(request))


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nexus Protocol — Sandbox</title>
  <style>
    :root { --bg:#0d0d0b; --surface:#1a1916; --text:#e8e6e1; --muted:#7a7870; --primary:#4f98a3; --ok:#6daa45; --err:#dd6974; }
    * { box-sizing:border-box; margin:0; padding:0; }
    body { font-family: Inter, system-ui, sans-serif; background:var(--bg); color:var(--text); padding:24px; max-width:1200px; margin:0 auto; }
    h1 { font-size:1.6rem; margin-bottom:4px; }
    .sub { color:var(--muted); margin-bottom:8px; }
    .url { color:var(--primary); font-family:monospace; font-size:.85rem; margin-bottom:20px; word-break:break-all; }
    .banner { background:rgba(109,170,69,.12); border:1px solid rgba(109,170,69,.3); color:var(--ok); padding:10px 14px; border-radius:8px; margin-bottom:20px; font-size:.9rem; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px; margin-bottom:24px; }
    .card { background:var(--surface); border:1px solid rgba(255,255,255,.08); border-radius:12px; padding:16px; }
    .card h2 { font-size:.8rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin-bottom:10px; }
    .badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:.75rem; font-weight:600; }
    .ok { background:rgba(109,170,69,.2); color:var(--ok); }
    .bad { background:rgba(221,105,116,.2); color:var(--err); }
    button { background:var(--primary); color:#0d0d0b; border:none; padding:10px 16px; border-radius:8px; font-weight:600; cursor:pointer; margin:4px 8px 4px 0; }
    button.secondary { background:transparent; color:var(--text); border:1px solid rgba(255,255,255,.15); }
    button.danger { background:var(--err); color:#fff; }
    pre { background:#111; padding:12px; border-radius:8px; overflow:auto; font-size:.72rem; max-height:280px; white-space:pre-wrap; }
    .actions { margin-top:12px; display:none; }
    .actions.visible { display:block; }
  </style>
</head>
<body>
  <h1>Nexus Protocol Sandbox</h1>
  <p class="sub">TrustRegistry → Sonar → ClearFrame → Aegis</p>
  <p class="url">{{PUBLIC_URL}}</p>
  <div class="banner">No login required — open sandbox demo for EC2 / remote access.</div>
  <div class="grid" id="health"><div class="card"><h2>Loading</h2><p class="sub">Checking services…</p></div></div>
  <div class="card" style="margin-bottom:16px">
    <h2>Pipeline Demo</h2>
    <p style="margin-bottom:12px;color:var(--muted);font-size:.9rem">
      Issues a trust certificate, runs Sonar threat scan, queues Aegis human approval.
    </p>
    <button onclick="runPipeline()">Run Pipeline</button>
    <button class="secondary" onclick="refresh()">Refresh Status</button>
    <div class="actions" id="hitl-actions">
      <button onclick="approveHitl(true)">Approve HITL</button>
      <button class="danger" onclick="approveHitl(false)">Reject HITL</button>
    </div>
  </div>
  <div class="card" id="pipeline-result"><h2>Last Result</h2><pre>Click "Run Pipeline" to start.</pre></div>
  <script>
    let pendingHitlId = null;

    async function refresh() {
      try {
        const h = await fetch('/health').then(r => r.json());
        document.getElementById('health').innerHTML = Object.entries(h.services).map(([name, s]) =>
          `<div class="card"><h2>${name}</h2><span class="badge ${s.ok?'ok':'bad'}">${s.ok?'online':'offline'}</span><pre>${JSON.stringify(s.detail,null,2)}</pre></div>`
        ).join('');
      } catch (e) {
        document.getElementById('health').innerHTML = `<div class="card"><h2>Error</h2><pre>${e}</pre></div>`;
      }
    }

    async function runPipeline() {
      const r = await fetch('/api/pipeline/run', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'}).then(r=>r.json());
      document.getElementById('pipeline-result').innerHTML = '<h2>Last Result</h2><pre>'+JSON.stringify(r,null,2)+'</pre>';
      pendingHitlId = r.hitl_request?.id || null;
      document.getElementById('hitl-actions').classList.toggle('visible', !!pendingHitlId);
      refresh();
    }

    async function approveHitl(approved) {
      if (!pendingHitlId) return;
      const d = await fetch('/api/pipeline/approve', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({request_id: pendingHitlId, approved, note: approved ? 'Approved on EC2 sandbox' : 'Rejected on EC2 sandbox'})
      }).then(r=>r.json());
      document.getElementById('pipeline-result').innerHTML += '<pre>'+JSON.stringify(d,null,2)+'</pre>';
      pendingHitlId = null;
      document.getElementById('hitl-actions').classList.remove('visible');
      refresh();
    }

    refresh();
    setInterval(refresh, 20000);
  </script>
</body>
</html>"""


def main() -> None:
    host = os.getenv("NEXUS_HOST", "0.0.0.0")
    public = _detect_public_host()
    port_suffix = "" if NEXUS_PORT in (80, 443) else f":{NEXUS_PORT}"
    print("")
    print("=" * 58)
    print("  Nexus Protocol Sandbox (EC2 unified gateway)")
    print("  NO LOGIN REQUIRED")
    print(f"  Open: http://{public}{port_suffix}/")
    print(f"  Bind: {host}:{NEXUS_PORT}")
    print("=" * 58)
    print("")
    uvicorn.run(app, host=host, port=NEXUS_PORT, log_level="info")


if __name__ == "__main__":
    main()

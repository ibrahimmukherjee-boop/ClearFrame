#!/usr/bin/env python3
"""Nexus Protocol — unified sandbox orchestrator and demo dashboard."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
COMPONENTS = ROOT / "components"

TRUST_URL = os.getenv("TRUST_REGISTRY_URL", "http://127.0.0.1:8001")
SONAR_URL = os.getenv("SONAR_URL", "http://127.0.0.1:8002")
AEGIS_URL = os.getenv("AEGIS_URL", "http://127.0.0.1:8003")
CLEARFRAME_URL = os.getenv("CLEARFRAME_URL", "http://127.0.0.1:7477")

app = FastAPI(title="Nexus Protocol Sandbox", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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
async def health() -> dict:
    services = {
        "trust_registry": TRUST_URL,
        "sonar": SONAR_URL,
        "aegis": AEGIS_URL,
        "clearframe": CLEARFRAME_URL,
    }
    results: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, url in services.items():
            try:
                r = await client.get(url if name != "clearframe" else f"{CLEARFRAME_URL}/")
                results[name] = {"ok": r.status_code == 200, "detail": r.json()}
            except Exception as exc:
                results[name] = {"ok": False, "detail": str(exc)}
    all_ok = all(v["ok"] for v in results.values())
    return {"status": "ok" if all_ok else "degraded", "services": results}


@app.get("/api/stack")
async def stack_status() -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        trust = (await client.get(f"{TRUST_URL}/certificates")).json()
        sonar = (await client.get(f"{SONAR_URL}/events?limit=10")).json()
        aegis = (await client.get(f"{AEGIS_URL}/queue")).json()
    return {"trust_entries": trust, "sonar_events": sonar, "hitl_queue": aegis}


@app.post("/api/pipeline/run")
async def run_pipeline(body: PipelineRequest) -> dict:
    """End-to-end Nexus Protocol demo: Trust → Sonar → ClearFrame → Aegis."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Issue trust certificate
        cert_resp = await client.post(f"{TRUST_URL}/certificates/issue", json={
            "name": body.agent_name,
            "version": "1.0.0",
            "owner": "Nexus Sandbox",
            "trust_level": "STANDARD",
            "validity_days": 1,
            "capabilities": {"can_make_http_requests": True, "allowed_tools": ["web_search", "send_email"]},
        })
        if cert_resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"TrustRegistry error: {cert_resp.text}")
        cert = cert_resp.json()

        # 2. Sonar scan user context
        sonar_resp = await client.post(f"{SONAR_URL}/scan", json={
            "agent": body.agent_name,
            "prompt": body.user_prompt,
            "model": "gpt-4o",
        })
        sonar = sonar_resp.json()
        if sonar.get("blocked"):
            return {"status": "blocked_by_sonar", "certificate": cert, "sonar": sonar}

        # 3. Sonar scan sensitive action (simulated tool output)
        action_scan = (await client.post(f"{SONAR_URL}/scan", json={
            "agent": body.agent_name,
            "prompt": body.sensitive_action,
            "response": body.sensitive_action,
            "model": "gpt-4o",
        })).json()

        # 4. Queue Aegis HITL approval for sensitive action
        hitl_resp = await client.post(f"{AEGIS_URL}/queue", json={
            "agent_id": cert.get("certificate_id", "agent-1"),
            "agent_name": body.agent_name,
            "session_id": f"sess-{int(time.time())}",
            "type": "approval",
            "payload": body.sensitive_action,
            "timeout_seconds": 3600,
        })
        hitl = hitl_resp.json()

        return {
            "status": "awaiting_hitl",
            "goal": body.goal,
            "certificate": cert,
            "sonar_context_scan": sonar,
            "sonar_action_scan": action_scan,
            "hitl_request": hitl,
        }


@app.post("/api/pipeline/approve")
async def approve_hitl(body: ApproveBody) -> dict:
    endpoint = "approve" if body.approved else "reject"
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(f"{AEGIS_URL}/queue/{body.request_id}/{endpoint}", json={
            "approved": body.approved,
            "reviewer": "sandbox-operator",
            "note": body.note,
        })
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return {"status": "decided", "result": r.json()}


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return DASHBOARD_HTML


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nexus Protocol Sandbox</title>
  <style>
    :root { --bg:#0d0d0b; --surface:#1a1916; --text:#e8e6e1; --muted:#7a7870; --primary:#4f98a3; --ok:#6daa45; --warn:#e8af34; --err:#dd6974; }
    * { box-sizing:border-box; margin:0; padding:0; }
    body { font-family: Inter, system-ui, sans-serif; background:var(--bg); color:var(--text); padding:24px; }
    h1 { font-size:1.6rem; margin-bottom:8px; }
    .sub { color:var(--muted); margin-bottom:24px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; margin-bottom:24px; }
    .card { background:var(--surface); border:1px solid rgba(255,255,255,.08); border-radius:12px; padding:16px; }
    .card h2 { font-size:.85rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin-bottom:12px; }
    .badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:.75rem; font-weight:600; }
    .ok { background:rgba(109,170,69,.2); color:var(--ok); }
    .bad { background:rgba(221,105,116,.2); color:var(--err); }
    button { background:var(--primary); color:#0d0d0b; border:none; padding:10px 16px; border-radius:8px; font-weight:600; cursor:pointer; margin-right:8px; }
    button.secondary { background:transparent; color:var(--text); border:1px solid rgba(255,255,255,.15); }
    pre { background:#111; padding:12px; border-radius:8px; overflow:auto; font-size:.75rem; max-height:240px; }
    .stack { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }
    .stack span { padding:4px 10px; border-radius:20px; font-size:.75rem; background:rgba(79,152,163,.15); color:var(--primary); }
  </style>
</head>
<body>
  <h1>Nexus Protocol Sandbox</h1>
  <p class="sub">Local demo — TrustRegistry → Sonar → ClearFrame → Aegis</p>
  <div class="stack">
    <span>TrustRegistry :8001</span><span>Sonar :8002</span><span>Aegis :8003</span><span>ClearFrame :7477</span><span>Dashboard :8080</span>
  </div>
  <div class="grid" id="health"></div>
  <div class="card" style="margin-bottom:16px">
    <h2>Pipeline Demo</h2>
    <p style="margin-bottom:12px;color:var(--muted);font-size:.9rem">Runs the full trust chain: issue cert → Sonar scan → Aegis HITL queue.</p>
    <button onclick="runPipeline()">Run Pipeline</button>
    <button class="secondary" onclick="refresh()">Refresh Status</button>
  </div>
  <div class="card" id="pipeline-result"><h2>Last Result</h2><pre>Click "Run Pipeline" to start.</pre></div>
  <script>
    async function refresh() {
      const h = await fetch('/health').then(r=>r.json());
      const el = document.getElementById('health');
      el.innerHTML = Object.entries(h.services).map(([name, s]) =>
        `<div class="card"><h2>${name}</h2><span class="badge ${s.ok?'ok':'bad'}">${s.ok?'online':'offline'}</span><pre>${JSON.stringify(s.detail,null,2)}</pre></div>`
      ).join('');
    }
    async function runPipeline() {
      const r = await fetch('/api/pipeline/run', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({})}).then(r=>r.json());
      document.getElementById('pipeline-result').innerHTML = '<h2>Last Result</h2><pre>'+JSON.stringify(r,null,2)+'</pre>';
      if (r.hitl_request?.id) {
        const id = r.hitl_request.id;
        if (confirm('Approve HITL request '+id+'?')) {
          const d = await fetch('/api/pipeline/approve', {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({request_id:id, approved:true, note:'Approved in sandbox demo'})}).then(r=>r.json());
          document.getElementById('pipeline-result').innerHTML += '<pre>'+JSON.stringify(d,null,2)+'</pre>';
        }
      }
      refresh();
    }
    refresh();
    setInterval(refresh, 15000);
  </script>
</body>
</html>"""


def _popen(cmd: list[str], cwd: Path | None = None) -> subprocess.Popen:
    return subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_services() -> list[subprocess.Popen]:
    py = sys.executable
    procs: list[subprocess.Popen] = []
    procs.append(_popen([py, "-m", "trust_registry.cli", "--host", "0.0.0.0", "--port", "8001"],
                        cwd=COMPONENTS / "trust-registry"))
    procs.append(_popen([py, "-m", "sonar.cli", "--host", "0.0.0.0", "--port", "8002"],
                        cwd=COMPONENTS / "sonar"))
    procs.append(_popen([py, "-m", "aegis.cli", "--host", "0.0.0.0", "--port", "8003"],
                        cwd=COMPONENTS / "aegis"))
    cf_path = ROOT.parent / "clearframe" / "clearframe"
    export_path = os.environ.get("PATH", "")
    if shutil.which("clearframe"):
        procs.append(_popen(["clearframe", "ops-start", "--host", "0.0.0.0", "--port", "7477"]))
    elif (cf_path / "clearframe" / "ops" / "server.py").exists():
        procs.append(subprocess.Popen(
            [py, "-c", (
                "from clearframe.core.config import ClearFrameConfig, OpsConfig; "
                "from clearframe.ops.server import create_ops_app; "
                "import uvicorn; "
                "app,_=create_ops_app(ClearFrameConfig(ops=OpsConfig(host='0.0.0.0',port=7477)).ops); "
                "uvicorn.run(app,host='0.0.0.0',port=7477,log_level='warning')"
            )],
            cwd=cf_path, env={**os.environ, "PYTHONPATH": str(cf_path)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ))
    return procs


def main() -> None:
    if "--no-start-deps" not in sys.argv:
        print("Starting Nexus Protocol services...")
        procs = start_services()
        time.sleep(3)
        print("  TrustRegistry → http://127.0.0.1:8001")
        print("  Sonar         → http://127.0.0.1:8002")
        print("  Aegis         → http://127.0.0.1:8003")
        print("  ClearFrame    → http://127.0.0.1:7477")
    else:
        procs = []
    print("  Dashboard     → http://127.0.0.1:8080")
    try:
        uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()

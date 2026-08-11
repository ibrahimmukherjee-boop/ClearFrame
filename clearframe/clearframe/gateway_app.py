"""ClearFrame unified deploy gateway — single process, no login."""

from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

WEB_DIR = Path(__file__).resolve().parent / "web" / "static"
NEXUS_HOME = Path(os.getenv("NEXUS_HOME", Path.home() / ".nexus"))
PORT = int(os.getenv("CLEARFRAME_PORT", os.getenv("NEXUS_PORT", "8080")))
HOST = os.getenv("CLEARFRAME_HOST", os.getenv("NEXUS_HOST", "0.0.0.0"))
PUBLIC_HOST = os.getenv("CLEARFRAME_PUBLIC_HOST", os.getenv("NEXUS_PUBLIC_HOST", ""))
DEMO_MODE = os.getenv("CLEARFRAME_DEMO", "1") != "0"  # no auth by default


def _repo_paths() -> list[str]:
    here = Path(__file__).resolve()
    # clearframe/clearframe/gateway_app.py → repo roots
    candidates = [
        here.parents[2] / "nexus-sandbox" / "components" / "trust-registry",
        here.parents[2] / "nexus-sandbox" / "components" / "aegis",
        here.parents[2] / "nexus-sandbox" / "components" / "sonar",
        here.parents[3] / "nexus-sandbox" / "components" / "trust-registry",
        here.parents[3] / "nexus-sandbox" / "components" / "aegis",
        here.parents[3] / "nexus-sandbox" / "components" / "sonar",
    ]
    return [str(p) for p in candidates if p.exists()]


def _ensure_stack_imports() -> None:
    for p in _repo_paths():
        if p not in sys.path:
            sys.path.insert(0, p)


def _detect_public_host() -> str:
    if PUBLIC_HOST:
        return PUBLIC_HOST
    try:
        r = httpx.get("http://169.254.169.254/latest/meta-data/public-ipv4", timeout=1.0)
        if r.status_code == 200 and r.text.strip():
            return r.text.strip()
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _loopback() -> str:
    suffix = "" if PORT in (80, 443) else f":{PORT}"
    return f"http://127.0.0.1{suffix}"


def _public_url(request: Request) -> str:
    host = request.headers.get("host", f"{_detect_public_host()}:{PORT}")
    scheme = request.headers.get("x-forwarded-proto", "http")
    return f"{scheme}://{host}"


def _create_clearframe_ops() -> FastAPI:
    from clearframe.core.config import OpsConfig
    from clearframe.ops.server import create_ops_app

    ops = OpsConfig(
        host=HOST,
        port=PORT,
        require_auth=not DEMO_MODE,
        cors_origins=["*"],
    )
    app, token = create_ops_app(ops)
    # Always expose a public health-compatible root
    @app.get("/status")
    def status() -> dict[str, str]:
        return {"status": "ok", "service": "clearframe", "auth": "off" if DEMO_MODE else "on"}

    if DEMO_MODE:
        token_path = Path.home() / ".clearframe" / "ops-token"
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(token)
        try:
            token_path.chmod(0o600)
        except OSError:
            pass
    return app


def _gateway_token() -> str:
    token_path = Path.home() / ".clearframe" / "gateway-token"
    if token_path.exists():
        return token_path.read_text().strip()
    import secrets

    token = secrets.token_urlsafe(32)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token)
    try:
        token_path.chmod(0o600)
    except OSError:
        pass
    return token


def create_gateway() -> FastAPI:
    _ensure_stack_imports()
    NEXUS_HOME.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="NexusProtocol", version="0.5.0", docs_url=None, redoc_url=None)

    # Real bearer auth when demo mode is off (CLEARFRAME_DEMO=0).
    gateway_token = _gateway_token()

    @app.middleware("http")
    async def _auth_middleware(request: Request, call_next):
        if DEMO_MODE:
            return await call_next(request)
        path = request.url.path
        if path in ("/", "/health") or path.startswith("/static") or path.startswith("/.well-known"):
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        import secrets as _secrets

        if not auth.lower().startswith("bearer ") or not _secrets.compare_digest(
            auth.split(None, 1)[1].strip(), gateway_token
        ):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {"detail": "Bearer token required (see ~/.clearframe/gateway-token)."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount Nexus stack (optional but preferred for full deploy)
    stack_ok = {"trust": False, "sonar": False, "aegis": False}
    try:
        from trust_registry.server import create_app as create_trust

        app.mount("/trust", create_trust(NEXUS_HOME / "trust-registry.json"))
        stack_ok["trust"] = True
    except Exception as exc:
        app.state.trust_error = str(exc)

    try:
        from sonar.server import create_app as create_sonar

        app.mount("/sonar", create_sonar(NEXUS_HOME / "sonar.json"))
        stack_ok["sonar"] = True
    except Exception as exc:
        app.state.sonar_error = str(exc)

    try:
        from aegis.server import create_app as create_aegis

        app.mount("/aegis", create_aegis(NEXUS_HOME / "aegis.json"))
        stack_ok["aegis"] = True
    except Exception as exc:
        app.state.aegis_error = str(exc)

    app.mount("/api/ops", _create_clearframe_ops())
    app.state.stack_ok = stack_ok

    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

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
        base = _loopback()
        checks = {
            "clearframe": f"{base}/api/ops/health",
            "trust_registry": f"{base}/trust/health",
            "sonar": f"{base}/sonar/health",
            "aegis": f"{base}/aegis/health",
        }
        results: dict[str, dict] = {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, url in checks.items():
                try:
                    r = await client.get(url)
                    results[name] = {"ok": r.status_code == 200, "detail": r.json()}
                except Exception as exc:
                    results[name] = {"ok": False, "detail": str(exc)}
        return {
            "status": "ok" if all(v["ok"] for v in results.values()) else "degraded",
            "product": "NexusProtocol",
            "tagline": "managed intelligence — the OS for AI agents",
            "version": "0.5.0",
            "auth_required": not DEMO_MODE,
            "public_url": _public_url(request),
            "services": results,
        }

    @app.post("/api/pipeline/run")
    async def run_pipeline(payload: PipelineRequest | None = None) -> dict:
        if payload is None:
            payload = PipelineRequest()
        base = _loopback()
        async with httpx.AsyncClient(timeout=15.0) as client:
            cert = (await client.post(f"{base}/trust/certificates/issue", json={
                "name": payload.agent_name,
                "version": "1.0.0",
                "owner": "ClearFrame",
                "trust_level": "STANDARD",
                "validity_days": 1,
                "capabilities": {
                    "can_make_http_requests": True,
                    "allowed_tools": ["web_search", "send_email"],
                },
            })).json()
            sonar = (await client.post(f"{base}/sonar/scan", json={
                "agent": payload.agent_name,
                "prompt": payload.user_prompt,
                "model": "on-device",
            })).json()
            if sonar.get("blocked"):
                return {"status": "blocked_by_sonar", "certificate": cert, "sonar": sonar}
            action = (await client.post(f"{base}/sonar/scan", json={
                "agent": payload.agent_name,
                "prompt": payload.sensitive_action,
                "response": payload.sensitive_action,
                "model": "on-device",
            })).json()
            hitl = (await client.post(f"{base}/aegis/queue", json={
                "agent_id": cert.get("certificate_id", "agent-1"),
                "agent_name": payload.agent_name,
                "session_id": f"sess-{int(time.time())}",
                "type": "approval",
                "payload": payload.sensitive_action,
                "timeout_seconds": 3600,
            })).json()
            return {
                "status": "awaiting_hitl",
                "goal": payload.goal,
                "certificate": cert,
                "sonar_context_scan": sonar,
                "sonar_action_scan": action,
                "hitl_request": hitl,
            }

    @app.post("/api/pipeline/approve")
    async def approve(payload: ApproveBody = Body(...)) -> dict:
        base = _loopback()
        endpoint = "approve" if payload.approved else "reject"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{base}/aegis/queue/{payload.request_id}/{endpoint}",
                json={"approved": payload.approved, "reviewer": "operator", "note": payload.note},
            )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return {"status": "decided", "result": r.json()}

    # ── Autonomous loop API — governed plan→act→observe ───────────────────

    LOOPS_DIR = NEXUS_HOME / "checkpoints"

    @app.post("/api/loop/run")
    async def run_loop(payload: dict = Body(...)) -> dict:
        from clearframe.core.checkpoint import CheckpointStore
        from clearframe.core.config import ClearFrameConfig
        from clearframe.core.manifest import GoalManifest, ToolPermission
        from clearframe.core.session import AgentSession
        from clearframe.loop import AgentLoop, LLMTurn, ScriptedPlanner, ToolCall
        from clearframe.policy import PolicyEngine

        goal = payload.get("goal", "Answer the user question accurately")
        provider_kind = payload.get("provider", "scripted")

        async def web_search(query: str = "") -> str:
            return f"[3 results for '{query}': iso-42001.ai, nist.gov, owasp.org]"

        async def send_email(to: str = "", body: str = "") -> str:
            return f"queued email to {to}"

        async def read_file(path: str = "") -> str:
            return f"[contents of {path}]"

        tools = {"web_search": web_search, "send_email": send_email, "read_file": read_file}
        manifest = GoalManifest(
            goal=goal,
            permitted_tools=[
                ToolPermission(tool_name="web_search", max_calls_per_session=5),
                ToolPermission(tool_name="read_file", max_calls_per_session=5),
                ToolPermission(tool_name="send_email", max_calls_per_session=1),
            ],
        )
        packs = payload.get("policy_packs") or ["baseline", "iso-42001"]
        engine = PolicyEngine.with_packs(*packs)

        if provider_kind == "scripted":
            provider = ScriptedPlanner([
                LLMTurn(
                    tool_calls=[ToolCall("web_search", {"query": goal[:60]})],
                    thought="Search the web for authoritative sources on the goal.",
                ),
                LLMTurn(
                    tool_calls=[ToolCall("send_email", {
                        "to": "ops@nexusprotocol.dev",
                        "body": "Findings attached for review.",
                    })],
                    thought="Notify the operator with findings before closing.",
                ),
                LLMTurn(
                    content="Goal achieved: sources gathered and operator notified.",
                    thought="All planned work is complete.",
                ),
            ])
        elif provider_kind == "ollama":
            from clearframe.loop import OllamaChatProvider

            provider = OllamaChatProvider(model=payload.get("model", "llama3.1"))
        elif provider_kind in ("openai", "openai_compat"):
            from clearframe.loop import OpenAICompatProvider

            provider = OpenAICompatProvider(
                base_url=payload.get("base_url", "https://api.openai.com/v1"),
                api_key=os.getenv(payload.get("api_key_env", "OPENAI_API_KEY"), ""),
                model=payload.get("model", "gpt-4o-mini"),
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider '{provider_kind}'.")

        session = AgentSession(ClearFrameConfig(), manifest,
                               tool_registry=tools, policy_engine=engine)
        await session.start()
        try:
            loop = AgentLoop(session, provider, max_steps=int(payload.get("max_steps", 8)),
                             checkpoints=CheckpointStore(NEXUS_HOME / "checkpoints"))
            result = await loop.run(goal)
        finally:
            await session.end()
        return result.to_dict()

    @app.get("/api/loop/{loop_id}")
    def loop_status(loop_id: str) -> dict:
        from clearframe.core.checkpoint import CheckpointStore

        store = CheckpointStore(NEXUS_HOME / "checkpoints")
        cp = store.latest(loop_id)
        if cp is None:
            raise HTTPException(status_code=404, detail=f"No loop '{loop_id}'.")
        return {
            "loop_id": loop_id,
            "status": cp.status,
            "step": cp.step,
            "task": cp.task,
            "checkpoints": len(store.load_all(loop_id)),
            "chunks": cp.chunks,
        }

    # ── Governance benchmark ──────────────────────────────────────────────

    @app.post("/api/bench/run")
    async def bench_run() -> dict:
        from clearframe.bench import run_benchmark

        return await run_benchmark()

    @app.get("/api/bench/report")
    def bench_report() -> dict:
        path = NEXUS_HOME / "bench-report.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Run POST /api/bench/run first.")
        import json as _json

        return _json.loads(path.read_text())

    # ── Agents API — create agents from portable specs ────────────────────

    AGENTS_DIR = NEXUS_HOME / "agents"
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    @app.get("/api/agents")
    def list_agents() -> list[dict]:
        from clearframe.agents import load_spec

        out = []
        for f in sorted(AGENTS_DIR.glob("*.agent.yaml")):
            try:
                spec = load_spec(f)
                out.append({
                    "name": spec.name,
                    "goal": spec.goal,
                    "provider": spec.provider,
                    "model": spec.model,
                    "tools": [t.name for t in spec.tools],
                    "adapters": sorted({t.adapter for t in spec.tools}),
                    "policy_packs": spec.policy_packs,
                    "trust_level": spec.trust_level,
                })
            except Exception as exc:
                out.append({"name": f.stem, "error": str(exc)})
        return out

    @app.post("/api/agents")
    def create_agent(payload: dict = Body(...)) -> dict:
        from clearframe.agents.spec import AgentSpec
        from clearframe.policy import PolicyEngine, PolicyError

        try:
            spec = AgentSpec.model_validate(payload)
            PolicyEngine.with_packs(*spec.policy_packs)  # validate packs exist
        except PolicyError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid agent spec: {exc}")
        path = AGENTS_DIR / f"{spec.name}.agent.yaml"
        spec.save(path)
        return {"status": "created", "name": spec.name, "path": str(path)}

    @app.get("/api/policies")
    def list_policies() -> list[dict]:
        from clearframe.policy import load_pack, packaged_packs

        packs = []
        for name, path in packaged_packs().items():
            pack = load_pack(path)
            packs.append({
                "name": name,
                "title": pack.get("title", ""),
                "version": pack.get("version", ""),
                "description": pack.get("description", "").strip(),
                "references": pack.get("references", []),
                "rules": pack.get("rules", {}),
            })
        return packs

    @app.get("/.well-known/agent-card.json")
    def agent_card(request: Request) -> dict:
        from clearframe.adapters import a2a_card

        return a2a_card(
            name="ClearFrame Gateway",
            description="Governed agent runtime — Nexus Protocol",
            url=_public_url(request),
            version="0.4.0",
            skills=[{
                "id": "governed-execution",
                "name": "Governed tool execution",
                "description": "Execute tool calls under goal manifests, policy packs, Sonar scanning, and Aegis human oversight.",
            }],
        )

    @app.get("/api/stack")
    async def stack() -> dict:
        base = _loopback()
        async with httpx.AsyncClient(timeout=10.0) as client:
            return {
                "trust_entries": (await client.get(f"{base}/trust/certificates")).json(),
                "sonar_events": (await client.get(f"{base}/sonar/events?limit=12")).json(),
                "hitl_queue": (await client.get(f"{base}/aegis/queue")).json(),
            }

    @app.get("/", response_model=None)
    def index() -> FileResponse | HTMLResponse:
        index_path = WEB_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse("<h1>ClearFrame</h1><p>UI missing — check clearframe/web/static</p>")

    return app


def serve(host: str | None = None, port: int | None = None) -> None:
    host = host or HOST
    port = port or PORT
    public = _detect_public_host()
    suffix = "" if port in (80, 443) else f":{port}"
    print("")
    print("=" * 60)
    print("  ClearFrame  ·  Nexus Protocol")
    print("  Private · Secure · Accessible by default")
    print(f"  Open → http://{public}{suffix}/")
    print(f"  Auth → {'disabled (demo)' if DEMO_MODE else 'enabled'}")
    print("=" * 60)
    print("")
    uvicorn.run(create_gateway(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    serve()

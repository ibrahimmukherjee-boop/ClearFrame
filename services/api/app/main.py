"""Erasys ClearFrame Stack API — enterprise BFF."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from fastapi.responses import RedirectResponse

from app.config import AUTH_REQUIRED, CORS_ORIGINS, HSTS_ENABLED, OLLAMA_HOST, USE_OLLAMA
from app.database import init_db, backend_label
from app.deps import get_current_user
from app.services import agents as agents_svc
from app.services import safepulse as safepulse_svc
from app.services import trust as trust_svc
from app.services import sessions as sessions_svc
from app.services import aegis as aegis_svc
from app.services import sonar as sonar_svc
from app.services import pipeline as pipeline_svc
from app.services import vault as vault_svc
from app.services import audit as audit_svc
from app.services import roi as roi_svc
from app.services import clearframe_ops as ops_svc
from app.services import clearframe_runtime as cf_runtime
from app.services import tools as tools_svc
from app.services import governance as governance_svc
from app.services import auth as auth_svc
from app.services import oidc as oidc_svc
from app.services import policy as policy_svc
from app.services import workflows as workflows_svc
from app.services import eu_ai_act as eu_svc
from app.services import evidence_export as export_svc
from app.services import llm_agent as llm_svc
from app.services import compliance as compliance_svc
from app.services import policy_hub as policy_hub_svc
from app.services import action_audit as action_audit_svc
from app.production import enforce_or_exit, production_status


@asynccontextmanager
async def lifespan(_app: FastAPI):
    enforce_or_exit()
    from app.bootstrap import init_all
    init_all()
    vault_svc.ensure_defaults()
    ops_svc.start_ops_server()
    yield
    ops_svc.stop_ops_server()


app = FastAPI(title="Erasys AI Governance and Safety API", version="2.0.0-enterprise", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "public"
    # Only emit HSTS with a real cert. Self-signed demo hosts must not set this —
    # browsers then force HTTPS and permanently block the site.
    if HSTS_ENABLED and (
        request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"
    ):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if AUTH_REQUIRED and request.url.path.startswith("/api/") and request.url.path not in auth_svc.PUBLIC_PATHS:
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not token:
            token = request.cookies.get("access_token", "")
        if not token or not auth_svc.decode_token(token):
            return Response(content='{"detail":"Authentication required"}', status_code=401, media_type="application/json")
    return await call_next(request)


class LoginIn(BaseModel):
    email: str
    password: str


class AgentIn(BaseModel):
    name: str
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    provider: str = "ollama"
    model: str = "llama3"
    maxSteps: int = 10
    allowWeb: bool = False
    allowFs: bool = False
    allowExec: bool = False


class ProfileIn(BaseModel):
    profile: list[float]


class CertIn(BaseModel):
    trustLevel: str = "STANDARD"
    ttlHours: int = 24


class RoiIn(BaseModel):
    agents: int = 50
    operators: int = 200
    reductionPct: float = 60


class ConnectionIn(BaseModel):
    toolId: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)


class RiskIn(BaseModel):
    agentId: str | None = None
    title: str
    description: str = ""
    likelihood: int = 3
    impact: int = 3


class ToolExecuteIn(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class PolicyIn(BaseModel):
    name: str
    rule: dict[str, Any]
    priority: int = 50


class WorkflowIn(BaseModel):
    name: str
    description: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)


class VaultSecretIn(BaseModel):
    key: str
    value: str


class HitlDecisionIn(BaseModel):
    note: str = ""
    operatorId: str = "operator"


class PolicyUploadIn(BaseModel):
    title: str
    category: str
    content: str
    fileName: str = ""
    version: str = "1.0"
    parentDocId: str | None = None
    hierarchyLevel: int = 0


class PolicyCardIn(BaseModel):
    docId: str
    title: str
    content: str
    priority: int = 50
    parentCardId: str | None = None
    hierarchyOrder: int = 0
    enforce: bool = True
    tags: list[str] = Field(default_factory=list)


class FrameworkAttestIn(BaseModel):
    attested: bool = True
    notes: str = ""


@app.get("/api/health")
async def health() -> dict[str, Any]:
    ollama_ok = False
    if USE_OLLAMA:
        ollama_ok = await llm_svc.ollama_available()
    return {
        "status": "ok",
        "service": "erasys-clearframe-stack",
        "version": "2.0.0-enterprise",
        "clearframeRuntime": cf_runtime.CLEARFRAME_AVAILABLE,
        "agentOps": ops_svc.ops_status(),
        "toolCount": len(tools_svc.list_catalog()),
        "ollama": {"enabled": USE_OLLAMA, "host": OLLAMA_HOST, "available": ollama_ok, "models": llm_svc.list_models() if ollama_ok else []},
        "authRequired": AUTH_REQUIRED,
        "database": backend_label(),
        "ssoEnabled": oidc_svc.sso_enabled(),
        "production": production_status(),
    }


@app.post("/api/auth/login")
def login(body: LoginIn) -> dict[str, Any]:
    try:
        result = auth_svc.login(body.email, body.password)
    except auth_svc.LoginLocked as exc:
        raise HTTPException(
            429,
            f"Too many failed attempts. Account locked — try again in {exc.retry_after} seconds.",
            headers={"Retry-After": str(exc.retry_after)},
        )
    if not result:
        raise HTTPException(401, "Invalid credentials")
    return result


class RefreshIn(BaseModel):
    refreshToken: str


@app.post("/api/auth/refresh")
def refresh_token(body: RefreshIn) -> dict[str, Any]:
    result = auth_svc.refresh(body.refreshToken)
    if not result:
        raise HTTPException(401, "Invalid or expired refresh token")
    return result


@app.get("/api/auth/oidc/login")
def oidc_login() -> dict[str, str]:
    try:
        return oidc_svc.login_url()
    except RuntimeError as exc:
        raise HTTPException(501, str(exc)) from exc


@app.get("/api/auth/oidc/callback")
def oidc_callback(code: str = "", state: str = "") -> RedirectResponse:
    if not code or not state:
        return RedirectResponse("/?sso_error=1")
    result = oidc_svc.handle_callback(code, state)
    if not result:
        return RedirectResponse("/?sso_error=1")
    import urllib.parse
    user = urllib.parse.quote(json.dumps(result["user"]))
    return RedirectResponse(f"/#accessToken={result['accessToken']}&refreshToken={result.get('refreshToken', '')}&user={user}")


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    return user or {}


@app.get("/api/auth/users")
def list_users(user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    if user and not auth_svc.has_permission(user["role"], "*"):
        raise HTTPException(403, "Admin only")
    return auth_svc.list_users()


@app.get("/api/compliance/iso42001")
def iso42001_assessment() -> dict[str, Any]:
    return compliance_svc.run_iso42001_assessment()


@app.get("/api/compliance/production")
def production_readiness() -> dict[str, Any]:
    assessment = compliance_svc.run_iso42001_assessment()
    prod = production_status()
    return {
        "productionReady": assessment["productionReady"] and prod["configValid"],
        "iso42001": {
            "score": assessment["complianceScore"],
            "level": assessment["certificationLevel"],
            "passed": assessment["passedControls"],
            "total": assessment["totalControls"],
            "failed": assessment["failedControls"],
        },
        "production": prod,
        "checklist": {
            "authEnabled": AUTH_REQUIRED,
            "auditChainValid": audit_svc.verify_chain().get("valid", False),
            "hitlPolicies": len([p for p in policy_svc.list_policies() if p["rule"].get("action") == "require_approval"]) > 0,
            "governancePolicies": len(governance_svc.list_policies()) >= 4,
            "rbacUsers": len(auth_svc.list_users()) >= 1,
        },
    }


@app.get("/api/state")
def get_state() -> dict[str, Any]:
    operator = safepulse_svc.get_operator()
    return {
        "currentAgent": agents_svc.get_current_agent(),
        "agents": agents_svc.list_agents(),
        "operator": operator,
        "cert": trust_svc.get_certificate(),
        "session": sessions_svc.get_session(),
        "auditLog": sessions_svc.get_audit_log(),
        "rtlTrace": sessions_svc.get_rtl_trace(),
        "toolCalls": aegis_svc.list_tool_calls(),
        "threatEvents": sonar_svc.list_threats(),
        "threatScore": sonar_svc.threat_score(),
        "pipelineLog": pipeline_svc.get_pipeline_log(),
        "auditVerify": audit_svc.verify_chain(),
        "vaultKeys": vault_svc.list_keys(unlocked=False),
        "presets": list(agents_svc.PRESETS.keys()),
        "safepulseEnrolled": bool(operator and operator.get("enrolled")),
        "clearframeRuntime": cf_runtime.CLEARFRAME_AVAILABLE,
        "agentOps": ops_svc.ops_status(),
        "toolCatalog": tools_svc.list_catalog(),
        "toolConnections": tools_svc.list_connections(),
        "governance": governance_svc.get_dashboard(),
        "runtimePolicies": policy_svc.list_policies(),
        "euAiAct": eu_svc.assess_portfolio(),
        "workflows": workflows_svc.list_workflows(),
    }


@app.get("/api/agents")
def list_agents() -> list[dict[str, Any]]:
    return agents_svc.list_agents()


@app.post("/api/agents")
def create_agent(body: AgentIn) -> dict[str, Any]:
    return agents_svc.save_agent(body.model_dump())


@app.post("/api/agents/{agent_id}/select")
def select_agent(agent_id: str) -> dict[str, Any]:
    agent = agents_svc.set_current_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: str) -> dict[str, str]:
    agents_svc.revoke_agent(agent_id)
    governance_svc.collect_evidence()
    return {"status": "revoked"}


@app.post("/api/agents/{agent_id}/suspend")
def suspend_agent(agent_id: str) -> dict[str, Any]:
    agent = agents_svc.suspend_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    governance_svc.collect_evidence()
    return agent


@app.post("/api/agents/{agent_id}/activate")
def activate_agent(agent_id: str) -> dict[str, Any]:
    agent = agents_svc.activate_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@app.get("/api/tools/catalog")
def tool_catalog() -> list[dict[str, Any]]:
    return tools_svc.list_catalog()


@app.get("/api/tools/connections")
def tool_connections() -> list[dict[str, Any]]:
    return tools_svc.list_connections()


@app.post("/api/tools/connections")
def create_connection(body: ConnectionIn) -> dict[str, Any]:
    return tools_svc.create_connection(body.toolId, body.name, body.config)


@app.post("/api/tools/execute")
def execute_tool(body: ToolExecuteIn) -> dict[str, Any]:
    agent = agents_svc.get_current_agent()
    ctx = {"trustScore": agent.get("trustScore", 100) if agent else 100, "agentStatus": agent.get("status", "active") if agent else "active"}
    pol = policy_svc.evaluate(body.tool, body.args, ctx)
    if pol["disposition"] == "deny":
        return {"ok": False, "blocked": True, "policy": pol}
    result = tools_svc.execute_tool(body.tool, **body.args)
    return {"ok": True, "result": result, "policy": pol}


@app.get("/api/policies")
def list_runtime_policies() -> list[dict[str, Any]]:
    return policy_svc.list_policies()


@app.post("/api/policies")
def create_policy(body: PolicyIn, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    if user and not auth_svc.has_permission(user["role"], "*"):
        raise HTTPException(403, "Admin only")
    return policy_svc.create_policy(body.name, body.rule, body.priority)


@app.get("/api/governance/hub")
def governance_hub() -> dict[str, Any]:
    return policy_hub_svc.get_governance_hub()


@app.get("/api/governance/frameworks")
def list_frameworks() -> list[dict[str, Any]]:
    return policy_hub_svc.get_frameworks()


@app.post("/api/governance/frameworks/{framework_id}/attest")
def attest_framework(framework_id: str, body: FrameworkAttestIn) -> dict[str, Any]:
    return policy_hub_svc.attest_framework(framework_id, body.attested, body.notes)


@app.get("/api/governance/documents")
def list_policy_documents(category: str | None = None) -> list[dict[str, Any]]:
    return policy_hub_svc.list_documents(category)


@app.post("/api/governance/documents")
def upload_policy_document(body: PolicyUploadIn) -> dict[str, Any]:
    return policy_hub_svc.upload_document(
        body.title, body.category, body.content, body.fileName, body.version, body.parentDocId, body.hierarchyLevel,
    )


@app.post("/api/governance/cards")
def create_policy_card(body: PolicyCardIn) -> dict[str, Any]:
    return policy_hub_svc.create_card(body.docId, body.title, body.content, body.priority, body.parentCardId, body.hierarchyOrder, body.enforce, body.tags)


@app.patch("/api/governance/cards/{card_id}/hierarchy")
def update_card_hierarchy(card_id: str, parentCardId: str | None = None, hierarchyOrder: int = 0, enforce: bool | None = None) -> dict[str, Any]:
    return policy_hub_svc.update_card_hierarchy(card_id, parentCardId, hierarchyOrder, enforce)


@app.get("/api/governance/actions")
def list_agent_actions(sessionId: str | None = None) -> list[dict[str, Any]]:
    return action_audit_svc.list_actions(sessionId)


@app.get("/api/governance/reasoning")
def reasoning_chain(sessionId: str | None = None) -> list[dict[str, Any]]:
    return action_audit_svc.get_reasoning_chain(sessionId)


@app.get("/api/governance/dashboard")
def governance_dashboard() -> dict[str, Any]:
    return governance_svc.get_dashboard()


@app.post("/api/governance/evidence")
def collect_evidence() -> dict[str, Any]:
    evidence = governance_svc.collect_evidence()
    return {"collected": len(evidence), "evidence": evidence}


@app.get("/api/governance/export")
def export_evidence() -> dict[str, Any]:
    return export_svc.build_evidence_pack()


@app.get("/api/governance/policies")
def governance_policies() -> list[dict[str, Any]]:
    return governance_svc.list_policies()


@app.post("/api/governance/risks")
def create_risk(body: RiskIn) -> dict[str, Any]:
    return governance_svc.create_risk(body.agentId, body.title, body.description, body.likelihood, body.impact)


@app.get("/api/eu-ai-act")
def eu_ai_act() -> dict[str, Any]:
    return eu_svc.assess_portfolio()


@app.get("/api/workflows")
def list_workflows() -> list[dict[str, Any]]:
    return workflows_svc.list_workflows()


@app.post("/api/workflows")
def create_workflow(body: WorkflowIn) -> dict[str, Any]:
    return workflows_svc.create_workflow(body.name, body.description, body.steps)


@app.post("/api/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str) -> dict[str, Any]:
    return await workflows_svc.run_workflow(workflow_id)


@app.get("/api/presets")
def presets() -> dict[str, Any]:
    return agents_svc.PRESETS


@app.post("/api/safepulse/enroll")
def enroll(body: ProfileIn) -> dict[str, Any]:
    return safepulse_svc.enroll(body.profile)


@app.post("/api/safepulse/verify")
def verify(body: ProfileIn) -> dict[str, Any]:
    return safepulse_svc.verify(body.profile)


@app.delete("/api/safepulse")
def reset_safepulse() -> dict[str, str]:
    safepulse_svc.reset()
    return {"status": "reset"}


@app.post("/api/trust/issue")
def issue_cert(body: CertIn) -> dict[str, Any]:
    return trust_svc.issue_certificate(body.trustLevel, body.ttlHours)


@app.get("/api/trust/verify")
def verify_cert() -> dict[str, Any]:
    return trust_svc.verify_certificate()


@app.post("/api/trust/revoke")
def revoke_cert() -> dict[str, Any]:
    return trust_svc.revoke_certificate()


@app.post("/api/sessions/start")
async def start_session() -> dict[str, Any]:
    return await sessions_svc.start_session()


@app.get("/api/sessions/audit")
def audit_log() -> list[dict[str, Any]]:
    return sessions_svc.get_audit_log()


@app.get("/api/sessions/rtl")
def rtl_trace() -> list[dict[str, Any]]:
    return sessions_svc.get_rtl_trace()


@app.get("/api/aegis/calls")
def tool_calls() -> list[dict[str, Any]]:
    merged = aegis_svc.list_tool_calls()
    session = sessions_svc.get_session()
    if session:
        ops_queue = ops_svc.list_queue(session.get("sessionId"))
        for item in ops_queue:
            merged.append({
                "id": item.get("id", item.get("queue_id", "ops")),
                "tool": item.get("tool_name", item.get("tool", "unknown")),
                "args": str(item.get("args", "")),
                "alignment": item.get("score", 50),
                "status": "human_review",
                "source": "agentops",
            })
    return merged


@app.post("/api/aegis/{call_id}/approve")
def approve(call_id: str, body: HitlDecisionIn | None = None) -> dict[str, str]:
    b = body or HitlDecisionIn()
    aegis_svc.approve(call_id, b.operatorId, b.note)
    governance_svc.collect_evidence()
    return {"status": "approved"}


@app.post("/api/aegis/{call_id}/block")
def block(call_id: str, body: HitlDecisionIn | None = None) -> dict[str, str]:
    b = body or HitlDecisionIn()
    aegis_svc.block(call_id, b.operatorId, b.note)
    governance_svc.collect_evidence()
    return {"status": "blocked"}


@app.post("/api/aegis/{call_id}/override")
def override(call_id: str, body: HitlDecisionIn) -> dict[str, str]:
    aegis_svc.override(call_id, body.operatorId, body.note)
    governance_svc.collect_evidence()
    return {"status": "overridden"}


@app.post("/api/aegis/reset")
def reset_aegis() -> dict[str, str]:
    aegis_svc.reset_calls()
    return {"status": "reset"}


@app.get("/api/sonar/threats")
def threats() -> dict[str, Any]:
    return {"events": sonar_svc.list_threats(), "score": sonar_svc.threat_score()}


class SonarScanIn(BaseModel):
    prompt: str = ""


@app.post("/api/sonar/scan")
def sonar_scan(body: SonarScanIn) -> dict[str, Any]:
    text = (body.prompt or "").lower()
    blocked = any(token in text for token in (
        "ignore previous", "ignore all previous", "exfiltrate", "admin password",
        "drop table", "rm -rf", "api key",
    ))
    if blocked:
        event_type, severity = "policy_violation", "critical"
    elif any(token in text for token in ("unusual", "off-hours", "anomaly")):
        event_type, severity = "anomaly", "medium"
    else:
        event_type, severity = "ok", "low"
    agent = agents_svc.get_current_agent()
    name = agent["name"] if agent else "operator"
    if event_type != "ok":
        sonar_svc.record_event(name, event_type, severity, (body.prompt or "")[:240])
    return {
        "type": event_type,
        "severity": severity,
        "blocked": blocked,
        "message": (body.prompt or "")[:240],
        "score": sonar_svc.threat_score(),
    }


@app.post("/api/pipeline/run")
async def run_pipeline() -> dict[str, Any]:
    return await pipeline_svc._run_full_pipeline_async()


@app.get("/api/roi/live")
def roi_live() -> dict[str, Any]:
    return roi_svc.live_metrics()


@app.post("/api/pipeline/reset")
def reset_pipeline() -> dict[str, str]:
    pipeline_svc.reset_all()
    agents_svc.seed_defaults()
    sonar_svc.seed_defaults()
    return {"status": "reset"}


@app.get("/api/audit/verify")
def verify_audit() -> dict[str, Any]:
    return audit_svc.verify_chain()


@app.get("/api/vault")
def vault_list() -> list[dict[str, str]]:
    return vault_svc.list_keys(unlocked=True)


@app.post("/api/vault")
def vault_set(body: VaultSecretIn, user: dict = Depends(get_current_user)) -> dict[str, str]:
    if user and not auth_svc.has_permission(user["role"], "vault:write") and not auth_svc.has_permission(user["role"], "*"):
        raise HTTPException(403, "Permission denied")
    vault_svc.set_secret(body.key, body.value)
    return {"status": "stored", "key": body.key}


@app.post("/api/roi/calculate")
def calculate_roi(body: RoiIn) -> dict[str, Any]:
    return roi_svc.calculate(body.agents, body.operators, body.reductionPct)


from pathlib import Path
from fastapi.staticfiles import StaticFiles

_static = Path(__file__).resolve().parent.parent / "static"
if _static.exists():
    app.mount("/", StaticFiles(directory=_static, html=True), name="frontend")

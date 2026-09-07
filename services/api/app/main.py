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
from app.services import soc_bus as soc_bus_svc
from app.services import integrations as integrations_svc
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
from app.services import backup as backup_svc
from app.services import federation as federation_svc
from app.services import history as history_svc
from app.services import idempotency as idem_svc
from app.services import lineage as lineage_svc
from app.services import migrations as migrations_svc
from app.services import tenancy as tenancy_svc
from app.services import data_access as data_access_svc
from app.services import memory as memory_svc
from app.services import otel as otel_svc
from app.services import mandate as mandate_svc
from app.services import ranger as ranger_svc
from app.services import providers as providers_svc
from app.services import lattice as lattice_svc
from app.production import enforce_or_exit, production_status


def require_permission(user: dict | None, permission: str) -> None:
    if user and not auth_svc.has_permission(user["role"], permission):
        raise HTTPException(403, f"Requires {permission} permission")


def tenant_from_request(request: Request) -> str:
    return request.headers.get("X-Tenant-Id", tenancy_svc.DEFAULT_TENANT)


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


class AgentUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    capabilities: list[str] | None = None
    provider: str | None = None
    model: str | None = None
    maxSteps: int | None = None
    allowWeb: bool | None = None
    allowFs: bool | None = None
    allowExec: bool | None = None
    owner: str | None = None


class BackupRestoreIn(BaseModel):
    formatVersion: int
    exportedAt: float | None = None
    tables: dict[str, list[dict[str, Any]]]


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
        "version": "2.1.0-enterprise",
        "clearframeRuntime": cf_runtime.CLEARFRAME_AVAILABLE,
        "agentOps": ops_svc.ops_status(),
        "toolCount": len(tools_svc.list_catalog()),
        "ollama": {"enabled": USE_OLLAMA, "host": OLLAMA_HOST, "available": ollama_ok, "models": llm_svc.list_models() if ollama_ok else []},
        "authRequired": AUTH_REQUIRED,
        "database": backend_label(),
        "ssoEnabled": oidc_svc.sso_enabled(),
        "production": production_status(),
        "migrations": migrations_svc.applied(),
        "features": {
            "federationEngine": True,
            "agentDataAccess": True,
            "continuumMemory": True,
            "latticeScale": True,
            "mandateStudio": True,
            "otelExport": True,
            "rangerVerify": True,
            "sonarAiSoc": True,
            "multiProviderLlm": True,
            "tenancy": True,
            "lineage": True,
            "idempotency": True,
            "backup": True,
            "history": True,
        },
        "providers": providers_svc.list_providers(),
        "product": {
            "openSource": "ClearFrame",
            "openSourceLicense": "Apache-2.0",
            "closedSource": "Nexus Protocol",
            "vendor": "Erasys",
            "nexusIncludes": ["SafePulse", "commercial support", "enterprise extensions"],
        },
    }


@app.get("/api/live")
def liveness() -> dict[str, str]:
    """Kubernetes liveness probe — process is up."""
    return {"status": "alive"}


@app.get("/api/ready")
def readiness() -> dict[str, Any]:
    """Kubernetes readiness probe — database accepts connections."""
    try:
        from app.database import get_conn
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return {"status": "ready", "database": backend_label()}
    except Exception as exc:
        raise HTTPException(503, f"not ready: {exc}")


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


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: str) -> dict[str, Any]:
    agent = agents_svc.get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@app.put("/api/agents/{agent_id}")
def update_agent(agent_id: str, body: AgentUpdateIn, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "agents:write")
    patch = body.model_dump(exclude_none=True)
    agent = agents_svc.update_agent(agent_id, patch, actor=(user or {}).get("email", "system"))
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@app.get("/api/agents/{agent_id}/history")
def agent_history(agent_id: str, user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    require_permission(user, "agents:read")
    if not agents_svc.get_agent(agent_id):
        raise HTTPException(404, "Agent not found")
    return history_svc.list_history("agent", agent_id)


@app.post("/api/agents/{agent_id}/rollback/{version}")
def rollback_agent(agent_id: str, version: int, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "agents:write")
    agent = agents_svc.rollback_agent(agent_id, version, actor=(user or {}).get("email", "system"))
    if not agent:
        raise HTTPException(404, "Agent or version not found")
    return agent


@app.post("/api/agents/{agent_id}/restore")
def restore_agent(agent_id: str, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "agents:write")
    agent = agents_svc.restore_agent(agent_id, actor=(user or {}).get("email", "system"))
    if not agent:
        raise HTTPException(404, "Agent is not revoked or has no restorable history")
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
    require_permission(user, "*")
    return policy_svc.create_policy(
        body.name, body.rule, body.priority, actor=(user or {}).get("email", "system")
    )


@app.put("/api/policies/{policy_id}")
def update_policy(policy_id: str, body: PolicyIn, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "*")
    policy = policy_svc.update_policy(
        policy_id,
        {"name": body.name, "rule": body.rule, "priority": body.priority},
        actor=(user or {}).get("email", "system"),
    )
    if not policy:
        raise HTTPException(404, "Policy not found")
    return policy


@app.delete("/api/policies/{policy_id}")
def delete_policy(policy_id: str, user: dict = Depends(get_current_user)) -> dict[str, str]:
    require_permission(user, "*")
    if not policy_svc.delete_policy(policy_id, actor=(user or {}).get("email", "system")):
        raise HTTPException(404, "Policy not found")
    return {"status": "disabled"}


@app.get("/api/policies/{policy_id}/history")
def policy_history(policy_id: str, user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    require_permission(user, "governance:read")
    if not policy_svc.get_policy(policy_id):
        raise HTTPException(404, "Policy not found")
    return history_svc.list_history("policy", policy_id)


@app.post("/api/policies/{policy_id}/rollback/{version}")
def rollback_policy(policy_id: str, version: int, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "*")
    policy = policy_svc.rollback_policy(policy_id, version, actor=(user or {}).get("email", "system"))
    if not policy:
        raise HTTPException(404, "Policy or version not found")
    return policy


@app.get("/api/admin/backup")
def export_backup(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "*")
    return backup_svc.export_all(actor=(user or {}).get("email", "system"))


@app.post("/api/admin/restore")
def restore_backup(body: BackupRestoreIn, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "*")
    try:
        return backup_svc.restore_all(body.model_dump(), actor=(user or {}).get("email", "system"))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


class TenantIn(BaseModel):
    name: str
    quotas: dict[str, Any] = Field(default_factory=lambda: {"maxAgents": 50, "maxQueriesPerHour": 500})


class CatalogIn(BaseModel):
    name: str
    kind: str = "virtual"
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    maskColumns: list[str] = Field(default_factory=list)


class FederatedQueryIn(BaseModel):
    sql: str
    agentId: str = ""


@app.get("/api/tenants")
def list_tenants(user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    require_permission(user, "governance:read")
    return tenancy_svc.list_tenants()


@app.post("/api/tenants")
def create_tenant(body: TenantIn, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "*")
    return tenancy_svc.create_tenant(body.name, body.quotas)


@app.get("/api/federation/catalogs")
def fed_catalogs(request: Request, user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    require_permission(user, "agents:read")
    return federation_svc.list_catalogs(tenant_from_request(request))


@app.post("/api/federation/catalogs")
def fed_register_catalog(body: CatalogIn, request: Request, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "*")
    try:
        return federation_svc.register_catalog(
            body.name, body.kind, body.config, body.description, body.maskColumns,
            tenant_id=tenant_from_request(request), actor=(user or {}).get("email", "system"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/federation/query")
def fed_query(body: FederatedQueryIn, request: Request, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "agents:write")
    idem = request.headers.get("Idempotency-Key", "").strip()
    path = "/api/federation/query"
    if idem:
        cached = idem_svc.lookup(idem, "POST", path)
        if cached:
            return cached["body"]
    try:
        result = federation_svc.execute_query(
            body.sql,
            tenant_id=tenant_from_request(request),
            actor=(user or {}).get("email", "system"),
            agent_id=body.agentId,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if idem:
        idem_svc.store(idem, "POST", path, 200, result)
    return result


@app.get("/api/federation/queries")
def fed_query_history(request: Request, user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    require_permission(user, "audit:read")
    return federation_svc.list_queries(tenant_from_request(request))


@app.get("/api/lineage")
def lineage_recent(user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    require_permission(user, "audit:read")
    return lineage_svc.recent()


@app.get("/api/lineage/{lineage_id}")
def lineage_get(lineage_id: str, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "audit:read")
    item = lineage_svc.get(lineage_id)
    if not item:
        raise HTTPException(404, "Lineage event not found")
    return item


@app.get("/api/admin/migrations")
def list_migrations(user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    require_permission(user, "*")
    return migrations_svc.applied()


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
    agent = agents_svc.get_current_agent()
    name = agent["name"] if agent else "operator"
    return sonar_svc.scan_prompt(body.prompt or "", agent_name=name)


@app.get("/api/sonar/soc")
def sonar_soc() -> dict[str, Any]:
    return sonar_svc.soc_dashboard()


@app.get("/api/sonar/playbooks")
def sonar_playbooks() -> list[dict[str, Any]]:
    return sonar_svc.list_playbooks()


@app.get("/api/sonar/catalog")
def sonar_catalog() -> list[dict[str, Any]]:
    return sonar_svc.threat_catalog()


class SonarLiveScanIn(BaseModel):
    threatId: str
    agentName: str = ""


@app.post("/api/sonar/live-scan")
def sonar_live_scan(body: SonarLiveScanIn) -> dict[str, Any]:
    agent = agents_svc.get_current_agent()
    name = body.agentName or (agent["name"] if agent else "operator")
    return sonar_svc.live_scan_threat(body.threatId, agent_name=name)


@app.post("/api/sonar/scan-session")
def sonar_scan_session() -> dict[str, Any]:
    agent = agents_svc.get_current_agent()
    name = agent["name"] if agent else "operator"
    return sonar_svc.scan_active_session(agent_name=name)


class SonarInjectIn(BaseModel):
    type: str | None = None
    severity: str | None = None
    description: str | None = None
    agentName: str = ""


@app.post("/api/sonar/inject")
def sonar_inject(body: SonarInjectIn) -> dict[str, Any]:
    return sonar_svc.inject_test_alert(body.type, body.severity, body.description, body.agentName)


class SonarContainIn(BaseModel):
    agentId: str | None = None
    action: str = "suspend"
    reason: str = "Sonar AI SOC containment"


@app.post("/api/sonar/contain")
def sonar_contain(body: SonarContainIn, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "agents:write")
    return sonar_svc.contain(body.agentId, body.action, body.reason)


class SocIngestIn(BaseModel):
    eventId: str | None = None
    source: str = "webhook"
    severity: str = "medium"
    actor: dict[str, Any] = {}
    asset: dict[str, Any] = {}
    action: str = "unknown"
    evidence: dict[str, Any] = {}
    ts: Any = None


@app.get("/api/soc/dashboard")
def soc_dashboard() -> dict[str, Any]:
    return soc_bus_svc.dashboard()


@app.get("/api/soc/events")
def soc_events(limit: int = 50) -> dict[str, Any]:
    return {"events": soc_bus_svc.list_events(limit)}


@app.get("/api/soc/cases")
def soc_cases(limit: int = 30) -> dict[str, Any]:
    return {"cases": soc_bus_svc.list_cases(limit)}


@app.get("/api/soc/cases/{case_id}")
def soc_case(case_id: str) -> dict[str, Any]:
    case = soc_bus_svc.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@app.post("/api/soc/ingest")
def soc_ingest(body: SocIngestIn) -> dict[str, Any]:
    return soc_bus_svc.ingest_event(body.model_dump(exclude_none=True))


@app.post("/api/soc/webhooks/{source}")
async def soc_webhook(source: str, request: Request) -> dict[str, Any]:
    """Generic webhook ingest — body is normalized into a SocEvent."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {"raw": payload}
    payload.setdefault("source", source)
    # Okta-ish convenience mapping
    if source.lower() == "okta" and "action" not in payload:
        event_type = (payload.get("eventType") or payload.get("type") or "").lower()
        if "impossible" in event_type or payload.get("impossibleTravel"):
            payload["action"] = "login.impossible_travel"
        elif "login" in event_type:
            payload["action"] = "login.success"
        actor = payload.get("actor") or {}
        if not actor and payload.get("user"):
            payload["actor"] = {"user": payload["user"], "ip": payload.get("ip")}
    return soc_bus_svc.ingest_event(payload)


@app.post("/api/soc/cases/{case_id}/run")
def soc_run_case(case_id: str, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "agents:write")
    result = soc_bus_svc.run_case_playbook(case_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "Case not found")
    return result


@app.post("/api/soc/demo/correlate")
def soc_demo_correlate() -> dict[str, Any]:
    """Tabletop: Okta impossible travel + Sonar exfil → correlated case."""
    return soc_bus_svc.demo_impossible_travel_and_exfil()


@app.post("/api/soc/tabletop/{story}")
def soc_tabletop(story: str) -> dict[str, Any]:
    """Proof stories: jailbreak_autocontain | impossible_travel_exfil | policy_hard_block."""
    result = soc_bus_svc.tabletop(story)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Unknown story")
    return result


@app.post("/api/soc/cases/{case_id}/triage")
def soc_triage(case_id: str) -> dict[str, Any]:
    result = soc_bus_svc.triage_case(case_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "Case not found")
    return result


@app.get("/api/integrations/status")
def integrations_status() -> dict[str, Any]:
    return integrations_svc.status()


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


# ── Agent-native data access (no operator SQL) ──────────────────────────────

class DataAskIn(BaseModel):
    question: str
    visualize: bool = False
    agentId: str = ""


@app.post("/api/data/ask")
def data_ask(body: DataAskIn, request: Request, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    actor = (user or {}).get("email", "operator")
    return data_access_svc.ask(
        body.question,
        tenant_id=tenant_from_request(request),
        actor=actor,
        agent_id=body.agentId,
        visualize=body.visualize,
    )


@app.get("/api/data/catalogs")
def data_catalogs(request: Request) -> list[dict[str, Any]]:
    """Catalog metadata for agents / console — not a SQL surface."""
    return federation_svc.list_catalogs(tenant_from_request(request))


# ── Continuum (managed memory) ──────────────────────────────────────────────

class MemoryLongIn(BaseModel):
    agentId: str
    key: str
    value: Any
    importance: float = 0.5


class ContinuumPutIn(BaseModel):
    agentId: str
    content: str
    strategy: str = "episodic"
    namespace: str = "default"
    key: str | None = None
    sessionId: str = ""
    importance: float = 0.5
    tags: list[str] = Field(default_factory=list)
    ttlSec: int | None = None


@app.get("/api/memory/{session_id}")
def memory_get(session_id: str, request: Request, agentId: str = "") -> dict[str, Any]:
    return memory_svc.context_bundle(session_id, tenant_from_request(request), agentId)


@app.post("/api/memory/long")
def memory_long_write(body: MemoryLongIn, request: Request) -> dict[str, Any]:
    mid = memory_svc.remember_long(
        tenant_from_request(request), body.agentId, body.key, body.value, body.importance
    )
    return {"ok": True, "memoryId": mid}


@app.get("/api/continuum")
def continuum_dash(request: Request) -> dict[str, Any]:
    return memory_svc.dashboard(tenant_from_request(request))


@app.get("/api/continuum/browse")
def continuum_browse(
    request: Request,
    agentId: str = "",
    namespace: str | None = None,
    strategy: str | None = None,
) -> list[dict[str, Any]]:
    return memory_svc.browse(tenant_from_request(request), agentId, namespace, strategy)


@app.get("/api/continuum/search")
def continuum_search(request: Request, q: str, agentId: str = "") -> list[dict[str, Any]]:
    return memory_svc.search(tenant_from_request(request), q, agentId)


@app.post("/api/continuum")
def continuum_put(body: ContinuumPutIn, request: Request) -> dict[str, Any]:
    try:
        return memory_svc.put(
            tenant_from_request(request),
            body.agentId,
            body.content,
            strategy=body.strategy,
            namespace=body.namespace,
            key=body.key,
            session_id=body.sessionId,
            importance=body.importance,
            tags=body.tags,
            ttl_sec=body.ttlSec,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ── Mandate Studio ──────────────────────────────────────────────────────────

class PolicyImportIn(BaseModel):
    text: str
    format: str = "auto"


class MandateAuthorIn(BaseModel):
    effect: str
    tool: str
    whenMinTrust: float | None = None
    requireApproval: bool = False
    name: str | None = None
    priority: int | None = None


@app.post("/api/policies/import")
def policy_import(body: PolicyImportIn, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    actor = (user or {}).get("email", "operator")
    try:
        return mandate_svc.import_policy(body.text, body.format, actor=actor)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/mandate/author")
def mandate_author(body: MandateAuthorIn, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    actor = (user or {}).get("email", "operator")
    try:
        return mandate_svc.author(
            body.effect,
            body.tool,
            when_min_trust=body.whenMinTrust,
            require_approval=body.requireApproval,
            name=body.name,
            priority=body.priority,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/mandate/preview")
def mandate_preview(body: MandateAuthorIn) -> dict[str, Any]:
    return mandate_svc.preview(body.effect, body.tool, body.whenMinTrust)


# ── Lattice (elastic scale-out) ─────────────────────────────────────────────

class LatticeScaleIn(BaseModel):
    workers: int = 4


class LatticeJobIn(BaseModel):
    agentId: str
    goal: str


@app.get("/api/lattice")
def lattice_status() -> dict[str, Any]:
    return lattice_svc.status()


@app.post("/api/lattice/scale")
def lattice_scale(body: LatticeScaleIn, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_permission(user, "agents:write")
    return lattice_svc.scale(body.workers)


@app.post("/api/lattice/jobs")
def lattice_enqueue(body: LatticeJobIn, request: Request) -> dict[str, Any]:
    return lattice_svc.enqueue(body.agentId, body.goal, tenant_from_request(request))


@app.get("/api/lattice/jobs")
def lattice_jobs() -> list[dict[str, Any]]:
    return lattice_svc.list_jobs()


@app.get("/api/lattice/jobs/{job_id}")
def lattice_job(job_id: str) -> dict[str, Any]:
    job = lattice_svc.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


# ── Access verification ─────────────────────────────────────────────────────

class RangerVerifyIn(BaseModel):
    principal: str
    resource: str
    action: str
    trustScore: float = 100
    agentStatus: str = "active"


@app.post("/api/verify/ranger")
def ranger_verify(body: RangerVerifyIn) -> dict[str, Any]:
    return ranger_svc.verify_access(
        body.principal,
        body.resource,
        body.action,
        {"trustScore": body.trustScore, "agentStatus": body.agentStatus},
    )


@app.get("/api/verify/ranger/portfolio")
def ranger_portfolio() -> dict[str, Any]:
    return ranger_svc.verify_agent_portfolio()


@app.get("/api/verify/audit-chain")
def verify_audit_chain() -> dict[str, Any]:
    return audit_svc.verify_chain()


# ── Providers + OTEL ────────────────────────────────────────────────────────

@app.get("/api/providers")
def list_llm_providers() -> list[dict[str, Any]]:
    return providers_svc.list_providers()


@app.get("/api/providers/{provider}/validate")
def validate_llm_provider(provider: str) -> dict[str, Any]:
    return providers_svc.validate_provider_config(provider)


@app.get("/api/otel/status")
def otel_status() -> dict[str, Any]:
    return {"enabled": otel_svc.OTEL_ENABLED, "path": otel_svc.OTEL_PATH}


# ── Policy hub hierarchy + upload ───────────────────────────────────────────

@app.get("/api/governance/hierarchy")
def policy_hierarchy() -> list[dict[str, Any]]:
    return policy_hub_svc.hierarchy_tree()


class PolicyUploadIn(BaseModel):
    title: str
    category: str = "internal"
    content: str
    fileName: str = ""
    version: str = "1.0"
    parentDocId: str | None = None


@app.post("/api/governance/documents/upload")
def upload_policy_doc(body: PolicyUploadIn) -> dict[str, Any]:
    try:
        return policy_hub_svc.upload_document(
            body.title, body.category, body.content,
            file_name=body.fileName, version=body.version, parent_doc_id=body.parentDocId,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


from pathlib import Path
from fastapi.staticfiles import StaticFiles

_static = Path(__file__).resolve().parent.parent / "static"
if _static.exists():
    app.mount("/", StaticFiles(directory=_static, html=True), name="frontend")

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from trust_registry.models import AgentIdentity, CapabilityScope, IssuanceRequest, TrustLevel
from trust_registry.registry import TrustRegistry


class IssueBody(BaseModel):
    name: str
    version: str = "1.0.0"
    owner: str = "Nexus Operator"
    trust_level: TrustLevel = TrustLevel.STANDARD
    validity_days: int = 30
    capabilities: CapabilityScope = CapabilityScope(can_make_http_requests=True)


def create_app(state_path: Path) -> FastAPI:
    registry = TrustRegistry(state_path)
    app = FastAPI(title="Nexus TrustRegistry", version="0.1.0")
    app.state.registry = registry

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "trust-registry"}

    @app.get("/certificates")
    def list_certs() -> list[dict]:
        return [c.to_public_dict() for c in registry.list_certificates()]

    @app.post("/certificates/issue")
    def issue(body: IssueBody) -> dict:
        cert = registry.issue_certificate(IssuanceRequest(
            agent=AgentIdentity(name=body.name, version=body.version, owner=body.owner),
            requested_trust_level=body.trust_level,
            capability_scope=body.capabilities,
            validity_days=body.validity_days,
        ))
        return cert.to_public_dict()

    @app.get("/certificates/{cert_id}/verify")
    def verify(cert_id: str) -> dict:
        try:
            cert = registry.verify(cert_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"valid": True, **cert.to_public_dict()}

    @app.post("/certificates/{cert_id}/revoke")
    def revoke(cert_id: str) -> dict[str, str]:
        try:
            registry.revoke(cert_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "revoked", "certificate_id": cert_id}

    return app

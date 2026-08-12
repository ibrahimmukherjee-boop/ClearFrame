"""FastAPI auth dependencies."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from app.config import AUTH_REQUIRED
from app.services import auth as auth_svc

ROLE_PERMISSIONS_MAP: dict[str, str] = {
    "GET:/api/agents": "agents:read",
    "POST:/api/agents": "agents:write",
    "POST:/api/sessions/start": "sessions:write",
    "POST:/api/pipeline/run": "pipeline:run",
    "POST:/api/aegis": "aegis:approve",
    "GET:/api/governance": "governance:read",
    "GET:/api/audit": "audit:read",
    "POST:/api/tools/execute": "tools:execute",
    "POST:/api/trust/issue": "trust:issue",
    "POST:/api/vault": "vault:write",
    "GET:/api/vault": "vault:read",
}


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("access_token")


def get_current_user(request: Request) -> dict[str, Any] | None:
    if not AUTH_REQUIRED:
        return {"userId": "system", "email": "system@local", "role": "admin", "name": "System"}
    if request.url.path in auth_svc.PUBLIC_PATHS:
        return None
    token = _extract_token(request)
    if not token:
        raise HTTPException(401, "Authentication required")
    payload = auth_svc.decode_token(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    user = auth_svc.get_user(payload["sub"])
    if not user:
        raise HTTPException(401, "User not found")
    return {"userId": user["user_id"], "email": user["email"], "role": user["role"], "name": user["name"]}


def require_permission(permission: str):
    def checker(request: Request) -> dict[str, Any]:
        user = get_current_user(request)
        if user is None:
            return {}
        if not auth_svc.has_permission(user["role"], permission):
            raise HTTPException(403, f"Permission denied: {permission}")
        return user
    return checker

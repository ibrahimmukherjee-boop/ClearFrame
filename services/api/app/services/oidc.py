"""OpenID Connect (SSO) authentication."""
from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import JWT_EXPIRY_HOURS
from app.database import get_conn
from app.services.auth import create_token, _hash_password

OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "").rstrip("/")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
OIDC_REDIRECT_URI = os.environ.get("OIDC_REDIRECT_URI", "")
OIDC_SCOPES = os.environ.get("OIDC_SCOPES", "openid profile email")
OIDC_ROLE_CLAIM = os.environ.get("OIDC_ROLE_CLAIM", "groups")
OIDC_ADMIN_GROUP = os.environ.get("OIDC_ADMIN_GROUP", "clearframe-admins")
OIDC_OPERATOR_GROUP = os.environ.get("OIDC_OPERATOR_GROUP", "clearframe-operators")

_pending_states: dict[str, float] = {}


def sso_enabled() -> bool:
    return bool(OIDC_ISSUER and OIDC_CLIENT_ID and OIDC_REDIRECT_URI)


def _discovery() -> dict[str, Any]:
    url = f"{OIDC_ISSUER}/.well-known/openid-configuration"
    r = httpx.get(url, timeout=10.0)
    r.raise_for_status()
    return r.json()


def login_url() -> dict[str, str]:
    if not sso_enabled():
        raise RuntimeError("SSO not configured")
    meta = _discovery()
    state = secrets.token_urlsafe(24)
    _pending_states[state] = time.time() + 600
    params = {
        "client_id": OIDC_CLIENT_ID,
        "response_type": "code",
        "scope": OIDC_SCOPES,
        "redirect_uri": OIDC_REDIRECT_URI,
        "state": state,
    }
    return {"url": f"{meta['authorization_endpoint']}?{urlencode(params)}", "state": state}


def _map_role(claims: dict[str, Any]) -> str:
    groups = claims.get(OIDC_ROLE_CLAIM) or claims.get("roles") or []
    if isinstance(groups, str):
        groups = [groups]
    if OIDC_ADMIN_GROUP in groups:
        return "admin"
    if OIDC_OPERATOR_GROUP in groups:
        return "operator"
    return "auditor"


def _provision_user(email: str, name: str, role: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            conn.execute("UPDATE users SET name = ?, role = ? WHERE email = ?", (name, role, email))
            return dict(row)
        user_id = f"usr-{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO users (user_id, email, password_hash, name, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, email, _hash_password(secrets.token_hex(32)), name, role, time.time()),
        )
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row)


def handle_callback(code: str, state: str) -> dict[str, Any] | None:
    if not sso_enabled():
        return None
    expires = _pending_states.pop(state, 0)
    if expires < time.time():
        return None
    meta = _discovery()
    token_resp = httpx.post(
        meta["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": OIDC_REDIRECT_URI,
            "client_id": OIDC_CLIENT_ID,
            "client_secret": OIDC_CLIENT_SECRET,
        },
        timeout=10.0,
    )
    token_resp.raise_for_status()
    tokens = token_resp.json()
    userinfo: dict[str, Any] = {}
    if tokens.get("id_token"):
        # decode payload without verification for claims (token came from IdP directly)
        try:
            payload = tokens["id_token"].split(".")[1]
            pad = "=" * (-len(payload) % 4)
            userinfo = json.loads(__import__("base64").urlsafe_b64decode(payload + pad))
        except Exception:
            pass
    if not userinfo.get("email") and meta.get("userinfo_endpoint"):
        ui = httpx.get(
            meta["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            timeout=10.0,
        )
        ui.raise_for_status()
        userinfo = ui.json()
    email = userinfo.get("email") or userinfo.get("preferred_username")
    if not email:
        return None
    name = userinfo.get("name") or email.split("@")[0]
    role = _map_role(userinfo)
    user = _provision_user(email, name, role)
    access = create_token(user["user_id"], user["email"], role)
    refresh_id = f"rt-{uuid.uuid4().hex}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO refresh_tokens (token_id, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (refresh_id, user["user_id"], time.time() + 7 * 86400, time.time()),
        )
    return {
        "accessToken": access,
        "refreshToken": refresh_id,
        "user": {"userId": user["user_id"], "email": email, "name": name, "role": role},
    }

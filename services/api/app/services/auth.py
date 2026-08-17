"""Enterprise JWT authentication and RBAC."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from app.config import JWT_EXPIRY_HOURS, JWT_SECRET
from app.database import get_conn, row_to_dict
from app.production import is_production

ROLES = ("admin", "operator", "auditor")
PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "operator": {
        "agents:read", "agents:write", "sessions:write", "pipeline:run",
        "aegis:approve", "tools:execute", "trust:issue", "safepulse:write",
        "vault:read",
    },
    "auditor": {
        "agents:read", "governance:read", "audit:read", "sonar:read",
        "sessions:read", "aegis:read", "trust:read", "vault:read",
    },
}

PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/oidc/login",
    "/api/auth/oidc/callback",
}


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or uuid.uuid4().hex[:16]
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000)
    return f"{salt}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(_hash_password(password, salt), stored)


def _b64url(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    import base64
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_token(user_id: str, email: str, role: str) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": int(time.time()) + JWT_EXPIRY_HOURS * 3600,
        "iat": int(time.time()),
    }).encode())
    sig = hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        header, payload, sig = token.split(".", 2)
        expected = _b64url(hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


def has_permission(role: str, permission: str) -> bool:
    perms = PERMISSIONS.get(role, set())
    return "*" in perms or permission in perms


def init_auth_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at REAL,
                created_at REAL
            );
            """
        )
        count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if not count:
            if is_production():
                admin_pw = __import__("os").environ.get("CLEARFRAME_ADMIN_PASSWORD")
                if not admin_pw:
                    raise RuntimeError("CLEARFRAME_ADMIN_PASSWORD required in production (no default users)")
                op_pw = __import__("os").environ.get("CLEARFRAME_OPERATOR_PASSWORD", admin_pw)
                aud_pw = __import__("os").environ.get("CLEARFRAME_AUDITOR_PASSWORD", admin_pw)
                defaults = [
                    ("usr-admin", "admin@erasys.local", "System Administrator", "admin", admin_pw),
                    ("usr-operator", "operator@erasys.local", "Pipeline Operator", "operator", op_pw),
                    ("usr-auditor", "auditor@erasys.local", "Compliance Auditor", "auditor", aud_pw),
                ]
            else:
                defaults = [
                    ("usr-admin", "admin@erasys.local", "System Administrator", "admin", "admin"),
                    ("usr-operator", "operator@erasys.local", "Pipeline Operator", "operator", "operator"),
                    ("usr-auditor", "auditor@erasys.local", "Compliance Auditor", "auditor", "auditor"),
                ]
            for uid, email, name, role, password in defaults:
                conn.execute(
                    "INSERT INTO users (user_id, email, password_hash, name, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (uid, email, _hash_password(password), name, role, time.time()),
                )
    _ensure_team_users()


def _ensure_team_users() -> None:
    """Ensure operator and auditor exist (needed for ISO 7.1 even after initial seed)."""
    import os
    admin_pw = os.environ.get("CLEARFRAME_ADMIN_PASSWORD", "")
    extras = [
        ("usr-operator", "operator@erasys.local", "Pipeline Operator", "operator", os.environ.get("CLEARFRAME_OPERATOR_PASSWORD", admin_pw)),
        ("usr-auditor", "auditor@erasys.local", "Compliance Auditor", "auditor", os.environ.get("CLEARFRAME_AUDITOR_PASSWORD", admin_pw)),
    ]
    with get_conn() as conn:
        for uid, email, name, role, password in extras:
            if not password:
                continue
            exists = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO users (user_id, email, password_hash, name, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (uid, email, _hash_password(password), name, role, time.time()),
                )


def login(email: str, password: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ? AND active = 1", (email,)).fetchone()
    if not row or not _verify_password(password, row["password_hash"]):
        return None
    user = dict(row)
    token = create_token(user["user_id"], user["email"], user["role"])
    refresh_id = f"rt-{uuid.uuid4().hex}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO refresh_tokens (token_id, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (refresh_id, user["user_id"], time.time() + 7 * 86400, time.time()),
        )
    return {
        "accessToken": token,
        "refreshToken": refresh_id,
        "user": {"userId": user["user_id"], "email": user["email"], "name": user["name"], "role": user["role"]},
    }


def refresh(refresh_token: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT rt.*, u.email, u.name, u.role FROM refresh_tokens rt JOIN users u ON u.user_id = rt.user_id WHERE rt.token_id = ? AND rt.expires_at > ? AND u.active = 1",
            (refresh_token, time.time()),
        ).fetchone()
    if not row:
        return None
    token = create_token(row["user_id"], row["email"], row["role"])
    return {
        "accessToken": token,
        "user": {"userId": row["user_id"], "email": row["email"], "name": row["name"], "role": row["role"]},
    }


def get_user(user_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT user_id, email, name, role, active FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return row_to_dict(row)


def list_users() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id, email, name, role, active, created_at FROM users ORDER BY created_at").fetchall()
    return [{"userId": r["user_id"], "email": r["email"], "name": r["name"], "role": r["role"], "active": bool(r["active"])} for r in rows]

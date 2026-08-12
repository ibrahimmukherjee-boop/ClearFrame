"""TrustRegistry PKI certificate service."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from app.config import JWT_SECRET
from app.database import get_conn
from app.services import audit as audit_svc
from app.services.agents import _log_pipeline, get_current_agent
from app.services.safepulse import get_operator

TRUST_LEVELS = ["SANDBOX", "RESTRICTED", "STANDARD", "ELEVATED", "CRITICAL"]


def _sign(payload: str) -> str:
    sig = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{sig}"


def _verify(payload: str, signature: str) -> bool:
    if not signature.startswith("hmac-sha256:"):
        return False
    expected = _sign(payload)
    return hmac.compare_digest(expected, signature)


def get_certificate() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM certificates ORDER BY issued_at DESC LIMIT 1").fetchone()
    if not row:
        return None
    return {
        "certId": row["cert_id"],
        "agentId": row["agent_id"],
        "trustLevel": row["trust_level"],
        "capabilities": json.loads(row["capabilities"]),
        "issuedAt": row["issued_at"],
        "expiresAt": row["expires_at"],
        "revoked": bool(row["revoked"]),
        "signature": row["signature"],
    }


def issue_certificate(trust_level: str, ttl_hours: int) -> dict[str, Any]:
    agent = get_current_agent()
    operator = get_operator()
    if not agent:
        return {"ok": False, "message": "No agent defined. Go to Agent Builder first."}
    if not operator or not operator["verified"]:
        return {"ok": False, "message": "Operator not verified. Complete SafePulse authentication first."}

    cert_id = f"cert-{uuid.uuid4().hex[:8]}"
    issued_at = time.time()
    expires_at = issued_at + ttl_hours * 3600
    sig_input = f"{cert_id}:{agent['agentId']}:{trust_level}:{issued_at}"
    signature = _sign(sig_input)

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO certificates (cert_id, agent_id, trust_level, capabilities, issued_at, expires_at, revoked, signature)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
            (cert_id, agent["agentId"], trust_level, json.dumps(agent["capabilities"]), issued_at, expires_at, signature),
        )
    audit_svc.write_event("cert_issued", cert_id, {"agent_id": agent["agentId"], "trust_level": trust_level})
    _log_pipeline("TrustRegistry: cert issued", f"{cert_id} level={trust_level}")
    return {"ok": True, "message": "Certificate issued", "cert": get_certificate()}


def verify_certificate() -> dict[str, Any]:
    cert = get_certificate()
    if not cert:
        return {"ok": False, "message": "No certificate in state. Issue one first."}
    if cert["revoked"]:
        return {"ok": False, "message": f"Certificate {cert['certId']} is REVOKED."}
    if time.time() > cert["expiresAt"]:
        return {"ok": False, "message": f"Certificate {cert['certId']} has EXPIRED."}
    sig_input = f"{cert['certId']}:{cert['agentId']}:{cert['trustLevel']}:{cert['issuedAt']}"
    if not _verify(sig_input, cert.get("signature", "")):
        return {"ok": False, "message": f"Certificate {cert['certId']} signature INVALID."}
    return {"ok": True, "message": f"Certificate {cert['certId']} is VALID at trust level {cert['trustLevel']}."}


def revoke_certificate() -> dict[str, Any]:
    cert = get_certificate()
    if not cert:
        return {"ok": False, "message": "No certificate to revoke."}
    with get_conn() as conn:
        conn.execute("UPDATE certificates SET revoked = 1 WHERE cert_id = ?", (cert["certId"],))
    audit_svc.write_event("cert_revoked", cert["certId"], {})
    _log_pipeline("TrustRegistry: cert revoked", cert["certId"])
    return {"ok": True, "message": f"Certificate {cert['certId']} has been REVOKED."}

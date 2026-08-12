"""SafePulse behavioural biometric service."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.database import get_conn
from app.services import audit as audit_svc
from app.services.agents import _log_pipeline


def compare_profiles(p1: list[float], p2: list[float]) -> float:
    length = min(len(p1), len(p2))
    if length == 0:
        return 0.0
    diff = 0.0
    for i in range(length):
        mx = max(p1[i], p2[i]) or 1.0
        diff += abs(p1[i] - p2[i]) / mx
    return max(0.0, min(1.0, 1.0 - diff / length))


def get_operator() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM operators ORDER BY timestamp DESC LIMIT 1").fetchone()
    if not row:
        return None
    return {
        "operatorId": row["operator_id"],
        "name": row["name"],
        "verified": bool(row["verified"]),
        "trustScore": row["trust_score"],
        "authMethod": row["auth_method"],
        "timestamp": row["timestamp"],
        "enrolled": row["profile"] is not None,
    }


def enroll(profile: list[float]) -> dict[str, Any]:
    operator_id = f"op-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        conn.execute("DELETE FROM operators")
        conn.execute(
            "INSERT INTO operators (operator_id, name, verified, trust_score, auth_method, profile, timestamp) VALUES (?, ?, 0, 0, ?, ?, ?)",
            (operator_id, "Enrolled Operator", "Keystroke Dynamics", json.dumps(profile), time.time()),
        )
    return {"enrolled": True, "operatorId": operator_id}


def verify(profile: list[float], threshold: float = 0.7) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM operators ORDER BY timestamp DESC LIMIT 1").fetchone()
    if not row or not row["profile"]:
        return {"success": False, "score": 0, "message": "No enrolled profile"}
    stored = json.loads(row["profile"])
    score = round(compare_profiles(stored, profile) * 100)
    success = score >= threshold * 100
    with get_conn() as conn:
        conn.execute(
            "UPDATE operators SET verified = ?, trust_score = ?, name = ?, timestamp = ? WHERE operator_id = ?",
            (int(success), score / 100, "Verified Operator" if success else row["name"], time.time(), row["operator_id"]),
        )
    audit_svc.write_event("safepulse_verify", row["operator_id"], {"score": score, "success": success})
    _log_pipeline("SafePulse auth", f"{'PASS' if success else 'FAIL'} score={score / 100:.2f}")
    return {"success": success, "score": score, "operatorId": row["operator_id"]}


def reset() -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM operators")

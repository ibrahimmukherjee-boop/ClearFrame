"""Unified AI action audit log with reasoning chain and HITL decisions."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.database import get_conn
from app.services import audit as audit_svc


def init_action_audit_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS action_audit (
                action_id TEXT PRIMARY KEY,
                session_id TEXT,
                agent_id TEXT,
                agent_name TEXT,
                timestamp REAL,
                tool TEXT,
                args TEXT,
                reasoning TEXT,
                alignment INTEGER,
                status TEXT,
                hitl_decision TEXT,
                operator_id TEXT,
                operator_note TEXT,
                policy_cards TEXT,
                result_preview TEXT
            )
            """
        )


def log_action(
    session_id: str,
    agent_id: str,
    agent_name: str,
    tool: str,
    args: dict[str, Any],
    reasoning: str = "",
    alignment: int = 80,
    status: str = "allowed",
    policy_cards: list[str] | None = None,
    result_preview: str = "",
) -> dict[str, Any]:
    action_id = f"act-{uuid.uuid4().hex[:8]}"
    entry = {
        "actionId": action_id,
        "sessionId": session_id,
        "agentId": agent_id,
        "agentName": agent_name,
        "timestamp": time.time(),
        "tool": tool,
        "args": json.dumps(args)[:500],
        "reasoning": reasoning,
        "alignment": alignment,
        "status": status,
        "hitlDecision": None,
        "operatorId": None,
        "operatorNote": None,
        "policyCards": policy_cards or [],
        "resultPreview": result_preview[:300],
    }
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO action_audit
               (action_id, session_id, agent_id, agent_name, timestamp, tool, args, reasoning, alignment, status, policy_cards, result_preview)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (action_id, session_id, agent_id, agent_name, entry["timestamp"], tool, entry["args"], reasoning, alignment, status, json.dumps(policy_cards or []), entry["resultPreview"]),
        )
    audit_svc.write_event("agent_action", session_id, {"actionId": action_id, "tool": tool, "status": status, "reasoning": reasoning[:200]})
    return entry


def list_actions(session_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if session_id:
            rows = conn.execute("SELECT * FROM action_audit WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?", (session_id, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM action_audit ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    return [_serialize(dict(r)) for r in rows]


def get_reasoning_chain(session_id: str | None = None) -> list[dict[str, Any]]:
    actions = list_actions(session_id)
    return [
        {
            "step": i,
            "actionId": a["actionId"],
            "tool": a["tool"],
            "reasoning": a["reasoning"],
            "alignment": a["alignment"],
            "status": a["status"],
            "hitlDecision": a["hitlDecision"],
            "timestamp": a["timestamp"],
        }
        for i, a in enumerate(reversed(actions))
    ]


def record_hitl_decision(action_id: str, decision: str, operator_id: str, note: str = "") -> dict[str, Any]:
    """decision: approved | blocked | overridden"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE action_audit SET hitl_decision = ?, operator_id = ?, operator_note = ?, status = ? WHERE action_id = ?",
            (decision, operator_id, note, "allowed" if decision in ("approved", "overridden") else "blocked", action_id),
        )
        row = conn.execute("SELECT * FROM action_audit WHERE action_id = ?", (action_id,)).fetchone()
    if row:
        audit_svc.write_event("hitl_decision", row["session_id"], {"actionId": action_id, "decision": decision, "operator": operator_id, "note": note})
    return _serialize(dict(row)) if row else {}


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    import datetime
    ts = row["timestamp"]
    return {
        "actionId": row["action_id"],
        "sessionId": row["session_id"],
        "agentId": row["agent_id"],
        "agentName": row["agent_name"],
        "timestamp": ts,
        "time": datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "",
        "tool": row["tool"],
        "args": row["args"],
        "reasoning": row["reasoning"] or "",
        "alignment": row["alignment"],
        "status": row["status"],
        "hitlDecision": row.get("hitl_decision"),
        "operatorId": row.get("operator_id"),
        "operatorNote": row.get("operator_note") or "",
        "policyCards": json.loads(row.get("policy_cards") or "[]"),
        "resultPreview": row.get("result_preview") or "",
    }

"""ClearFrame runtime session service."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from app.config import USE_CLEARFRAME_RUNTIME
from app.database import get_conn
from app.services import audit as audit_svc
from app.services.agents import _log_pipeline, get_current_agent
from app.services.safepulse import get_operator
from app.services.trust import get_certificate
from app.services import aegis as aegis_svc
from app.services import sonar as sonar_svc
from app.services import clearframe_ops as ops_svc
from app.services import llm_agent as llm_svc
from app.services import governance as governance_svc
from app.services import action_audit as action_audit_svc

DEFAULT_TOOL_CALLS = [
    ("tc-1", "web_search", 'query: "cybersecurity best practices 2026"', 95, "allowed"),
    ("tc-2", "send_email", 'to: "team@company.com", subject: "Security Report"', 88, "allowed"),
    ("tc-3", "file_delete", 'path: "/important/data.csv"', 25, "human_review"),
    ("tc-4", "db_query", 'query: "DROP TABLE users"', 5, "blocked"),
    ("tc-5", "api_call", 'endpoint: "/internal/secrets"', 35, "human_review"),
]


def get_session() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM sessions ORDER BY started_at DESC LIMIT 1").fetchone()
    if not row:
        return None
    return {
        "sessionId": row["session_id"],
        "agentId": row["agent_id"],
        "status": row["status"],
        "startedAt": row["started_at"],
        "endedAt": row["ended_at"],
        "runtime": row["runtime"] if "runtime" in row.keys() else "builtin",
    }


def get_audit_log() -> list[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT steps FROM sessions ORDER BY started_at DESC LIMIT 1").fetchone()
    if not row or not row["steps"]:
        return []
    return json.loads(row["steps"])


def get_rtl_trace() -> list[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT steps FROM sessions ORDER BY started_at DESC LIMIT 1").fetchone()
    if not row or not row["steps"]:
        return []
    entries = json.loads(row["steps"])
    return [{"step": i, "tool": e.get("tool"), "action": e.get("action"), "status": e.get("status"), "alignment": e.get("alignment")} for i, e in enumerate(entries)]


def _persist_session(session_id: str, agent_id: str, started_at: float, audit_entries: list[dict[str, Any]], runtime: str, trace: list | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, agent_id, status, started_at, steps, alerts, runtime) VALUES (?, ?, 'running', ?, ?, '[]', ?)",
            (session_id, agent_id, started_at, json.dumps(audit_entries), runtime),
        )


async def start_session() -> dict[str, Any]:
    agent = get_current_agent()
    operator = get_operator()
    cert = get_certificate()
    if not agent:
        return {"ok": False, "message": "No agent defined. Go to Agent Builder and save an agent."}
    if not operator or not operator.get("verified"):
        return {"ok": False, "message": "Operator not verified via SafePulse."}
    if not cert or cert.get("revoked"):
        return {"ok": False, "message": "No valid TrustRegistry certificate."}
    if agent.get("status") == "suspended":
        return {"ok": False, "message": "Agent is suspended. Activate before starting a session."}

    goal = agent.get("description") or agent["name"]
    runtime_result = await llm_svc.run_agent_loop(agent, goal)

    session_id = runtime_result["sessionId"]
    audit_entries = runtime_result["auditLog"]
    started_at = runtime_result["startedAt"]
    runtime = runtime_result.get("runtime", "ollama")
    trace = runtime_result.get("trace", [])

    for i, entry in enumerate(audit_entries):
        trace_step = trace[i] if i < len(trace) else {}
        reasoning = ""
        if isinstance(trace_step, dict):
            dec = trace_step.get("decision", {})
            if isinstance(dec, dict):
                reasoning = dec.get("thought", dec.get("answer", ""))
        reasoning = reasoning or entry.get("action", "")
        action_audit_svc.log_action(
            session_id, agent["agentId"], agent["name"],
            entry.get("tool", "unknown"), {"action": entry.get("action", "")},
            reasoning=reasoning,
            alignment=int(entry.get("alignment", 80)),
            status=entry.get("status", "allowed"),
            result_preview=str(entry.get("result", ""))[:200],
        )
        audit_svc.write_event("tool_call", session_id, entry)

    _persist_session(session_id, agent["agentId"], started_at, audit_entries, runtime, trace)
    aegis_svc.enqueue_from_audit(session_id, audit_entries)
    ops_svc.register_session(session_id, goal, agent.get("capabilities", []))
    sonar_svc.record_drift(agent["name"], session_id)
    governance_svc.collect_evidence()
    _log_pipeline("Session started", f"{session_id} ({runtime})")
    return {
        "ok": True,
        "message": f"Session {session_id} started via {runtime}",
        "session": get_session(),
        "auditLog": audit_entries,
        "trace": trace,
        "answer": runtime_result.get("answer", ""),
    }

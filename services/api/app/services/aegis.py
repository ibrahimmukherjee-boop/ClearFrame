"""Aegis human-in-the-loop approval service."""
from __future__ import annotations

import time
from typing import Any

from app.database import get_conn
from app.services.agents import _log_pipeline
from app.services import action_audit as action_audit_svc


def _status_from_alignment(alignment: int, tool: str) -> str:
    if alignment < 20 or tool in {"file_delete", "db_query"} and alignment < 30:
        return "blocked"
    if alignment < 50 or tool in {"api_call", "file_delete", "email_send", "send_email"}:
        return "human_review"
    return "allowed"


def enqueue_from_audit(session_id: str, audit_entries: list[dict[str, Any]]) -> None:
    sid = session_id.replace("-", "")[:8]
    queued: list[tuple[str, str, int, str, str]] = []
    with get_conn() as conn:
        conn.execute("DELETE FROM tool_calls WHERE session_id = ?", (session_id,))
        for i, entry in enumerate(audit_entries):
            alignment = int(entry.get("alignment", 80))
            tool = entry.get("tool", "unknown")
            status = entry.get("status") or _status_from_alignment(alignment, tool)
            if status == "flagged":
                status = "human_review"
            reasoning = entry.get("reasoning") or entry.get("action", "")
            tc_id = f"tc-{sid}-{i + 1}"
            conn.execute(
                "INSERT OR REPLACE INTO tool_calls (id, session_id, tool, args, alignment, status, reasoning) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (tc_id, session_id, tool, entry.get("action", ""), alignment, status, reasoning),
            )
            queued.append((tool, entry.get("action", ""), alignment, status, reasoning))
    # Log after releasing the SQLite write lock (nested get_conn deadlocks otherwise).
    for tool, action, alignment, status, reasoning in queued:
        action_audit_svc.log_action(
            session_id, "", "",
            tool, {"args": action},
            reasoning=reasoning, alignment=alignment, status=status,
        )


def enqueue_session(session_id: str, agent_name: str, trust_level: str) -> None:
    with get_conn() as conn:
        for tc_id, tool, args, alignment, status in [
            ("tc-1", "web_search", 'query: "cybersecurity"', 95, "allowed"),
            ("tc-2", "send_email", 'to: team@company.com', 88, "allowed"),
            ("tc-3", "file_delete", 'path: /important/data.csv', 25, "human_review"),
            ("tc-4", "db_query", 'query: DROP TABLE users', 5, "blocked"),
            ("tc-5", "api_call", 'endpoint: /internal/secrets', 35, "human_review"),
        ]:
            conn.execute(
                "INSERT OR IGNORE INTO tool_calls (id, session_id, tool, args, alignment, status) VALUES (?, ?, ?, ?, ?, ?)",
                (tc_id, session_id, tool, args, alignment, status),
            )


def list_tool_calls() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM tool_calls
               ORDER BY CASE status WHEN 'pending_approval' THEN 0 ELSE 1 END, id"""
        ).fetchall()
    result = []
    for r in rows:
        item = {
            "id": r["id"],
            "sessionId": r["session_id"],
            "tool": r["tool"],
            "args": r["args"],
            "alignment": r["alignment"],
            "status": r["status"],
            "reasoning": r["reasoning"] if "reasoning" in r.keys() else "",
        }
        result.append(item)
    return result


def approve(call_id: str, operator_id: str = "operator", note: str = "") -> None:
    _hitl_decision(call_id, "approved", operator_id, note)


def block(call_id: str, operator_id: str = "operator", note: str = "") -> None:
    _hitl_decision(call_id, "blocked", operator_id, note)


def override(call_id: str, operator_id: str = "operator", note: str = "") -> None:
    """Human override — force-allow a flagged action with documented justification."""
    _hitl_decision(call_id, "overridden", operator_id, note)


def _hitl_decision(call_id: str, decision: str, operator_id: str, note: str) -> None:
    status = "allowed" if decision in ("approved", "overridden") else "blocked"
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tool_calls WHERE id = ?", (call_id,)).fetchone()
        conn.execute(
            "UPDATE tool_calls SET status = ? WHERE id = ?",
            (status if decision != "overridden" else "overridden", call_id),
        )
        try:
            conn.execute(
                "UPDATE tool_calls SET hitl_action = ?, operator_id = ?, operator_note = ? WHERE id = ?",
                (decision, operator_id, note, call_id),
            )
        except Exception:
            pass
    _log_pipeline(f"Aegis: {decision}", f"{call_id} — {note}" if note else call_id)
    if row and row["session_id"]:
        _sync_ops_approval(row["session_id"], row["tool"], approved=decision != "blocked")
        actions = action_audit_svc.list_actions(row["session_id"])
        for a in actions:
            if a["tool"] == row["tool"] and not a.get("hitlDecision"):
                action_audit_svc.record_hitl_decision(a["actionId"], decision, operator_id, note)
                break


def approve_legacy(call_id: str) -> None:
    approve(call_id)


def _sync_ops_approval(session_id: str, tool: str, approved: bool) -> None:
    from app.services import clearframe_ops as ops_svc
    queue = ops_svc.list_queue(session_id)
    for item in queue:
        if item.get("tool_name") == tool or item.get("tool") == tool:
            ops_svc.approve_queue_item(session_id, item.get("id", item.get("queue_id", "")), approved)
            break


def reset_calls() -> None:
    from app.production import is_production
    defaults = [
        ("tc-1", None, "web_search", 'query: "cybersecurity best practices 2026"', 95, "allowed"),
        ("tc-2", None, "send_email", 'to: "team@company.com"', 88, "allowed"),
        ("tc-3", None, "file_delete", 'path: "/important/data.csv"', 25, "human_review"),
        ("tc-4", None, "db_query", 'query: "DROP TABLE users"', 5, "blocked"),
        ("tc-5", None, "api_call", 'endpoint: "/internal/secrets"', 35, "human_review"),
    ]
    with get_conn() as conn:
        conn.execute("DELETE FROM tool_calls")
        if is_production():
            return
        for tc_id, sess, tool, args, alignment, status in defaults:
            conn.execute(
                "INSERT INTO tool_calls (id, session_id, tool, args, alignment, status) VALUES (?, ?, ?, ?, ?, ?)",
                (tc_id, sess, tool, args, alignment, status),
            )

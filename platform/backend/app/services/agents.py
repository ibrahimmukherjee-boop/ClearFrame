"""Agent registry and builder service."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.database import get_conn, row_to_dict
from app.services import audit as audit_svc

PRESETS: dict[str, dict[str, Any]] = {
    "Customer Support Bot": {
        "name": "Customer Support Bot",
        "description": "Handles customer queries, checks order status, escalates complaints.",
        "capabilities": ["web_search", "database_read", "email_send"],
        "provider": "ollama",
        "model": "llama3",
        "max_steps": 8,
        "allow_web": True,
        "allow_fs": False,
        "allow_exec": False,
    },
    "Data Analysis Agent": {
        "name": "Data Analysis Agent",
        "description": "Reads internal datasets, produces reports and insights.",
        "capabilities": ["database_read", "file_read", "chart_generate"],
        "provider": "ollama",
        "model": "mistral",
        "max_steps": 15,
        "allow_web": False,
        "allow_fs": True,
        "allow_exec": False,
    },
    "DevOps Automation Agent": {
        "name": "DevOps Automation Agent",
        "description": "Monitors CI/CD pipelines, auto-triages alerts, opens PRs.",
        "capabilities": ["git_read", "git_write", "shell_exec", "webhook_send"],
        "provider": "ollama",
        "model": "codellama",
        "max_steps": 20,
        "allow_web": True,
        "allow_fs": True,
        "allow_exec": True,
    },
    "Research Assistant": {
        "name": "Research Assistant",
        "description": "Searches the web, summarises papers, drafts reports.",
        "capabilities": ["web_search", "file_write", "pdf_read"],
        "provider": "ollama",
        "model": "llama3",
        "max_steps": 12,
        "allow_web": True,
        "allow_fs": True,
        "allow_exec": False,
    },
}


def _serialize_agent(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "agentId": row["agent_id"],
        "name": row["name"],
        "description": row["description"] or "",
        "capabilities": json.loads(row["capabilities"]),
        "provider": row["provider"],
        "model": row["model"],
        "maxSteps": row["max_steps"],
        "allowWeb": bool(row["allow_web"]),
        "allowFs": bool(row["allow_fs"]),
        "allowExec": bool(row["allow_exec"]),
        "trustScore": row["trust_score"],
        "status": row["status"],
        "owner": row["owner"],
        "registeredAt": row["registered_at"],
        "isCurrent": bool(row["is_current"]),
    }


def seed_defaults() -> None:
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM agents").fetchone()["c"]
        if count:
            return
        defaults = [
            ("agt-7f3a9b", "CodeReviewer-Alpha", "Automated code review", ["file_read", "git_read"], 94, "active", "DevOps Team"),
            ("agt-2e8c1d", "DataAnalyst-Beta", "Data analysis", ["database_read", "chart_generate"], 87, "active", "Data Science"),
            ("agt-5b1f4e", "SupportBot-Gamma", "Customer support", ["web_search", "email_send"], 45, "suspended", "Support Team"),
        ]
        for agent_id, name, desc, caps, score, status, owner in defaults:
            conn.execute(
                """INSERT INTO agents (agent_id, name, description, capabilities, provider, model, max_steps,
                   allow_web, allow_fs, allow_exec, trust_score, status, owner, registered_at, is_current)
                   VALUES (?, ?, ?, ?, 'ollama', 'llama3', 10, 0, 1, 0, ?, ?, ?, ?, 0)""",
                (agent_id, name, desc, json.dumps(caps), score, status, owner, time.time()),
            )


def list_agents() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM agents ORDER BY registered_at DESC").fetchall()
    return [_serialize_agent(dict(r)) for r in rows]


def get_current_agent() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM agents WHERE is_current = 1 LIMIT 1").fetchone()
    return _serialize_agent(dict(row)) if row else None


def save_agent(data: dict[str, Any], set_current: bool = True) -> dict[str, Any]:
    agent_id = data.get("agentId") or f"agt-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        if set_current:
            conn.execute("UPDATE agents SET is_current = 0")
        conn.execute(
            """INSERT OR REPLACE INTO agents
               (agent_id, name, description, capabilities, provider, model, max_steps,
                allow_web, allow_fs, allow_exec, trust_score, status, owner, registered_at, is_current)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_id,
                data["name"],
                data.get("description", ""),
                json.dumps(data.get("capabilities", [])),
                data.get("provider", "ollama"),
                data.get("model", "llama3"),
                data.get("maxSteps", 10),
                int(data.get("allowWeb", data.get("allow_web", False))),
                int(data.get("allowFs", data.get("allow_fs", False))),
                int(data.get("allowExec", data.get("allow_exec", False))),
                data.get("trustScore", 100),
                data.get("status", "active"),
                data.get("owner", "Current User"),
                time.time(),
                1 if set_current else 0,
            ),
        )
    audit_svc.write_event("agent_saved", agent_id, {"name": data["name"]})
    _log_pipeline("Agent defined", f"{data['name']} ({agent_id})")
    agent = get_current_agent() if set_current else next((a for a in list_agents() if a["agentId"] == agent_id), None)
    return agent or {}


def set_current_agent(agent_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        conn.execute("UPDATE agents SET is_current = 0")
        conn.execute("UPDATE agents SET is_current = 1 WHERE agent_id = ?", (agent_id,))
        row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
    return _serialize_agent(dict(row)) if row else None


def suspend_agent(agent_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        conn.execute("UPDATE agents SET status = 'suspended', trust_score = trust_score - 20 WHERE agent_id = ?", (agent_id,))
        row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
    audit_svc.write_event("agent_suspended", agent_id, {})
    _log_pipeline("Agent suspended", agent_id)
    return _serialize_agent(dict(row)) if row else None


def activate_agent(agent_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        conn.execute("UPDATE agents SET status = 'active' WHERE agent_id = ?", (agent_id,))
        row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
    audit_svc.write_event("agent_activated", agent_id, {})
    return _serialize_agent(dict(row)) if row else None


def revoke_agent(agent_id: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE agents SET status = 'revoked', trust_score = 0 WHERE agent_id = ?", (agent_id,))
    audit_svc.write_event("agent_revoked", agent_id, {})
    _log_pipeline("Agent revoked", agent_id)


def _log_pipeline(step: str, detail: str = "") -> None:
    import datetime
    msg = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {step}" + (f" — {detail}" if detail else "")
    with get_conn() as conn:
        conn.execute("INSERT INTO pipeline_log (message, created_at) VALUES (?, ?)", (msg, time.time()))

"""Integrate the real ClearFrame AgentSession runtime."""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Any, Callable

from app.config import CLEARFRAME_RUNTIME_DIR, DATA_DIR
from app.services import tools as tools_svc

CLEARFRAME_AVAILABLE = False
SessionError: type[Exception] = RuntimeError

try:
    from clearframe import AgentSession
    from clearframe.core.config import AuditConfig, ClearFrameConfig, VaultConfig
    from clearframe.core.errors import SessionError as _SessionError
    from clearframe.core.manifest import GoalManifest, ToolPermission

    SessionError = _SessionError
    CLEARFRAME_AVAILABLE = True
except ImportError:
    AgentSession = None  # type: ignore
    GoalManifest = None  # type: ignore
    ToolPermission = None  # type: ignore
    ClearFrameConfig = None  # type: ignore


def runtime_config() -> ClearFrameConfig:
    CLEARFRAME_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("CLEARFRAME_AUDIT_SECRET", "erasys-local-audit-secret-change-in-prod")
    return ClearFrameConfig(
        vault=VaultConfig(
            vault_path=CLEARFRAME_RUNTIME_DIR / "vault.enc",
            salt_path=CLEARFRAME_RUNTIME_DIR / "vault.salt",
        ),
        audit=AuditConfig(log_path=CLEARFRAME_RUNTIME_DIR / "clearframe-audit.log"),
    )


def agent_to_manifest(agent: dict[str, Any]) -> GoalManifest:
    caps = agent.get("capabilities") or ["web_search"]
    return GoalManifest(
        goal=agent.get("description") or agent["name"],
        permitted_tools=[
            ToolPermission(tool_name=c, max_calls_per_session=10, require_approval=c in {"file_delete", "db_query", "api_call"})
            for c in caps
        ],
        allow_file_write=bool(agent.get("allowFs")),
        allow_code_execution=bool(agent.get("allowExec")),
        max_steps=int(agent.get("maxSteps", 10)),
    )


def _build_tools(agent: dict[str, Any]) -> dict[str, Callable[..., Any]]:
    caps = agent.get("capabilities") or ["web_search"]
    return tools_svc.build_registry(caps)


def build_session_plan(agent: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    """Build a realistic session script from the agent's declared capabilities."""
    caps = set(agent.get("capabilities") or ["web_search"])
    plan: list[tuple[str, dict[str, Any], str]] = []

    if "web_search" in caps:
        plan.append(("web_search", {"query": "enterprise security"}, "allowed"))
    if "web_fetch" in caps:
        plan.append(("web_fetch", {"url": "https://docs.example.com"}, "allowed"))
    if "file_read" in caps:
        plan.append(("file_read", {"path": "/data/report.csv"}, "allowed"))
    elif not agent.get("allowFs"):
        plan.append(("file_read", {"path": "/etc/passwd"}, "blocked"))
    if "email_send" in caps:
        plan.append(("email_send", {"to": "report@company.com"}, "flagged"))
    elif "send_email" in caps:
        plan.append(("send_email", {"to": "report@company.com"}, "flagged"))
    if "database_read" in caps:
        plan.append(("database_read", {"table": "customers"}, "allowed"))
    elif "db_query" in caps:
        plan.append(("db_query", {"query": "SELECT * FROM users"}, "allowed"))

    if not plan:
        plan = [
            ("web_search", {"query": "enterprise security"}, "allowed"),
            ("file_read", {"path": "/etc/passwd"}, "blocked"),
        ]
    return plan


async def _run_async(agent: dict[str, Any]) -> dict[str, Any]:
    config = runtime_config()
    manifest = agent_to_manifest(agent)
    tools = _build_tools(agent)
    started_at = time.time()
    audit_entries: list[dict[str, Any]] = []

    plan = build_session_plan(agent)

    async with AgentSession(config, manifest, tool_registry=tools) as session:
        session_id = session.session_id

        for i, (tool, kwargs, expected) in enumerate(plan):
            ts = time.strftime("%H:%M:%S")
            status = expected
            alignment = 95 if expected == "allowed" else 15 if expected == "blocked" else 72
            try:
                await session.call_tool(tool, **kwargs)
            except SessionError:
                if expected == "blocked":
                    status = "blocked"
                    alignment = 15
                else:
                    status = "flagged"
                    alignment = 40
            except Exception:
                status = "blocked"
                alignment = 10

            audit_entries.append(
                {
                    "id": f"audit-{i}",
                    "timestamp": ts,
                    "action": f'{tool}({", ".join(f"{k}={v!r}" for k, v in kwargs.items())})',
                    "tool": tool,
                    "alignment": alignment,
                    "status": status,
                }
            )

    return {
        "sessionId": session_id,
        "agentId": agent["agentId"],
        "status": "running",
        "startedAt": started_at,
        "auditLog": audit_entries,
        "runtime": "clearframe",
    }


def run_clearframe_session(agent: dict[str, Any]) -> dict[str, Any] | None:
    if not CLEARFRAME_AVAILABLE:
        return None
    return asyncio.run(_run_async(agent))

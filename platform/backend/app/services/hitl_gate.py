"""Pre-execution human-in-the-loop gate — blocks tool runs until operator decision."""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Any

from app.database import get_conn
from app.production import is_production

HITL_TIMEOUT_SEC = int(os.environ.get("CLEARFRAME_HITL_TIMEOUT_SEC", "120"))
# Dev/demo defaults to auto-approve so the one-click pipeline does not block on a
# human decision — the pending→approved transition is still written to the audit
# trail and surfaced in the Aegis tab. Production forces manual approval.
_HITL_AUTO_DEFAULT = "false" if is_production() else "true"
HITL_AUTO_APPROVE = os.environ.get("CLEARFRAME_HITL_AUTO_APPROVE", _HITL_AUTO_DEFAULT).lower() in {"1", "true", "yes"}
if is_production():
    HITL_AUTO_APPROVE = False  # never auto-approve in production


def _call_status(call_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT status FROM tool_calls WHERE id = ?", (call_id,)).fetchone()
    return row["status"] if row else None


def create_pending(
    session_id: str,
    tool: str,
    args: dict[str, Any],
    alignment: int,
    reasoning: str,
    policy_reasons: list[str] | None = None,
) -> str:
    call_id = f"tc-{uuid.uuid4().hex[:8]}"
    args_str = json.dumps(args)[:500]
    note = reasoning
    if policy_reasons:
        note = f"{reasoning} | Policy: {'; '.join(policy_reasons)}"
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO tool_calls (id, session_id, tool, args, alignment, status, reasoning)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (call_id, session_id, tool, args_str, alignment, "pending_approval", note[:1000]),
        )
    return call_id


async def wait_for_decision(call_id: str, timeout_sec: int | None = None) -> str:
    """Returns: approved | blocked | timeout."""
    deadline = time.time() + (timeout_sec or HITL_TIMEOUT_SEC)
    while time.time() < deadline:
        status = _call_status(call_id)
        if status is None:
            return "blocked"
        if status == "pending_approval":
            if HITL_AUTO_APPROVE:
                from app.services import aegis as aegis_svc
                aegis_svc.approve(call_id, "system", "Auto-approved (development mode)")
                return "approved"
            await asyncio.sleep(0.5)
            continue
        if status in {"allowed", "approved", "overridden"}:
            return "approved"
        if status == "blocked":
            return "blocked"
        await asyncio.sleep(0.5)

    from app.services import aegis as aegis_svc
    aegis_svc.block(call_id, "system", "HITL timeout — no operator response within limit")
    return "timeout"


async def governed_execute(
    session_id: str,
    agent: dict[str, Any],
    tool: str,
    args: dict[str, Any],
    step: int,
    reasoning: str = "",
) -> dict[str, Any]:
    """Evaluate policy, gate on HITL, then execute tool. Returns audit entry dict."""
    from app.services import policy as policy_svc
    from app.services import tools as tools_svc
    from app.services import sonar as sonar_svc

    ctx = {"trustScore": agent.get("trustScore", 100), "agentStatus": agent.get("status", "active")}
    pol = policy_svc.evaluate(tool, args, ctx)
    ts = time.strftime("%H:%M:%S")
    alignment = 95 if pol["allowed"] else 15 if pol["disposition"] == "deny" else 55

    if pol["disposition"] == "deny":
        sonar_svc.record_event(agent.get("name", "unknown"), "policy_violation", "high",
                               f"Blocked {tool}: {'; '.join(pol['reasons'])}", session_id)
        return {
            "id": f"audit-{step}", "timestamp": ts,
            "action": f"{tool}({json.dumps(args)[:80]})",
            "tool": tool, "alignment": alignment, "status": "blocked",
            "policyReasons": pol["reasons"], "executed": False,
        }

    if pol["disposition"] == "require_approval":
        call_id = create_pending(session_id, tool, args, alignment, reasoning or f"Step {step}", pol["reasons"])
        decision = await wait_for_decision(call_id)
        if decision != "approved":
            sonar_svc.record_event(agent.get("name", "unknown"), "hitl_denied", "medium",
                                   f"HITL denied {tool} ({decision})", session_id)
            return {
                "id": f"audit-{step}", "timestamp": ts,
                "action": f"{tool}({json.dumps(args)[:80]})",
                "tool": tool, "alignment": alignment,
                "status": "blocked" if decision == "blocked" else "timeout",
                "policyReasons": pol["reasons"], "hitlCallId": call_id, "executed": False,
            }

    result = tools_svc.execute_tool(tool, **args)
    status = "allowed" if pol["allowed"] else "human_review"
    return {
        "id": f"audit-{step}", "timestamp": ts,
        "action": f"{tool}({json.dumps(args)[:80]})",
        "tool": tool, "alignment": alignment, "status": status,
        "result": str(result)[:200], "executed": True,
    }

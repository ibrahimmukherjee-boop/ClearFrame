"""Platform metrics — derived from live audit/session data only."""
from __future__ import annotations

from typing import Any

from app.database import get_conn


def _gather_stats() -> dict[str, Any]:
    with get_conn() as conn:
        agents = conn.execute("SELECT COUNT(*) AS c FROM agents").fetchone()["c"]
        operators = conn.execute("SELECT COUNT(*) AS c FROM operators WHERE verified = 1").fetchone()["c"]
        sessions = conn.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"]
        total_calls = conn.execute("SELECT COUNT(*) AS c FROM tool_calls").fetchone()["c"]
        blocked = conn.execute(
            "SELECT COUNT(*) AS c FROM tool_calls WHERE status IN ('blocked', 'timeout')"
        ).fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM tool_calls WHERE status = 'pending_approval'"
        ).fetchone()["c"]
        hitl_total = conn.execute(
            "SELECT COUNT(*) AS c FROM tool_calls WHERE status IN ('human_review', 'pending_approval', 'overridden')"
        ).fetchone()["c"]
        hitl_resolved = conn.execute(
            "SELECT COUNT(*) AS c FROM action_audit WHERE hitl_decision IS NOT NULL"
        ).fetchone()["c"]
        threats = conn.execute("SELECT COUNT(*) AS c FROM threat_events").fetchone()["c"]
        avg_align_row = conn.execute("SELECT AVG(alignment) AS a FROM tool_calls").fetchone()
        avg_alignment = round(float(avg_align_row["a"] or 0), 1)

        auth_row = conn.execute(
            "SELECT AVG(trust_score) AS a FROM operators WHERE verified = 1"
        ).fetchone()
        auth_score = round(float(auth_row["a"] or 0) * 100, 1)

        policy_blocks = conn.execute(
            "SELECT COUNT(*) AS c FROM policy_evaluations WHERE decision = 'deny'"
        ).fetchone()["c"]
        policy_hitl = conn.execute(
            "SELECT COUNT(*) AS c FROM policy_evaluations WHERE decision = 'require_approval'"
        ).fetchone()["c"]

    block_rate = round((blocked / total_calls) * 100) if total_calls else 0
    hitl_resolution = round((hitl_resolved / max(hitl_total, 1)) * 100) if hitl_total else 100

    return {
        "registeredAgents": agents,
        "verifiedOperators": operators,
        "sessionsRun": sessions,
        "toolCallsTotal": total_calls,
        "toolCallsBlocked": blocked,
        "toolCallsAllowed": max(0, total_calls - blocked - pending),
        "pendingApprovals": pending,
        "threatEvents": threats,
        "policyDenials": policy_blocks,
        "policyHitlTriggers": policy_hitl,
        "avgAlignment": avg_alignment,
        "authTrustScore": auth_score,
        "blockRate": block_rate,
        "hitlResolution": hitl_resolution,
    }


def calculate(_agents: int = 0, _operators: int = 0, _reduction_pct: float = 0) -> dict[str, Any]:
    """Return live governance metrics only — no fabricated cost projections."""
    stats = _gather_stats()

    return {
        "liveStats": stats,
        "dataSource": "live",
        "metrics": [
            {
                "label": "Policy Block Rate",
                "value": stats["blockRate"],
                "target": 15,
                "unit": "%",
                "lowerIsBetter": True,
                "description": f"{stats['toolCallsBlocked']} of {stats['toolCallsTotal']} tool calls blocked by policy",
            },
            {
                "label": "HITL Resolution",
                "value": stats["hitlResolution"],
                "target": 90,
                "unit": "%",
                "description": "Human review decisions recorded in the audit log",
            },
            {
                "label": "Auth Trust Score",
                "value": int(stats["authTrustScore"]),
                "target": 85,
                "unit": "%",
                "description": f"{stats['verifiedOperators']} verified operator(s) via SafePulse",
            },
            {
                "label": "Avg Alignment",
                "value": int(stats["avgAlignment"]),
                "target": 80,
                "unit": "%",
                "description": "Mean goal-alignment score across governed tool calls",
            },
            {
                "label": "Threat Events",
                "value": stats["threatEvents"],
                "target": 0,
                "unit": "",
                "lowerIsBetter": True,
                "description": "Recorded from live sessions and policy violations",
            },
        ],
        "activitySummary": [
            {"label": "Registered agents", "value": stats["registeredAgents"]},
            {"label": "Verified operators", "value": stats["verifiedOperators"]},
            {"label": "Sessions completed", "value": stats["sessionsRun"]},
            {"label": "Tool calls (total)", "value": stats["toolCallsTotal"]},
            {"label": "Policy denials", "value": stats["policyDenials"]},
            {"label": "HITL triggers", "value": stats["policyHitlTriggers"]},
            {"label": "Pending approvals", "value": stats["pendingApprovals"]},
        ],
    }


def live_metrics() -> dict[str, Any]:
    return calculate()

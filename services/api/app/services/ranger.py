"""Apache Ranger-style policy verification for ClearFrame.

Provides an external-governance verification surface enterprises already know:
resource → permission → principal checks, with a dry-run audit report.
"""
from __future__ import annotations

import time
from typing import Any

from app.services import agents as agents_svc
from app.services import policy as policy_svc
from app.services import policy_hub as policy_hub_svc
from app.services import audit as audit_svc


def verify_access(
    principal: str,
    resource: str,
    action: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ranger-like access check against ClearFrame runtime + document policies."""
    ctx = context or {"trustScore": 100, "agentStatus": "active"}
    # Map resource/action to tool evaluation
    tool = action if action else resource
    pol = policy_svc.evaluate(tool, {"resource": resource, "principal": principal}, ctx)
    cards = policy_hub_svc.enforced_cards()
    card_hits = [c for c in cards if _card_blocks(c, tool, resource)]
    allowed = pol["disposition"] != "deny" and not card_hits
    report = {
        "principal": principal,
        "resource": resource,
        "action": action,
        "allowed": allowed,
        "engine": "clearframe-ranger-bridge",
        "runtimePolicy": pol,
        "documentPolicyHits": [{"cardId": c["cardId"], "title": c["title"]} for c in card_hits],
        "checkedAt": time.time(),
    }
    audit_svc.write_event("ranger_verify", resource, {"allowed": allowed, "principal": principal})
    return report


def verify_agent_portfolio() -> dict[str, Any]:
    """Scan all agents for capability / policy conflicts (compliance verification)."""
    findings: list[dict[str, Any]] = []
    for agent in agents_svc.list_agents():
        if agent["status"] == "revoked":
            continue
        for cap in agent.get("capabilities") or []:
            r = verify_access(agent["agentId"], cap, cap, {"trustScore": agent.get("trustScore", 100), "agentStatus": agent["status"]})
            if not r["allowed"]:
                findings.append({"agentId": agent["agentId"], "capability": cap, "detail": r})
    return {
        "ok": len(findings) == 0,
        "agentsScanned": len(agents_svc.list_agents()),
        "violations": findings,
        "engine": "apache-ranger-compatible-verification",
    }


def _card_blocks(card: dict[str, Any], tool: str, resource: str) -> bool:
    text = f"{card.get('title', '')} {card.get('content', '')}".lower()
    if not card.get("enforce", True):
        return False
    # Explicit prohibit language + tool mention
    prohibit = any(w in text for w in ("prohibit", "must not", "forbidden", "unauthorized", "blocked"))
    mentioned = tool.lower() in text or resource.lower() in text
    return prohibit and mentioned

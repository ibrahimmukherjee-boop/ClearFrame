"""Declarative policy engine — evaluated at runtime on every tool call."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.database import get_conn

DEFAULT_POLICIES: list[dict[str, Any]] = [
    {
        "id": "pol-block-delete",
        "name": "Block file deletion",
        "rule": {"tool": "file_delete", "action": "deny"},
        "priority": 100,
    },
    {
        "id": "pol-hitl-email",
        "name": "HITL for outbound email",
        "rule": {"tool": "email_send", "action": "require_approval"},
        "priority": 90,
    },
    {
        "id": "pol-hitl-shell",
        "name": "HITL for shell execution",
        "rule": {"tool": "shell_exec", "action": "require_approval"},
        "priority": 85,
    },
    {
        "id": "pol-block-drop",
        "name": "Block destructive SQL",
        "rule": {"tool": "db_query", "pattern": "DROP|DELETE|TRUNCATE", "action": "deny"},
        "priority": 100,
    },
    {
        "id": "pol-trust-shell",
        "name": "Shell requires elevated trust",
        "rule": {"tool": "shell_exec", "min_trust_score": 80, "action": "deny"},
        "priority": 95,
    },
    {
        "id": "pol-suspended-agent",
        "name": "Suspended agents cannot execute",
        "rule": {"agent_status": "suspended", "action": "deny"},
        "priority": 200,
    },
]


def init_policy_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runtime_policies (
                policy_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                rule_json TEXT NOT NULL,
                priority INTEGER DEFAULT 50,
                enabled INTEGER DEFAULT 1,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS policy_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_id TEXT,
                tool TEXT,
                decision TEXT,
                context TEXT,
                evaluated_at REAL
            );
            """
        )
        count = conn.execute("SELECT COUNT(*) AS c FROM runtime_policies").fetchone()["c"]
        if count:
            return
        for p in DEFAULT_POLICIES:
            conn.execute(
                "INSERT INTO runtime_policies (policy_id, name, rule_json, priority, created_at) VALUES (?, ?, ?, ?, ?)",
                (p["id"], p["name"], json.dumps(p["rule"]), p["priority"], time.time()),
            )


def list_policies() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM runtime_policies WHERE enabled = 1 ORDER BY priority DESC").fetchall()
    return [
        {"policyId": r["policy_id"], "name": r["name"], "rule": json.loads(r["rule_json"]), "priority": r["priority"]}
        for r in rows
    ]


def evaluate(tool: str, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Returns {allowed, disposition, matchedPolicies, reasons}.

    Evaluates runtime_policies AND enforced document policy cards so uploaded
    PDF/MD/DOCX policies are hard-gates, not advisory text.
    """
    from app.services import policy_hub as policy_hub_svc

    policies = list_policies()
    matched: list[str] = []
    reasons: list[str] = []
    disposition = "allow"

    for pol in policies:
        rule = pol["rule"]
        if not _matches(rule, tool, args, context):
            continue
        matched.append(pol["policyId"])
        action = rule.get("action", "allow")
        if action == "deny":
            disposition = "deny"
            reasons.append(f"Policy '{pol['name']}' denied {tool}")
            break
        if action == "require_approval":
            disposition = "require_approval"
            reasons.append(f"Policy '{pol['name']}' requires approval for {tool}")

    # Document-card hard enforcement (NLP-parsed uploads)
    if disposition != "deny":
        for card in policy_hub_svc.enforced_cards():
            text = f"{card.get('title', '')} {card.get('content', '')}".lower()
            tool_l = tool.lower()
            if tool_l not in text and not any(k in text for k in (tool_l.replace("_", " "),)):
                # Also match common capability synonyms
                synonyms = {
                    "shell_exec": ["shell", "command execution", "bash"],
                    "email_send": ["email", "outbound mail"],
                    "file_delete": ["delete file", "file deletion"],
                    "data_fetch": ["exfiltrat", "personal data", "customer data"],
                }
                if not any(s in text for s in synonyms.get(tool, [])):
                    continue
            if any(w in text for w in ("must not", "shall not", "prohibit", "forbidden", "unauthorized", "blocked")):
                disposition = "deny"
                matched.append(card["cardId"])
                reasons.append(f"Document policy '{card['title']}' forbids {tool}")
                break
            if any(w in text for w in ("require approval", "human oversight", "human-in-the-loop", "must be approved")):
                if disposition == "allow":
                    disposition = "require_approval"
                matched.append(card["cardId"])
                reasons.append(f"Document policy '{card['title']}' requires human oversight for {tool}")

    _log_evaluation(matched, tool, disposition, context)
    return {
        "allowed": disposition == "allow",
        "disposition": disposition,
        "matchedPolicies": matched,
        "reasons": reasons,
    }


def _log_evaluation(matched: list[str], tool: str, disposition: str, context: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO policy_evaluations (policy_id, tool, decision, context, evaluated_at) VALUES (?, ?, ?, ?, ?)",
            (matched[0] if matched else None, tool, disposition, json.dumps(context)[:500], time.time()),
        )


def _matches(rule: dict[str, Any], tool: str, args: dict[str, Any], context: dict[str, Any]) -> bool:
    if "tool" in rule and rule["tool"] != tool:
        return False
    if "agent_status" in rule and context.get("agentStatus") != rule["agent_status"]:
        return False
    if "min_trust_score" in rule and context.get("trustScore", 100) < rule["min_trust_score"]:
        return True
    if "pattern" in rule:
        import re
        text = json.dumps(args)
        if re.search(rule["pattern"], text, re.IGNORECASE):
            return True
        return False
    if "tool" in rule or "agent_status" in rule:
        return True
    return False


def create_policy(name: str, rule: dict[str, Any], priority: int = 50, actor: str = "system") -> dict[str, Any]:
    from app.services import history as history_svc
    pid = f"pol-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO runtime_policies (policy_id, name, rule_json, priority, created_at) VALUES (?, ?, ?, ?, ?)",
            (pid, name, json.dumps(rule), priority, time.time()),
        )
    policy = {"policyId": pid, "name": name, "rule": rule, "priority": priority, "enabled": True}
    history_svc.record("policy", pid, "created", policy, actor)
    return policy


def get_policy(policy_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM runtime_policies WHERE policy_id = ?", (policy_id,)).fetchone()
    if not r:
        return None
    return {
        "policyId": r["policy_id"],
        "name": r["name"],
        "rule": json.loads(r["rule_json"]),
        "priority": r["priority"],
        "enabled": bool(r["enabled"]),
    }


def update_policy(policy_id: str, patch: dict[str, Any], actor: str = "system") -> dict[str, Any] | None:
    from app.services import history as history_svc
    existing = get_policy(policy_id)
    if not existing:
        return None
    name = patch.get("name", existing["name"])
    rule = patch.get("rule", existing["rule"])
    priority = patch.get("priority", existing["priority"])
    with get_conn() as conn:
        conn.execute(
            "UPDATE runtime_policies SET name = ?, rule_json = ?, priority = ? WHERE policy_id = ?",
            (name, json.dumps(rule), priority, policy_id),
        )
    policy = get_policy(policy_id)
    history_svc.record("policy", policy_id, "updated", policy, actor)
    return policy


def delete_policy(policy_id: str, actor: str = "system") -> bool:
    """Soft delete: the policy is disabled, not removed, so its evaluation
    history stays attributable and the delete is reversible via rollback."""
    from app.services import history as history_svc
    existing = get_policy(policy_id)
    if not existing:
        return False
    with get_conn() as conn:
        conn.execute("UPDATE runtime_policies SET enabled = 0 WHERE policy_id = ?", (policy_id,))
    history_svc.record("policy", policy_id, "disabled", {**existing, "enabled": False}, actor)
    return True


def rollback_policy(policy_id: str, version: int, actor: str = "system") -> dict[str, Any] | None:
    from app.services import history as history_svc
    snapshot = history_svc.get_version("policy", policy_id, version)
    if not snapshot or not get_policy(policy_id):
        return None
    with get_conn() as conn:
        conn.execute(
            "UPDATE runtime_policies SET name = ?, rule_json = ?, priority = ?, enabled = ? WHERE policy_id = ?",
            (
                snapshot["name"],
                json.dumps(snapshot["rule"]),
                snapshot["priority"],
                int(snapshot.get("enabled", True)),
                policy_id,
            ),
        )
    policy = get_policy(policy_id)
    history_svc.record("policy", policy_id, f"rollback_to_v{version}", policy, actor)
    return policy

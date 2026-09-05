"""Cedar and OPA/Rego policy import — AgentCore-parity authoring UX bridge.

Imports human-authored Cedar (AWS) or Rego (OPA) snippets into ClearFrame
runtime_policies so enterprises can reuse existing policy assets.
"""
from __future__ import annotations

import re
from typing import Any

from app.services import policy as policy_svc


def import_cedar(cedar_text: str, actor: str = "system") -> dict[str, Any]:
    """Translate common Cedar permit/forbid patterns into runtime policies."""
    created: list[dict[str, Any]] = []
    text = cedar_text or ""
    # forbid(principal, action == Action::"shell_exec", resource) → deny shell
    for m in re.finditer(
        r'(forbid|permit)\s*\([^)]*action\s*==\s*(?:AgentCore::)?Action::"([^"]+)"[^)]*\)(?:\s*when\s*\{([^}]+)\})?',
        text,
        re.I | re.S,
    ):
        kind, action, when = m.group(1).lower(), m.group(2), (m.group(3) or "")
        rule: dict[str, Any] = {"tool": action, "action": "deny" if kind == "forbid" else "require_approval"}
        if "amount" in when and "<" in when:
            rule["action"] = "require_approval"
        pol = policy_svc.create_policy(
            f"cedar-{kind}-{action}",
            rule,
            priority=120 if kind == "forbid" else 80,
            actor=actor,
        )
        created.append(pol)
    if not created:
        # Fallback: any Action::"tool" mentioned with forbid nearby
        tools = re.findall(r'Action::"([^"]+)"', text)
        if "forbid" in text.lower() and tools:
            for t in tools[:5]:
                created.append(policy_svc.create_policy(f"cedar-forbid-{t}", {"tool": t, "action": "deny"}, 120, actor))
    return {"ok": True, "format": "cedar", "imported": len(created), "policies": created}


def import_rego(rego_text: str, actor: str = "system") -> dict[str, Any]:
    """Translate simple OPA Rego deny rules into runtime policies."""
    created: list[dict[str, Any]] = []
    text = rego_text or ""
    # deny if input.tool == "shell_exec"
    for m in re.finditer(r'deny\s*(?:contains\s*)?[^{]*\{[^}]*input\.tool\s*==\s*"([^"]+)"', text, re.I | re.S):
        tool = m.group(1)
        created.append(policy_svc.create_policy(f"opa-deny-{tool}", {"tool": tool, "action": "deny"}, 125, actor))
    for m in re.finditer(r'allow\s*=\s*false[^{]*\{[^}]*tool\s*==\s*"([^"]+)"', text, re.I | re.S):
        tool = m.group(1)
        created.append(policy_svc.create_policy(f"opa-deny-{tool}", {"tool": tool, "action": "deny"}, 125, actor))
    return {"ok": True, "format": "rego", "imported": len(created), "policies": created}


def import_policy(text: str, fmt: str = "auto", actor: str = "system") -> dict[str, Any]:
    fmt = (fmt or "auto").lower()
    if fmt == "auto":
        if "forbid(" in text or "permit(" in text or "Action::" in text:
            fmt = "cedar"
        elif "package " in text or "deny {" in text or "input." in text:
            fmt = "rego"
        else:
            fmt = "cedar"
    if fmt == "cedar":
        return import_cedar(text, actor)
    if fmt in {"rego", "opa"}:
        return import_rego(text, actor)
    raise ValueError(f"Unsupported policy format: {fmt}")

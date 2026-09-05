"""Mandate Studio — ClearFrame policy authoring (open source).

Structured forbid/permit authoring, Mandate DSL, and OPA/Rego import.
Compiles into runtime_policies so agents are hard-gated.
"""
from __future__ import annotations

import re
from typing import Any

from app.services import policy as policy_svc


def author(
    effect: str,
    tool: str,
    *,
    when_min_trust: float | None = None,
    require_approval: bool = False,
    name: str | None = None,
    priority: int | None = None,
    actor: str = "system",
) -> dict[str, Any]:
    """Visual / structured Mandate authoring — no vendor policy language required."""
    effect = (effect or "").lower()
    if effect not in {"forbid", "permit", "deny", "allow", "require_approval"}:
        raise ValueError("effect must be forbid|permit|require_approval")
    tool = (tool or "").strip()
    if not tool:
        raise ValueError("tool is required")

    if effect in {"forbid", "deny"}:
        action = "deny"
        pri = priority if priority is not None else 120
    elif effect == "require_approval" or require_approval:
        action = "require_approval"
        pri = priority if priority is not None else 80
    else:
        action = "allow"
        pri = priority if priority is not None else 40

    rule: dict[str, Any] = {"tool": tool, "action": action}
    if when_min_trust is not None:
        rule["min_trust_score"] = when_min_trust
        if action == "allow":
            # Below threshold → deny via separate companion? Encode as deny when low trust
            rule["action"] = "deny"
            rule["min_trust_score"] = when_min_trust

    pol_name = name or f"mandate-{effect}-{tool}"
    pol = policy_svc.create_policy(pol_name, rule, priority=pri, actor=actor)
    return {"ok": True, "format": "mandate", "policy": pol, "studio": "Mandate Studio"}


def preview(effect: str, tool: str, when_min_trust: float | None = None) -> dict[str, Any]:
    """Dry-run what a Mandate would compile to."""
    action = "deny" if effect in {"forbid", "deny"} else ("require_approval" if effect == "require_approval" else "allow")
    rule: dict[str, Any] = {"tool": tool, "action": action}
    if when_min_trust is not None:
        rule["min_trust_score"] = when_min_trust
    return {
        "studio": "Mandate Studio",
        "dsl": f'{effect}(principal, action == Action::"{tool}", resource);',
        "compiled": rule,
        "enforced": True,
    }


def import_mandate_dsl(text: str, actor: str = "system") -> dict[str, Any]:
    """Import Mandate DSL: forbid/permit(principal, action == Action::\"tool\", resource)."""
    created: list[dict[str, Any]] = []
    for m in re.finditer(
        r'(forbid|permit)\s*\([^)]*action\s*==\s*(?:ClearFrame::|Mandate::)?Action::"([^"]+)"[^)]*\)(?:\s*when\s*\{([^}]+)\})?',
        text or "",
        re.I | re.S,
    ):
        kind, action, when = m.group(1).lower(), m.group(2), (m.group(3) or "")
        require = "amount" in when and "<" in when
        created.append(
            author(
                "require_approval" if (kind == "permit" and require) else kind,
                action,
                actor=actor,
            )["policy"]
        )
    if not created:
        tools = re.findall(r'Action::"([^"]+)"', text or "")
        if "forbid" in (text or "").lower() and tools:
            for t in tools[:8]:
                created.append(author("forbid", t, actor=actor)["policy"])
    return {"ok": True, "format": "mandate", "imported": len(created), "policies": created, "studio": "Mandate Studio"}


def import_rego(rego_text: str, actor: str = "system") -> dict[str, Any]:
    """Import OPA Rego deny rules into runtime policies."""
    created: list[dict[str, Any]] = []
    text = rego_text or ""
    for m in re.finditer(r'deny\s*(?:contains\s*)?[^{]*\{[^}]*input\.tool\s*==\s*"([^"]+)"', text, re.I | re.S):
        created.append(author("forbid", m.group(1), actor=actor)["policy"])
    for m in re.finditer(r'allow\s*=\s*false[^{]*\{[^}]*tool\s*==\s*"([^"]+)"', text, re.I | re.S):
        created.append(author("forbid", m.group(1), actor=actor)["policy"])
    return {"ok": True, "format": "rego", "imported": len(created), "policies": created, "studio": "Mandate Studio"}


def import_policy(text: str, fmt: str = "auto", actor: str = "system") -> dict[str, Any]:
    fmt = (fmt or "auto").lower()
    if fmt in {"cedar"}:  # legacy alias → Mandate DSL (no vendor branding in responses)
        fmt = "mandate"
    if fmt == "auto":
        if "forbid(" in text or "permit(" in text or "Action::" in text:
            fmt = "mandate"
        elif "package " in text or "deny {" in text or "input." in text:
            fmt = "rego"
        else:
            fmt = "mandate"
    if fmt in {"mandate", "dsl"}:
        return import_mandate_dsl(text, actor)
    if fmt in {"rego", "opa"}:
        return import_rego(text, actor)
    raise ValueError(f"Unsupported policy format: {fmt}")


# Backward-compatible aliases used by older imports
def import_cedar(text: str, actor: str = "system") -> dict[str, Any]:
    return import_mandate_dsl(text, actor)

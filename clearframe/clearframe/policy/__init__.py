"""ClearFrame Policy Engine — policy-as-code for AI agents.

Policies are YAML documents evaluated on every tool call, before the Goal
Monitor. Decisions: ALLOW, DENY, REQUIRE_HITL (queue for Aegis).

Rule types:
  tools.deny / tools.allow          — tool name allow/deny lists (glob ok)
  domains.allow                     — outbound URL/domain scoping
  data.deny_patterns                — regex guards (PII, secrets) on args
  actions.require_approval          — tools that always require a human
  limits.max_calls_per_tool         — per-session budget per tool
  trust.min_level                   — minimum TrustRegistry level
"""

from clearframe.policy.engine import (
    Decision,
    PolicyDecision,
    PolicyEngine,
    PolicyError,
    load_pack,
    packaged_packs,
)

__all__ = [
    "Decision",
    "PolicyDecision",
    "PolicyEngine",
    "PolicyError",
    "load_pack",
    "packaged_packs",
]

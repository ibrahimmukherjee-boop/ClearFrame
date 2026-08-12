"""A2A (Agent2Agent) AgentCard export.

A2A v1.0 (Linux Foundation) is the 2026 standard for cross-org agent
discovery and delegation. ClearFrame exports a spec-compliant AgentCard so
other agents (Copilot Studio, Azure AI Foundry, Bedrock AgentCore, Google
ADK) can discover and delegate to a governed ClearFrame agent.
"""

from __future__ import annotations

from typing import Any


def a2a_card(
    *,
    name: str,
    description: str,
    url: str,
    version: str = "1.0.0",
    skills: list[dict[str, Any]] | None = None,
    provider: str = "ClearFrame / Nexus Protocol",
) -> dict[str, Any]:
    """Build an A2A AgentCard (serve at /.well-known/agent-card.json)."""
    return {
        "protocolVersion": "1.0",
        "name": name,
        "description": description,
        "url": url,
        "version": version,
        "provider": {"organization": provider},
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "authentication": {"schemes": ["bearer"]},
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": skills or [],
        "metadata": {
            "governance": {
                "goal_manifest": True,
                "audit_chain": "hmac-sha256",
                "policy_engine": True,
                "human_in_the_loop": "aegis",
                "threat_detection": "sonar",
                "trust_registry": "ed25519",
            }
        },
    }

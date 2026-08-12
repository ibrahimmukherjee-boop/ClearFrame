"""EU AI Act conformity assessment module."""
from __future__ import annotations

from typing import Any

from app.services import agents as agents_svc
from app.services import governance as gov_svc

RISK_CATEGORIES = {
    "unacceptable": ["social_scoring", "subliminal_manipulation", "biometric_categorization"],
    "high_risk": ["hr_screening", "credit_scoring", "law_enforcement", "critical_infrastructure"],
    "limited_risk": ["chatbot", "emotion_recognition", "deepfake"],
    "minimal_risk": ["spam_filter", "recommendation", "general_assistant"],
}

HIGH_RISK_CAPABILITIES = {"shell_exec", "database_read", "api_call", "file_write"}


def assess_agent(agent: dict[str, Any]) -> dict[str, Any]:
    caps = set(agent.get("capabilities") or [])
    high_risk_tools = caps & HIGH_RISK_CAPABILITIES
    allow_exec = agent.get("allowExec", False)

    if allow_exec and "shell_exec" in caps:
        category = "high_risk"
        obligations = [
            "Conformity assessment required (Art. 43)",
            "Risk management system mandatory (Art. 9)",
            "Human oversight required (Art. 14)",
            "Technical documentation (Art. 11)",
            "Logging and traceability (Art. 12)",
        ]
    elif high_risk_tools:
        category = "limited_risk"
        obligations = [
            "Transparency obligations (Art. 50)",
            "Users must be informed they interact with AI",
            "Human oversight recommended",
        ]
    else:
        category = "minimal_risk"
        obligations = ["Voluntary codes of conduct (Art. 95)"]

    score = 100
    gaps: list[str] = []
    if category == "high_risk":
        if agent.get("trustScore", 0) < 80:
            score -= 20
            gaps.append("Trust score below 80 for high-risk system")
        if not agent.get("description"):
            score -= 10
            gaps.append("Missing system description (Art. 11)")
    if agent.get("status") == "suspended":
        score -= 30
        gaps.append("Agent suspended — not deployable")

    return {
        "agentId": agent["agentId"],
        "agentName": agent["name"],
        "riskCategory": category,
        "conformityScore": max(0, score),
        "obligations": obligations,
        "gaps": gaps,
        "compliant": len(gaps) == 0 and score >= 70,
    }


def assess_portfolio() -> dict[str, Any]:
    agents = agents_svc.list_agents()
    assessments = [assess_agent(a) for a in agents]
    high_risk = sum(1 for a in assessments if a["riskCategory"] == "high_risk")
    compliant = sum(1 for a in assessments if a["compliant"])
    gov = gov_svc.get_dashboard()
    return {
        "totalAgents": len(agents),
        "highRiskAgents": high_risk,
        "compliantAgents": compliant,
        "portfolioScore": round(compliant / len(agents) * 100) if agents else 100,
        "assessments": assessments,
        "governanceCompliance": gov["complianceScore"],
        "annexCategories": RISK_CATEGORIES,
    }

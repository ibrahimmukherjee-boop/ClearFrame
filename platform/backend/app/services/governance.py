"""ISO 42001 / ISO 23894 AI Governance engine."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.database import get_conn
from app.services import agents as agents_svc
from app.services import audit as audit_svc
from app.services import aegis as aegis_svc
from app.services import sonar as sonar_svc
from app.services import sessions as sessions_svc
from app.services import trust as trust_svc
from app.services import safepulse as safepulse_svc

ISO_42001_CONTROLS: list[dict[str, Any]] = [
    {"id": "4.1", "clause": "Context of the organization", "title": "AI system scope defined", "category": "context"},
    {"id": "4.2", "clause": "Interested parties", "title": "Stakeholder requirements identified", "category": "context"},
    {"id": "5.1", "clause": "Leadership commitment", "title": "AI governance policy established", "category": "leadership"},
    {"id": "5.2", "clause": "AI policy", "title": "Documented AI management policy", "category": "leadership"},
    {"id": "6.1", "clause": "Risk assessment", "title": "AI risks identified and assessed", "category": "planning"},
    {"id": "6.2", "clause": "AI objectives", "title": "Measurable AI objectives set", "category": "planning"},
    {"id": "7.1", "clause": "Resources", "title": "Adequate resources for AI management", "category": "support"},
    {"id": "7.2", "clause": "Competence", "title": "Personnel competence verified", "category": "support"},
    {"id": "7.5", "clause": "Documented information", "title": "AI documentation maintained", "category": "support"},
    {"id": "8.1", "clause": "Operational planning", "title": "Agent lifecycle controls active", "category": "operation"},
    {"id": "8.2", "clause": "AI risk assessment process", "title": "Continuous risk monitoring", "category": "operation"},
    {"id": "8.3", "clause": "Human oversight", "title": "HITL approval for high-risk actions", "category": "operation"},
    {"id": "8.4", "clause": "AI system lifecycle", "title": "Design → deploy → monitor → retire", "category": "operation"},
    {"id": "9.1", "clause": "Monitoring and measurement", "title": "KPIs tracked and reported", "category": "performance"},
    {"id": "9.2", "clause": "Internal audit", "title": "Tamper-evident audit trail verified", "category": "performance"},
    {"id": "9.3", "clause": "Management review", "title": "Governance dashboard reviewed", "category": "performance"},
    {"id": "10.1", "clause": "Nonconformity", "title": "Incidents logged and remediated", "category": "improvement"},
    {"id": "10.2", "clause": "Continual improvement", "title": "Lessons learned applied", "category": "improvement"},
]

RISK_TIERS = ["minimal", "limited", "high", "unacceptable"]


def init_governance_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS governance_risks (
                risk_id TEXT PRIMARY KEY,
                agent_id TEXT,
                title TEXT NOT NULL,
                description TEXT,
                likelihood INTEGER,
                impact INTEGER,
                tier TEXT,
                treatment TEXT,
                status TEXT DEFAULT 'open',
                owner TEXT,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS governance_policies (
                policy_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT,
                version TEXT,
                status TEXT DEFAULT 'active',
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS control_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                control_id TEXT NOT NULL,
                evidence_type TEXT,
                evidence_data TEXT,
                collected_at REAL
            );
            """
        )
        count = conn.execute("SELECT COUNT(*) AS c FROM governance_policies").fetchone()["c"]
        if not count:
            policies = [
                ("AI Acceptable Use Policy", "All AI agents must operate within declared capability scopes. Unauthorized tool access is prohibited."),
                ("Data Handling Policy", "Agents must not exfiltrate PII. All data access is logged in the HMAC audit chain."),
                ("Human Oversight Policy", "High-risk tool calls require human-in-the-loop approval via Aegis before execution."),
                ("Incident Response Policy", "All security incidents detected by Sonar must be triaged within 4 hours."),
            ]
            for title, content in policies:
                conn.execute(
                    "INSERT INTO governance_policies (policy_id, title, content, version, created_at) VALUES (?, ?, ?, '1.0', ?)",
                    (f"pol-{uuid.uuid4().hex[:8]}", title, content, time.time()),
                )


def collect_evidence() -> list[dict[str, Any]]:
    """Auto-collect evidence for ISO 42001 controls from live system state."""
    evidence: list[dict[str, Any]] = []
    agents = agents_svc.list_agents()
    operator = safepulse_svc.get_operator()
    cert = trust_svc.get_certificate()
    session = sessions_svc.get_session()
    audit = audit_svc.verify_chain()
    threats = sonar_svc.list_threats()
    calls = aegis_svc.list_tool_calls()
    hitl_pending = sum(1 for c in calls if c["status"] == "human_review")

    checks = [
        ("8.1", "agent_lifecycle", {"agents": len(agents), "active": sum(1 for a in agents if a["status"] == "active")}),
        ("8.3", "human_oversight", {"hitl_pending": hitl_pending, "hitl_enabled": True}),
        ("8.4", "session_active", {"session": session is not None, "sessionId": session.get("sessionId") if session else None}),
        ("9.2", "audit_integrity", audit),
        ("6.1", "risk_monitoring", {"threats": len(threats), "threatScore": sonar_svc.threat_score()}),
        ("7.2", "operator_verified", {"verified": bool(operator and operator.get("verified")), "trustScore": operator.get("trustScore") if operator else 0}),
        ("8.2", "trust_certificate", {"certValid": cert is not None and not cert.get("revoked"), "trustLevel": cert.get("trustLevel") if cert else None}),
    ]

    with get_conn() as conn:
        for control_id, ev_type, data in checks:
            conn.execute(
                "INSERT INTO control_evidence (control_id, evidence_type, evidence_data, collected_at) VALUES (?, ?, ?, ?)",
                (control_id, ev_type, json.dumps(data), time.time()),
            )
            evidence.append({"controlId": control_id, "type": ev_type, "data": data})

    return evidence


def get_dashboard() -> dict[str, Any]:
    agents = agents_svc.list_agents()
    threats = sonar_svc.list_threats()
    calls = aegis_svc.list_tool_calls()
    audit = audit_svc.verify_chain()
    operator = safepulse_svc.get_operator()

    controls_status = []
    for ctrl in ISO_42001_CONTROLS:
        status = "compliant"
        if ctrl["id"] == "8.3" and any(c["status"] == "human_review" for c in calls):
            status = "attention"
        if ctrl["id"] == "9.2" and not audit.get("valid"):
            status = "non-compliant"
        if ctrl["id"] == "7.2" and not (operator and operator.get("verified")):
            status = "attention"
        controls_status.append({**ctrl, "status": status})

    with get_conn() as conn:
        risks = [dict(r) for r in conn.execute("SELECT * FROM governance_risks ORDER BY created_at DESC LIMIT 20").fetchall()]
        policies = [dict(r) for r in conn.execute("SELECT * FROM governance_policies WHERE status = 'active'").fetchall()]

    return {
        "controls": controls_status,
        "complianceScore": round(sum(1 for c in controls_status if c["status"] == "compliant") / len(controls_status) * 100),
        "agents": {"total": len(agents), "active": sum(1 for a in agents if a["status"] == "active"), "suspended": sum(1 for a in agents if a["status"] == "suspended")},
        "risks": risks,
        "policies": [{"policyId": p["policy_id"], "title": p["title"], "version": p["version"]} for p in policies],
        "kpis": {
            "auditIntegrity": audit.get("valid", False),
            "auditEntries": audit.get("count", 0),
            "threatScore": sonar_svc.threat_score(),
            "activeThreats": len([t for t in threats if t["severity"] in ("high", "critical")]),
            "hitlPending": sum(1 for c in calls if c["status"] == "human_review"),
            "operatorVerified": bool(operator and operator.get("verified")),
        },
    }


def create_risk(agent_id: str | None, title: str, description: str, likelihood: int, impact: int) -> dict[str, Any]:
    score = likelihood * impact
    tier = "minimal" if score <= 4 else "limited" if score <= 9 else "high" if score <= 16 else "unacceptable"
    risk_id = f"risk-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO governance_risks (risk_id, agent_id, title, description, likelihood, impact, tier, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)",
            (risk_id, agent_id, title, description, likelihood, impact, tier, time.time()),
        )
    return {"riskId": risk_id, "title": title, "tier": tier, "score": score}


def list_policies() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM governance_policies WHERE status = 'active'").fetchall()
    return [{"policyId": r["policy_id"], "title": r["title"], "content": r["content"], "version": r["version"]} for r in rows]

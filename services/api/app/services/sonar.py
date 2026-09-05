"""Sonar — ClearFrame AI Security Operations Center (AI SOC).

Detects prompt injection, policy violations, credential abuse, drift, and
anomalous agent behaviour. Emits playbook-driven responses and optional
containment hooks (suspend agent / revoke cert) for sellable SOC coverage.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Any

from app.database import get_conn
from app.production import is_production
from app.services.agents import _log_pipeline

DEFAULT_THREATS = [
    ("evt-1", "14:32:08", "CodeReviewer-Alpha", "policy_violation", "high", "Attempted file access outside allowed scope"),
    ("evt-2", "14:31:45", "SupportBot-Gamma", "anomaly", "medium", "Unusual query pattern detected"),
    ("evt-3", "14:30:12", "DataAnalyst-Beta", "credential_abuse", "critical", "API key used from unknown IP range"),
    ("evt-4", "14:28:33", "CodeReviewer-Alpha", "insider_threat", "low", "Off-hours activity pattern"),
]

# Detection rules: (regex | substring list, type, severity, playbook_id)
_RULES: list[tuple[Any, str, str, str]] = [
    (re.compile(r"ignore\s+(all\s+)?previous|jailbreak|dan mode|system prompt", re.I),
     "prompt_injection", "critical", "pb-contain-prompt"),
    (re.compile(r"exfiltrat|admin password|dump\s+(secrets|keys)|steal\s+(token|api)", re.I),
     "data_exfiltration", "critical", "pb-block-exfil"),
    (re.compile(r"drop\s+table|rm\s+-rf|;\s*delete\s+from|truncate\s+", re.I),
     "destructive_command", "critical", "pb-block-destructive"),
    (re.compile(r"api[_ ]?key|aws_secret|bearer\s+[a-z0-9._-]{20,}", re.I),
     "credential_exposure", "high", "pb-rotate-creds"),
    (["unusual", "off-hours", "anomaly"], "anomaly", "medium", "pb-investigate"),
]

PLAYBOOKS = [
    {
        "id": "pb-contain-prompt",
        "name": "Contain prompt injection",
        "severity": "critical",
        "steps": ["Block request", "Record threat event", "Queue Aegis review", "Optional: suspend agent"],
        "autoContain": True,
    },
    {
        "id": "pb-block-exfil",
        "name": "Block data exfiltration",
        "severity": "critical",
        "steps": ["Deny tool execution", "Alert SOC", "Flag session for forensics"],
        "autoContain": True,
    },
    {
        "id": "pb-block-destructive",
        "name": "Block destructive command",
        "severity": "critical",
        "steps": ["Deny execution", "Require human override", "Audit chain verify"],
        "autoContain": True,
    },
    {
        "id": "pb-rotate-creds",
        "name": "Credential exposure response",
        "severity": "high",
        "steps": ["Redact from logs", "Recommend vault rotate", "Notify operator"],
        "autoContain": False,
    },
    {
        "id": "pb-investigate",
        "name": "Investigate anomaly",
        "severity": "medium",
        "steps": ["Enrich with session context", "Compare baseline behaviour", "Escalate if repeated"],
        "autoContain": False,
    },
    {
        "id": "pb-policy-breach",
        "name": "Policy breach response",
        "severity": "high",
        "steps": ["Enforce document policy card", "Block tool", "Notify compliance"],
        "autoContain": True,
    },
]


def seed_defaults() -> None:
    """Seed illustrative threats in development only — production uses real session events."""
    if is_production():
        return
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM threat_events").fetchone()["c"]
        if count:
            return
        for eid, ts, agent, typ, sev, desc in DEFAULT_THREATS:
            conn.execute(
                "INSERT INTO threat_events (id, timestamp, agent, type, severity, description) VALUES (?, ?, ?, ?, ?, ?)",
                (eid, ts, agent, typ, sev, desc),
            )


def record_event(
    agent_name: str,
    event_type: str,
    severity: str,
    description: str,
    session_id: str = "",
) -> dict[str, Any]:
    eid = f"evt-{uuid.uuid4().hex[:6]}"
    desc = description if not session_id else f"{description} [session: {session_id}]"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO threat_events (id, timestamp, agent, type, severity, description) VALUES (?, ?, ?, ?, ?, ?)",
            (eid, time.strftime("%H:%M:%S"), agent_name, event_type, severity, desc[:500]),
        )
    _log_pipeline("Sonar: event recorded", f"{event_type} ({severity})")
    try:
        from app.services import otel as otel_svc
        otel_svc.emit_span("sonar.threat", {"eventId": eid, "type": event_type, "severity": severity})
    except Exception:
        pass
    return {"id": eid, "type": event_type, "severity": severity, "description": desc[:500]}


def list_threats(limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM threat_events ORDER BY rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "agent": r["agent"],
            "type": r["type"],
            "severity": r["severity"],
            "description": r["description"],
        }
        for r in rows
    ]


def threat_score() -> float:
    threats = list_threats(100)
    base = 12.0
    for t in threats:
        base += {"low": 2, "medium": 6, "high": 12, "critical": 20}.get(t["severity"], 4)
    return min(99.0, base)


def record_drift(agent_name: str, session_id: str) -> None:
    record_event(agent_name, "drift", "medium", f"ClearFrame: behavioural drift in session {session_id}", session_id)


def scan_prompt(prompt: str, agent_name: str = "operator") -> dict[str, Any]:
    """Full AI SOC prompt / intent scan with playbook recommendation."""
    text = prompt or ""
    lower = text.lower()
    matched_type, severity, playbook_id = "ok", "low", None
    blocked = False

    for rule, typ, sev, pb in _RULES:
        hit = False
        if hasattr(rule, "search"):
            hit = bool(rule.search(text))
        else:
            hit = any(tok in lower for tok in rule)
        if hit:
            matched_type, severity, playbook_id = typ, sev, pb
            blocked = sev in {"high", "critical"}
            break

    event = None
    if matched_type != "ok":
        event = record_event(agent_name, matched_type, severity, text[:240])

    playbook = next((p for p in PLAYBOOKS if p["id"] == playbook_id), None)
    return {
        "type": matched_type,
        "severity": severity,
        "blocked": blocked,
        "message": text[:240],
        "score": threat_score(),
        "playbook": playbook,
        "event": event,
        "soc": True,
    }


def list_playbooks() -> list[dict[str, Any]]:
    return PLAYBOOKS


def contain(
    agent_id: str | None = None,
    action: str = "suspend",
    reason: str = "Sonar AI SOC containment",
    actor: str = "sonar-soc",
) -> dict[str, Any]:
    """Containment hook: suspend agent and/or revoke trust certificate."""
    from app.services import agents as agents_svc
    from app.services import trust as trust_svc

    result: dict[str, Any] = {"ok": True, "action": action, "reason": reason}
    agent = agents_svc.get_agent(agent_id) if agent_id else agents_svc.get_current_agent()
    if not agent:
        return {"ok": False, "error": "No agent to contain"}
    result["agentId"] = agent["agentId"]
    result["agentName"] = agent["name"]

    if action in {"suspend", "full"}:
        agents_svc.suspend_agent(agent["agentId"])
        result["suspended"] = True
    if action in {"revoke_cert", "full"}:
        try:
            trust_svc.revoke_certificate()
            result["certRevoked"] = True
        except Exception as exc:
            result["certRevoked"] = False
            result["certError"] = str(exc)

    record_event(agent["name"], "containment", "critical", f"{action}: {reason}")
    return result


def soc_dashboard() -> dict[str, Any]:
    threats = list_threats(100)
    by_sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    by_type: dict[str, int] = {}
    for t in threats:
        by_sev[t["severity"]] = by_sev.get(t["severity"], 0) + 1
        by_type[t["type"]] = by_type.get(t["type"], 0) + 1
    open_critical = by_sev.get("critical", 0) + by_sev.get("high", 0)
    return {
        "product": "Sonar AI SOC",
        "sellableWith": "ClearFrame (OSS) + Nexus Protocol (commercial SafePulse)",
        "score": threat_score(),
        "openCriticalHigh": open_critical,
        "bySeverity": by_sev,
        "byType": by_type,
        "recent": threats[:15],
        "playbooks": PLAYBOOKS,
        "capabilities": [
            "prompt_injection_detection",
            "exfiltration_blocking",
            "policy_breach_response",
            "credential_exposure",
            "behavioural_drift",
            "containment_hooks",
            "otel_export",
            "playbook_automation",
        ],
    }

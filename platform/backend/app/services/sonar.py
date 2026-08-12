"""Sonar AI SOC threat detection service."""
from __future__ import annotations

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
) -> None:
    eid = f"evt-{uuid.uuid4().hex[:6]}"
    desc = description if not session_id else f"{description} [session: {session_id}]"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO threat_events (id, timestamp, agent, type, severity, description) VALUES (?, ?, ?, ?, ?, ?)",
            (eid, time.strftime("%H:%M:%S"), agent_name, event_type, severity, desc[:500]),
        )
    _log_pipeline("Sonar: event recorded", f"{event_type} ({severity})")


def list_threats() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM threat_events ORDER BY timestamp DESC LIMIT 50").fetchall()
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
    threats = list_threats()
    base = 30.0
    for t in threats:
        base += {"low": 3, "medium": 8, "high": 15, "critical": 25}.get(t["severity"], 5)
    return min(95.0, base)


def record_drift(agent_name: str, session_id: str) -> None:
    eid = f"evt-{uuid.uuid4().hex[:6]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO threat_events (id, timestamp, agent, type, severity, description) VALUES (?, ?, ?, 'drift', 'medium', ?)",
            (eid, time.strftime("%H:%M:%S"), agent_name, f"ClearFrame: behavioural drift in session {session_id}"),
        )
    _log_pipeline("Sonar: threat detected", "drift (MEDIUM)")

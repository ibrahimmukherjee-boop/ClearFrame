"""ClearFrame AI SOC — operating model (AI-only, not a general SIEM).

Wedge: detect and respond to threats *against and by* AI agents, then fan out
to enterprise tools (CrowdStrike, IdP, ticketing) for host/identity response.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.database import get_conn


def init_ai_soc_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ai_soc_bindings (
                binding_id TEXT PRIMARY KEY,
                agent_id TEXT,
                agent_name TEXT,
                actor_user TEXT,
                hostname TEXT,
                device_id TEXT,
                vendor TEXT,
                meta TEXT,
                updated_at REAL
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_soc_bindings_user ON ai_soc_bindings(actor_user)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_soc_bindings_host ON ai_soc_bindings(hostname)"
        )


def operating_model() -> dict[str, Any]:
    """Simple, shareable description of how the AI SOC works."""
    return {
        "product": "ClearFrame AI SOC",
        "positioning": "Best-in-class security operations for AI agents — not a general SIEM/UEBA.",
        "wedge": "Agent response control plane + enterprise fan-out",
        "layers": [
            {
                "id": "1-detect",
                "name": "Detect (Sonar)",
                "does": "Scans prompts, tool calls, sessions for AI-specific threats (jailbreak, exfil, tool poisoning, MCP abuse, drift).",
            },
            {
                "id": "2-bus",
                "name": "Correlate (SOC bus)",
                "does": "Ingests enterprise signals (CrowdStrike, Defender, Okta) and links them to the same user/host/agent.",
            },
            {
                "id": "3-case",
                "name": "Case",
                "does": "Opens a case when AI risk meets enterprise risk (e.g. Falcon alert + agent exfil).",
            },
            {
                "id": "4-respond",
                "name": "Respond",
                "does": "Suspends the agent, revokes trust, isolates the host (CrowdStrike/Defender/S1), suspends IdP user, tickets + pages.",
            },
            {
                "id": "5-export",
                "name": "Export (optional)",
                "does": "Fans out to Slack/Jira/PagerDuty/Splunk so your existing SOC still sees AI incidents.",
            },
        ],
        "not": [
            "Full network SIEM",
            "Generic UEBA for every employee laptop",
            "Replacement for CrowdStrike Falcon console",
        ],
        "integrations": {
            "edr": ["CrowdStrike Falcon", "Microsoft Defender", "SentinelOne"],
            "identity": ["Okta"],
            "notify": ["Slack", "Jira", "PagerDuty", "webhook", "Splunk HEC"],
        },
        "liveVsSimulated": "Each connector is live when secrets are set; otherwise clearly labelled simulated so demos never lie.",
        "oneLiner": "Sonar watches the agent. The bus joins EDR/IdP. A case runs the playbook: kill the agent path, contain the host, alert humans.",
    }


def bind_entity(
    *,
    agent_id: str = "",
    agent_name: str = "",
    actor_user: str = "",
    hostname: str = "",
    device_id: str = "",
    vendor: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Link AI agent ↔ human user ↔ endpoint for cross-domain correlation."""
    init_ai_soc_db()
    bid = f"bind-{uuid.uuid4().hex[:10]}"
    now = time.time()
    with get_conn() as conn:
        # Upsert-like: replace prior row for same agent+user+host
        conn.execute(
            """DELETE FROM ai_soc_bindings
               WHERE COALESCE(agent_id,'')=? AND COALESCE(actor_user,'')=? AND COALESCE(hostname,'')=?""",
            (agent_id or "", actor_user or "", hostname or ""),
        )
        conn.execute(
            """INSERT INTO ai_soc_bindings
               (binding_id, agent_id, agent_name, actor_user, hostname, device_id, vendor, meta, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bid,
                agent_id,
                agent_name,
                actor_user,
                hostname,
                device_id,
                vendor,
                json.dumps(meta or {}),
                now,
            ),
        )
    return get_binding(bid) or {"bindingId": bid}


def get_binding(binding_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM ai_soc_bindings WHERE binding_id=?", (binding_id,)).fetchone()
    return _row_binding(row) if row else None


def resolve_bindings(*, actor_user: str = "", hostname: str = "", agent_name: str = "") -> list[dict[str, Any]]:
    init_ai_soc_db()
    clauses: list[str] = []
    args: list[Any] = []
    if actor_user:
        clauses.append("actor_user=?")
        args.append(actor_user)
    if hostname:
        clauses.append("hostname=?")
        args.append(hostname)
    if agent_name:
        clauses.append("agent_name=?")
        args.append(agent_name)
    if not clauses:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM ai_soc_bindings ORDER BY updated_at DESC LIMIT 50").fetchall()
        return [_row_binding(r) for r in rows]
    where = " OR ".join(clauses)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM ai_soc_bindings WHERE {where} ORDER BY updated_at DESC LIMIT 50",
            tuple(args),
        ).fetchall()
    return [_row_binding(r) for r in rows]


def _row_binding(row: Any) -> dict[str, Any]:
    meta = {}
    try:
        meta = json.loads(row["meta"] or "{}")
    except Exception:
        meta = {}
    return {
        "bindingId": row["binding_id"],
        "agentId": row["agent_id"],
        "agentName": row["agent_name"],
        "actorUser": row["actor_user"],
        "hostname": row["hostname"],
        "deviceId": row["device_id"],
        "vendor": row["vendor"],
        "meta": meta,
        "updatedAt": row["updated_at"],
    }


def posture() -> dict[str, Any]:
    from app.services import connectors as connectors_svc
    from app.services import integrations as integrations_svc
    from app.services import sonar as sonar_svc
    from app.services import soc_bus as soc_bus_svc

    integ = integrations_svc.status()
    dash = soc_bus_svc.dashboard()
    return {
        **operating_model(),
        "threatScore": sonar_svc.threat_score(),
        "openCases": dash.get("openCases"),
        "totalCases": dash.get("totalCases"),
        "connectors": integ.get("connectors"),
        "liveCount": integ.get("liveCount"),
        "edr": connectors_svc.connector_status(),
        "bindings": resolve_bindings()[:10],
        "catalogSize": len(sonar_svc.threat_catalog()),
    }

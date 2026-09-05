"""Data lineage — provenance for every governed action and federated query.

Enterprises need to answer: where did this result come from, which agent
produced it, and under which policy? Lineage records form a directed graph of
inputs → process → outputs that auditors can walk.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.database import get_conn
from app.services import audit as audit_svc


def init_lineage_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS lineage_events (
                lineage_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                inputs_json TEXT NOT NULL,
                outputs_json TEXT NOT NULL,
                actor TEXT,
                agent_id TEXT,
                metadata_json TEXT,
                created_at REAL
            );
            """
        )


def record(
    entity_type: str,
    entity_id: str,
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    actor: str = "system",
    agent_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    lid = entity_id if entity_id.startswith("fq-") else f"lin-{uuid.uuid4().hex[:10]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO lineage_events"
            " (lineage_id, entity_type, entity_id, inputs_json, outputs_json, actor, agent_id, metadata_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                lid,
                entity_type,
                entity_id,
                json.dumps(inputs),
                json.dumps(outputs),
                actor,
                agent_id,
                json.dumps(metadata or {}),
                time.time(),
            ),
        )
    audit_svc.write_event("lineage_recorded", lid, {"entityType": entity_type, "entityId": entity_id})
    return lid


def get(lineage_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM lineage_events WHERE lineage_id = ?", (lineage_id,)).fetchone()
    if not r:
        return None
    return {
        "lineageId": r["lineage_id"],
        "entityType": r["entity_type"],
        "entityId": r["entity_id"],
        "inputs": json.loads(r["inputs_json"]),
        "outputs": json.loads(r["outputs_json"]),
        "actor": r["actor"],
        "agentId": r["agent_id"],
        "metadata": json.loads(r["metadata_json"] or "{}"),
        "createdAt": r["created_at"],
    }


def list_for_entity(entity_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM lineage_events WHERE entity_id = ? ORDER BY created_at DESC",
            (entity_id,),
        ).fetchall()
    return [get(r["lineage_id"]) for r in rows]  # type: ignore[misc]


def recent(limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT lineage_id FROM lineage_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [get(r["lineage_id"]) for r in rows]  # type: ignore[misc]

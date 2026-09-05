"""Versioned change history for governed resources.

Every mutation of a governed resource (agent, policy) stores a full JSON
snapshot after the change, with a monotonically increasing version number,
the action taken, and the actor. Any prior version can be inspected and
rolled back to — rollback itself is recorded as a new version, so history
is append-only and never rewritten.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.database import get_conn
from app.services import audit as audit_svc

_SCHEMA = """
CREATE TABLE IF NOT EXISTS resource_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    action TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    actor TEXT,
    created_at REAL
);
"""


def init_history_db() -> None:
    from app.database import USE_POSTGRES
    schema = (
        _SCHEMA.replace("id INTEGER PRIMARY KEY AUTOINCREMENT", "id SERIAL PRIMARY KEY")
        if USE_POSTGRES
        else _SCHEMA
    )
    with get_conn() as conn:
        conn.executescript(schema)


def record(
    resource_type: str,
    resource_id: str,
    action: str,
    snapshot: dict[str, Any],
    actor: str = "system",
) -> int:
    """Append a new version. Returns the version number assigned."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM resource_history"
            " WHERE resource_type = ? AND resource_id = ?",
            (resource_type, resource_id),
        ).fetchone()
        version = row["v"] + 1
        conn.execute(
            "INSERT INTO resource_history"
            " (resource_type, resource_id, version, action, snapshot, actor, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (resource_type, resource_id, version, action, json.dumps(snapshot), actor, time.time()),
        )
    return version


def list_history(resource_type: str, resource_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT version, action, snapshot, actor, created_at FROM resource_history"
            " WHERE resource_type = ? AND resource_id = ? ORDER BY version DESC",
            (resource_type, resource_id),
        ).fetchall()
    return [
        {
            "version": r["version"],
            "action": r["action"],
            "snapshot": json.loads(r["snapshot"]),
            "actor": r["actor"],
            "createdAt": r["created_at"],
        }
        for r in rows
    ]


def get_version(resource_type: str, resource_id: str, version: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT snapshot FROM resource_history"
            " WHERE resource_type = ? AND resource_id = ? AND version = ?",
            (resource_type, resource_id, version),
        ).fetchone()
    return json.loads(row["snapshot"]) if row else None


def record_and_audit(
    resource_type: str,
    resource_id: str,
    action: str,
    snapshot: dict[str, Any],
    actor: str = "system",
) -> int:
    version = record(resource_type, resource_id, action, snapshot, actor)
    audit_svc.write_event(
        f"{resource_type}_{action}",
        resource_id,
        {"version": version, "actor": actor},
    )
    return version

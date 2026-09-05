"""Multi-tenant isolation for enterprise deployments.

Every governed resource can be scoped to a tenant (organisation). Requests
carry an optional ``X-Tenant-Id`` header; when set, list/mutate operations
are constrained to that tenant's namespace — the database-level analogue of
row-level security.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from app.database import get_conn


DEFAULT_TENANT = "ten-default"


def init_tenancy_db() -> None:
    from app.database import USE_POSTGRES
    schema = """
    CREATE TABLE IF NOT EXISTS tenants (
        tenant_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        quotas TEXT,
        created_at REAL
    );
    CREATE TABLE IF NOT EXISTS tenant_memberships (
        tenant_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        PRIMARY KEY (tenant_id, user_id)
    );
    """
    if USE_POSTGRES:
        # identical for these tables
        pass
    with get_conn() as conn:
        conn.executescript(schema)
        row = conn.execute("SELECT 1 AS x FROM tenants WHERE tenant_id = ?", (DEFAULT_TENANT,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO tenants (tenant_id, name, status, quotas, created_at) VALUES (?, ?, 'active', ?, ?)",
                (DEFAULT_TENANT, "Default Organisation", '{"maxAgents":100,"maxQueriesPerHour":1000}', time.time()),
            )


def list_tenants() -> list[dict[str, Any]]:
    import json
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM tenants ORDER BY created_at").fetchall()
    return [
        {
            "tenantId": r["tenant_id"],
            "name": r["name"],
            "status": r["status"],
            "quotas": json.loads(r["quotas"] or "{}"),
            "createdAt": r["created_at"],
        }
        for r in rows
    ]


def create_tenant(name: str, quotas: dict[str, Any] | None = None) -> dict[str, Any]:
    import json
    tid = f"ten-{uuid.uuid4().hex[:8]}"
    q = quotas or {"maxAgents": 50, "maxQueriesPerHour": 500}
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tenants (tenant_id, name, status, quotas, created_at) VALUES (?, ?, 'active', ?, ?)",
            (tid, name, json.dumps(q), time.time()),
        )
    return {"tenantId": tid, "name": name, "status": "active", "quotas": q}


def get_tenant(tenant_id: str) -> dict[str, Any] | None:
    return next((t for t in list_tenants() if t["tenantId"] == tenant_id), None)


def ensure_tenant_column(conn: Any, table: str, column: str = "tenant_id") -> None:
    """Best-effort schema patch for soft multi-tenancy on existing tables."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT '{DEFAULT_TENANT}'")
    except Exception:
        pass

"""Schema migration registry — versioned, auditable DDL history.

Enterprises need to know which schema version is live and that migrations are
applied exactly once. This is the lightweight analogue of Flyway/Liquibase.
"""
from __future__ import annotations

import time
from typing import Any

from app.database import get_conn

# Ordered list of named migrations. Add new entries at the bottom only.
MIGRATIONS: list[tuple[str, str]] = [
    ("001_tenants", "tenancy"),
    ("002_federation", "federation"),
    ("003_lineage", "lineage"),
    ("004_idempotency", "idempotency"),
]


def init_migrations_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at REAL
            );
            """
        )


def applied() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT version, name, applied_at FROM schema_migrations ORDER BY version").fetchall()
    return [{"version": r["version"], "name": r["name"], "appliedAt": r["applied_at"]} for r in rows]


def mark_applied(version: str, name: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (version, name, time.time()),
        )


def run_pending() -> list[str]:
    """Apply any enterprise module inits that have not yet been recorded."""
    from app.services import federation as federation_svc
    from app.services import idempotency as idem_svc
    from app.services import lineage as lineage_svc
    from app.services import tenancy as tenancy_svc

    handlers = {
        "tenancy": tenancy_svc.init_tenancy_db,
        "federation": federation_svc.init_federation_db,
        "lineage": lineage_svc.init_lineage_db,
        "idempotency": idem_svc.init_idempotency_db,
    }
    done = {m["version"] for m in applied()}
    newly: list[str] = []
    for version, name in MIGRATIONS:
        if version in done:
            continue
        handlers[name]()
        mark_applied(version, name)
        newly.append(version)
    return newly

"""Full-state backup and restore for governance data.

Exports every governance table as JSON so operators can take point-in-time
backups and restore them (system-level rollback). Credential material is
deliberately excluded: users, refresh tokens, login attempts, and vault
secrets never leave the database through this path.
"""
from __future__ import annotations

import time
from typing import Any

from app.database import get_conn
from app.services import audit as audit_svc

BACKUP_TABLES = [
    "agents",
    "operators",
    "certificates",
    "sessions",
    "tool_calls",
    "threat_events",
    "pipeline_log",
    "runtime_policies",
    "resource_history",
    "workflows",
    "workflow_runs",
    "settings",
]

BACKUP_FORMAT_VERSION = 1


def _table_exists(conn: Any, table: str) -> bool:
    try:
        conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        return True
    except Exception:
        return False


def export_all(actor: str = "system") -> dict[str, Any]:
    tables: dict[str, list[dict[str, Any]]] = {}
    with get_conn() as conn:
        for table in BACKUP_TABLES:
            if not _table_exists(conn, table):
                continue
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            tables[table] = [dict(r) for r in rows]
    audit_svc.write_event("backup_exported", "system", {"tables": len(tables), "actor": actor})
    return {
        "formatVersion": BACKUP_FORMAT_VERSION,
        "exportedAt": time.time(),
        "tables": tables,
    }


def restore_all(payload: dict[str, Any], actor: str = "system") -> dict[str, Any]:
    """Atomic restore: all tables replaced in one transaction, or none are.

    Only tables on the BACKUP_TABLES allowlist are touched — a crafted payload
    cannot write to auth or secret tables.
    """
    if payload.get("formatVersion") != BACKUP_FORMAT_VERSION:
        raise ValueError(f"Unsupported backup format (expected {BACKUP_FORMAT_VERSION})")
    tables = payload.get("tables")
    if not isinstance(tables, dict) or not tables:
        raise ValueError("Backup contains no tables")

    restored: dict[str, int] = {}
    with get_conn() as conn:
        for table, rows in tables.items():
            if table not in BACKUP_TABLES or not _table_exists(conn, table):
                continue
            if not isinstance(rows, list):
                raise ValueError(f"Table {table}: expected a list of rows")
            conn.execute(f"DELETE FROM {table}")
            for row in rows:
                if not isinstance(row, dict) or not row:
                    raise ValueError(f"Table {table}: malformed row")
                columns = list(row.keys())
                if any(not c.replace("_", "").isalnum() for c in columns):
                    raise ValueError(f"Table {table}: invalid column name")
                placeholders = ", ".join("?" for _ in columns)
                conn.execute(
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                    tuple(row[c] for c in columns),
                )
            restored[table] = len(rows)
    audit_svc.write_event("backup_restored", "system", {"tables": restored, "actor": actor})
    return {"ok": True, "restored": restored}

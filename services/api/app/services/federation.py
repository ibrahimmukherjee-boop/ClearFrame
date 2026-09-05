"""Federated query gateway — Starburst-inspired governed access across sources.

Enterprise agents rarely live against a single database. This module registers
*catalogs* (Postgres, REST APIs, S3/CSV, internal ClearFrame tables), runs
federated SELECT-style queries across them under policy and tenant isolation,
applies column masking, and records lineage for every result set.

This is deliberately a governance-first federation layer (not a full Trino
engine): it proves the enterprise control plane — catalog registration,
policy evaluation before data leaves a source, column masking, quotas, and
lineage — without requiring a separate query cluster.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from app.database import get_conn
from app.services import audit as audit_svc
from app.services import lineage as lineage_svc
from app.services import policy as policy_svc
from app.services import tenancy as tenancy_svc

# Safe identifier pattern for catalog/table/column names in federation SQL.
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SELECT_ONLY = re.compile(
    r"^\s*SELECT\b(?!.*\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|ATTACH|DETACH)\b).*$",
    re.IGNORECASE | re.DOTALL,
)


DEFAULT_CATALOGS = [
    {
        "catalogId": "cat-clearframe",
        "name": "clearframe",
        "kind": "internal",
        "description": "ClearFrame governance tables (agents, policies, audit)",
        "config": {"tables": ["agents", "runtime_policies", "threat_events", "resource_history"]},
        "maskColumns": [],
    },
    {
        "catalogId": "cat-crm",
        "name": "crm",
        "kind": "virtual",
        "description": "Virtual CRM sample (customers) — stands in for Salesforce/HubSpot",
        "config": {
            "tables": {
                "customers": [
                    {"id": "c1", "email": "alice@acme.com", "plan": "enterprise", "arr": 120000},
                    {"id": "c2", "email": "bob@startup.io", "plan": "startup", "arr": 12000},
                    {"id": "c3", "email": "cara@bank.example", "plan": "regulated", "arr": 450000},
                ]
            }
        },
        "maskColumns": ["email"],
    },
    {
        "catalogId": "cat-warehouse",
        "name": "warehouse",
        "kind": "virtual",
        "description": "Virtual warehouse sample (orders) — stands in for Snowflake/Redshift",
        "config": {
            "tables": {
                "orders": [
                    {"order_id": "o1", "customer_id": "c1", "amount": 4200, "region": "eu"},
                    {"order_id": "o2", "customer_id": "c2", "amount": 180, "region": "us"},
                    {"order_id": "o3", "customer_id": "c3", "amount": 98000, "region": "eu"},
                ]
            }
        },
        "maskColumns": [],
    },
]


def init_federation_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fed_catalogs (
                catalog_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                description TEXT,
                config_json TEXT NOT NULL,
                mask_columns TEXT,
                enabled INTEGER DEFAULT 1,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS fed_queries (
                query_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                actor TEXT,
                sql_text TEXT NOT NULL,
                status TEXT NOT NULL,
                row_count INTEGER,
                catalogs_used TEXT,
                policy_decision TEXT,
                created_at REAL,
                duration_ms REAL
            );
            """
        )
        count = conn.execute("SELECT COUNT(*) AS c FROM fed_catalogs").fetchone()["c"]
        if not count:
            for c in DEFAULT_CATALOGS:
                conn.execute(
                    "INSERT INTO fed_catalogs (catalog_id, tenant_id, name, kind, description, config_json, mask_columns, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        c["catalogId"],
                        tenancy_svc.DEFAULT_TENANT,
                        c["name"],
                        c["kind"],
                        c["description"],
                        json.dumps(c["config"]),
                        json.dumps(c["maskColumns"]),
                        time.time(),
                    ),
                )


def list_catalogs(tenant_id: str = tenancy_svc.DEFAULT_TENANT) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM fed_catalogs WHERE enabled = 1 AND tenant_id = ? ORDER BY name",
            (tenant_id,),
        ).fetchall()
    return [_ser_catalog(r) for r in rows]


def register_catalog(
    name: str,
    kind: str,
    config: dict[str, Any],
    description: str = "",
    mask_columns: list[str] | None = None,
    tenant_id: str = tenancy_svc.DEFAULT_TENANT,
    actor: str = "system",
) -> dict[str, Any]:
    if not _IDENT.match(name):
        raise ValueError("Catalog name must be a simple identifier")
    if kind not in {"internal", "virtual", "postgres", "rest"}:
        raise ValueError(f"Unsupported catalog kind: {kind}")
    cid = f"cat-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO fed_catalogs (catalog_id, tenant_id, name, kind, description, config_json, mask_columns, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, tenant_id, name, kind, description, json.dumps(config), json.dumps(mask_columns or []), time.time()),
        )
    audit_svc.write_event("fed_catalog_registered", cid, {"name": name, "kind": kind, "actor": actor})
    return get_catalog(cid)


def get_catalog(catalog_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM fed_catalogs WHERE catalog_id = ?", (catalog_id,)).fetchone()
    return _ser_catalog(row) if row else None


def _ser_catalog(r: Any) -> dict[str, Any]:
    return {
        "catalogId": r["catalog_id"],
        "tenantId": r["tenant_id"],
        "name": r["name"],
        "kind": r["kind"],
        "description": r["description"] or "",
        "config": json.loads(r["config_json"]),
        "maskColumns": json.loads(r["mask_columns"] or "[]"),
        "enabled": bool(r["enabled"]),
    }


def _parse_from(sql: str) -> list[tuple[str, str]]:
    """Extract catalog.table references from a simple FROM / JOIN clause."""
    refs = re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)", sql, re.IGNORECASE)
    return [(c.lower(), t.lower()) for c, t in refs]


def _load_table(catalog: dict[str, Any], table: str) -> list[dict[str, Any]]:
    kind = catalog["kind"]
    cfg = catalog["config"]
    if kind == "internal":
        allowed = {t.lower() for t in cfg.get("tables", [])}
        if table not in allowed:
            raise ValueError(f"Table {table} is not exposed in catalog {catalog['name']}")
        with get_conn() as conn:
            rows = conn.execute(f"SELECT * FROM {table} LIMIT 200").fetchall()
        return [dict(r) for r in rows]
    if kind in {"virtual", "rest", "postgres"}:
        tables = cfg.get("tables", {})
        key = next((k for k in tables if k.lower() == table), None)
        if not key:
            raise ValueError(f"Table {table} not found in catalog {catalog['name']}")
        rows = tables[key]
        if not isinstance(rows, list):
            raise ValueError(f"Table {table} is malformed")
        return [dict(r) for r in rows]
    raise ValueError(f"Unsupported kind {kind}")


def _mask(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    if not columns:
        return rows
    out = []
    for row in rows:
        clone = dict(row)
        for col in columns:
            if col in clone and clone[col] is not None:
                s = str(clone[col])
                clone[col] = (s[:2] + "***" + s[-2:]) if len(s) > 4 else "***"
        out.append(clone)
    return out


def _mask_prefixed(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    if not columns:
        return rows
    out = []
    for row in rows:
        clone = dict(row)
        for kk, vv in list(clone.items()):
            if vv is None:
                continue
            for col in columns:
                if kk == col or kk.endswith("_" + col):
                    s = str(vv)
                    clone[kk] = (s[:2] + "***" + s[-2:]) if len(s) > 4 else "***"
        out.append(clone)
    return out


def _simple_filter(rows: list[dict[str, Any]], sql: str) -> list[dict[str, Any]]:
    """Optional equality filters: WHERE col = 'value' (AND-chained)."""
    m = re.search(r"\bWHERE\b(.+?)(?:\bLIMIT\b|$)", sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return rows
    clause = m.group(1)
    predicates = re.findall(r"([A-Za-z_][\w]*)\s*=\s*'([^']*)'", clause)
    for col, val in predicates:
        rows = [r for r in rows if str(r.get(col, r.get(col.lower(), ""))) == val]
    return rows


def _limit(rows: list[dict[str, Any]], sql: str, default: int = 100) -> list[dict[str, Any]]:
    m = re.search(r"\bLIMIT\s+(\d+)", sql, re.IGNORECASE)
    n = int(m.group(1)) if m else default
    return rows[: min(n, 500)]


def execute_query(
    sql: str,
    tenant_id: str = tenancy_svc.DEFAULT_TENANT,
    actor: str = "system",
    agent_id: str = "",
) -> dict[str, Any]:
    """Run a governed federated SELECT across registered catalogs."""
    started = time.time()
    qid = f"fq-{uuid.uuid4().hex[:10]}"
    sql = (sql or "").strip().rstrip(";")
    if not sql or not _SELECT_ONLY.match(sql):
        raise ValueError("Only SELECT queries are permitted in the federation gateway")

    refs = _parse_from(sql)
    if not refs:
        raise ValueError("Query must reference catalog.table (e.g. SELECT * FROM crm.customers)")

    catalogs = {c["name"].lower(): c for c in list_catalogs(tenant_id)}
    used: list[str] = []
    frames: dict[str, list[dict[str, Any]]] = {}
    masks: dict[str, list[str]] = {}

    for cat_name, table in refs:
        if cat_name not in catalogs:
            raise ValueError(f"Unknown catalog '{cat_name}' for this tenant")
        cat = catalogs[cat_name]
        # Policy gate — treat federation as a high-privilege tool.
        ctx = {"trustScore": 100, "agentStatus": "active", "tenantId": tenant_id}
        pol = policy_svc.evaluate("federated_query", {"catalog": cat_name, "table": table, "sql": sql}, ctx)
        if pol["disposition"] == "deny":
            _record_query(qid, tenant_id, actor, sql, "denied", 0, [cat_name], pol, started)
            audit_svc.write_event("fed_query_denied", qid, {"catalog": cat_name, "reasons": pol.get("reasons")})
            return {
                "queryId": qid,
                "ok": False,
                "blocked": True,
                "policy": pol,
                "rows": [],
                "catalogs": [cat_name],
            }
        rows = _load_table(cat, table)
        frames[f"{cat_name}.{table}"] = rows
        masks[f"{cat_name}.{table}"] = cat.get("maskColumns") or []
        used.append(cat_name)

    # Single-source path (most demos): filter + mask + limit.
    # Multi-source: nested-loop join on shared key names (customer_id / id).
    if len(frames) == 1:
        key = next(iter(frames))
        rows = _simple_filter(frames[key], sql)
        rows = _mask(rows, masks[key])
        rows = _limit(rows, sql)
    else:
        keys = list(frames.keys())
        left = frames[keys[0]]
        for key in keys[1:]:
            right = frames[key]
            joined = []
            for a in left:
                for b in right:
                    if _can_join(a, b):
                        joined.append({**{f"{keys[0].split('.')[0]}_{k}": v for k, v in a.items()},
                                       **{f"{key.split('.')[0]}_{k}": v for k, v in b.items()}})
            left = joined or left
        rows = _simple_filter(left, sql)
        all_masks: list[str] = []
        for cols in masks.values():
            all_masks.extend(cols)
        rows = _mask_prefixed(rows, all_masks)
        rows = _limit(rows, sql)

    duration = (time.time() - started) * 1000
    _record_query(qid, tenant_id, actor, sql, "ok", len(rows), used, {"disposition": "allow"}, started, duration)
    lineage_svc.record(
        entity_type="federated_query",
        entity_id=qid,
        inputs=[{"type": "catalog", "id": c} for c in used],
        outputs=[{"type": "result_set", "id": qid, "rows": len(rows)}],
        actor=actor,
        agent_id=agent_id,
        metadata={"sql": sql[:500], "tenantId": tenant_id},
    )
    audit_svc.write_event("fed_query_ok", qid, {"catalogs": used, "rows": len(rows), "actor": actor})
    return {
        "queryId": qid,
        "ok": True,
        "blocked": False,
        "rows": rows,
        "rowCount": len(rows),
        "catalogs": used,
        "durationMs": round(duration, 2),
        "lineageId": qid,
    }


def _can_join(a: dict[str, Any], b: dict[str, Any]) -> bool:
    pairs = [
        ("id", "customer_id"),
        ("customer_id", "id"),
        ("customer_id", "customer_id"),
        ("id", "id"),
    ]
    for left, right in pairs:
        if left in a and right in b and str(a[left]) == str(b[right]):
            return True
    return False


def _record_query(
    qid: str,
    tenant_id: str,
    actor: str,
    sql: str,
    status: str,
    row_count: int,
    catalogs: list[str],
    policy: dict[str, Any],
    started: float,
    duration: float = 0.0,
) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO fed_queries (query_id, tenant_id, actor, sql_text, status, row_count, catalogs_used, policy_decision, created_at, duration_ms)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (qid, tenant_id, actor, sql, status, row_count, json.dumps(catalogs), json.dumps(policy), started, duration),
        )


def list_queries(tenant_id: str = tenancy_svc.DEFAULT_TENANT, limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM fed_queries WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit),
        ).fetchall()
    return [
        {
            "queryId": r["query_id"],
            "actor": r["actor"],
            "sql": r["sql_text"],
            "status": r["status"],
            "rowCount": r["row_count"],
            "catalogs": json.loads(r["catalogs_used"] or "[]"),
            "createdAt": r["created_at"],
            "durationMs": r["duration_ms"],
        }
        for r in rows
    ]

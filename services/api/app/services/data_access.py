"""Agent-native governed data access (Trino-style federation under the hood).

Operators do not write SQL. Agents call ``data_fetch`` / ``data_visualize``
with natural-language questions; this module translates intent to governed
catalog reads (Trino-compatible SELECT path), applies column masking, policy,
and lineage — then returns rows or a chart spec for the console.
"""
from __future__ import annotations

import re
from typing import Any

from app.services import federation as federation_svc
from app.services import tenancy as tenancy_svc

# Intent → catalog.table (demo mapping; production plugs Trino catalogs here)
_INTENT_MAP = [
    (re.compile(r"customer|crm|client|account", re.I), "SELECT * FROM crm.customers LIMIT 50"),
    (re.compile(r"order|sales|revenue|warehouse", re.I), "SELECT * FROM warehouse.orders LIMIT 50"),
    (re.compile(r"join|combined|customer.?order|order.?customer", re.I),
     "SELECT * FROM crm.customers JOIN warehouse.orders LIMIT 50"),
    (re.compile(r"agent|policy|threat|governance|audit", re.I),
     "SELECT * FROM clearframe.agents LIMIT 50"),
]


def question_to_sql(question: str) -> str:
    q = (question or "").strip()
    if not q:
        raise ValueError("Ask a question about your data (e.g. 'show customers in EU')")
    for pattern, sql in _INTENT_MAP:
        if pattern.search(q):
            # Optional equality filters from natural language
            m = re.search(r"\b(?:in|region)\s+([A-Za-z]{2,})\b", q, re.I)
            if m and "orders" in sql:
                region = m.group(1).lower()
                if "WHERE" not in sql.upper():
                    sql = sql.replace("LIMIT", f"WHERE region = '{region}' LIMIT")
            return sql
    # Default: CRM browse
    return "SELECT * FROM crm.customers LIMIT 25"


def ask(
    question: str,
    tenant_id: str = tenancy_svc.DEFAULT_TENANT,
    actor: str = "system",
    agent_id: str = "",
    visualize: bool = False,
) -> dict[str, Any]:
    """Natural-language governed data access for agents and the console."""
    sql = question_to_sql(question)
    result = federation_svc.execute_query(sql, tenant_id=tenant_id, actor=actor, agent_id=agent_id)
    out = {
        "ok": result.get("ok", False),
        "blocked": result.get("blocked", False),
        "question": question,
        "interpretedAs": sql,
        "engine": "trino-compatible-gateway",
        "rows": result.get("rows", []),
        "rowCount": result.get("rowCount", 0),
        "catalogs": result.get("catalogs", []),
        "queryId": result.get("queryId"),
        "lineageId": result.get("lineageId"),
        "policy": result.get("policy"),
        "durationMs": result.get("durationMs"),
    }
    if visualize and out["ok"] and out["rows"]:
        out["chart"] = _chart_spec(out["rows"], question)
    return out


def _chart_spec(rows: list[dict[str, Any]], question: str) -> dict[str, Any]:
    """Produce a simple visualization spec the console can render."""
    numeric = None
    label = None
    sample = rows[0]
    for k, v in sample.items():
        if isinstance(v, (int, float)) and "id" not in k.lower():
            numeric = k
        if isinstance(v, str) and label is None and "email" not in k.lower():
            label = k
    if not numeric:
        return {"type": "table", "title": question, "columns": list(sample.keys())}
    points = [{"label": str(r.get(label or "id", i)), "value": float(r.get(numeric) or 0)} for i, r in enumerate(rows[:12])]
    return {"type": "bar", "title": question, "metric": numeric, "points": points}

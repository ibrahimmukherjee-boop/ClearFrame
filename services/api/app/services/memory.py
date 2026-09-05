"""Continuum — ClearFrame managed agent memory.

Open-source, self-hosted memory with working / episodic / semantic layers,
namespaces, keyword recall, and operator-facing browse APIs.
Part of ClearFrame (Apache 2.0). Nexus Protocol may add commercial extensions.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from app.database import get_conn
from app.services import audit as audit_svc

STRATEGIES = ("working", "episodic", "semantic")


def init_memory_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_short (
                memory_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_id TEXT,
                role TEXT,
                content TEXT NOT NULL,
                created_at REAL,
                expires_at REAL
            );
            CREATE TABLE IF NOT EXISTS memory_long (
                memory_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                importance REAL DEFAULT 0.5,
                created_at REAL,
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS continuum_entries (
                entry_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                session_id TEXT,
                namespace TEXT NOT NULL DEFAULT 'default',
                strategy TEXT NOT NULL,
                key TEXT,
                content TEXT NOT NULL,
                importance REAL DEFAULT 0.5,
                tags TEXT,
                created_at REAL,
                updated_at REAL,
                expires_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_continuum_agent ON continuum_entries(tenant_id, agent_id, strategy);
            CREATE INDEX IF NOT EXISTS idx_continuum_ns ON continuum_entries(namespace);
            """
        )


def remember_short(session_id: str, content: str, agent_id: str = "", role: str = "context", ttl_sec: int = 3600) -> str:
    mid = f"mem-{uuid.uuid4().hex[:10]}"
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO memory_short (memory_id, session_id, agent_id, role, content, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mid, session_id, agent_id, role, content[:4000], now, now + ttl_sec),
        )
    # Mirror into Continuum working layer
    if agent_id:
        put(
            tenant_id="default",
            agent_id=agent_id,
            content=content,
            strategy="working",
            session_id=session_id,
            key=role,
            ttl_sec=ttl_sec,
        )
    return mid


def recall_short(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    now = time.time()
    with get_conn() as conn:
        conn.execute("DELETE FROM memory_short WHERE expires_at < ?", (now,))
        rows = conn.execute(
            "SELECT * FROM memory_short WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [
        {"memoryId": r["memory_id"], "role": r["role"], "content": r["content"], "createdAt": r["created_at"]}
        for r in rows
    ]


def remember_long(tenant_id: str, agent_id: str, key: str, value: Any, importance: float = 0.5) -> str:
    mid = f"mlong-{uuid.uuid4().hex[:10]}"
    now = time.time()
    payload = json.dumps(value) if not isinstance(value, str) else value
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT memory_id FROM memory_long WHERE tenant_id = ? AND agent_id = ? AND key = ?",
            (tenant_id, agent_id, key),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE memory_long SET value = ?, importance = ?, updated_at = ? WHERE memory_id = ?",
                (payload, importance, now, existing["memory_id"]),
            )
            mid = existing["memory_id"]
        else:
            conn.execute(
                "INSERT INTO memory_long (memory_id, tenant_id, agent_id, key, value, importance, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (mid, tenant_id, agent_id, key, payload, importance, now, now),
            )
    put(
        tenant_id=tenant_id,
        agent_id=agent_id,
        content=payload,
        strategy="semantic",
        key=key,
        importance=importance,
        namespace="facts",
    )
    audit_svc.write_event("continuum_write", mid, {"agentId": agent_id, "key": key, "strategy": "semantic"})
    return mid


def recall_long(tenant_id: str, agent_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM memory_long WHERE tenant_id = ? AND agent_id = ? ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (tenant_id, agent_id, limit),
        ).fetchall()
    return [
        {
            "memoryId": r["memory_id"],
            "key": r["key"],
            "value": r["value"],
            "importance": r["importance"],
            "updatedAt": r["updated_at"],
        }
        for r in rows
    ]


def put(
    tenant_id: str,
    agent_id: str,
    content: str,
    strategy: str = "episodic",
    namespace: str = "default",
    key: str | None = None,
    session_id: str = "",
    importance: float = 0.5,
    tags: list[str] | None = None,
    ttl_sec: int | None = None,
) -> dict[str, Any]:
    """Write a Continuum entry (working | episodic | semantic)."""
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {STRATEGIES}")
    eid = f"cx-{uuid.uuid4().hex[:10]}"
    now = time.time()
    expires = (now + ttl_sec) if ttl_sec else (now + 3600 if strategy == "working" else None)
    with get_conn() as conn:
        if key and strategy == "semantic":
            existing = conn.execute(
                "SELECT entry_id FROM continuum_entries WHERE tenant_id=? AND agent_id=? AND namespace=? AND key=? AND strategy='semantic'",
                (tenant_id, agent_id, namespace, key),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE continuum_entries SET content=?, importance=?, updated_at=?, tags=? WHERE entry_id=?",
                    (content[:8000], importance, now, json.dumps(tags or []), existing["entry_id"]),
                )
                eid = existing["entry_id"]
                return get_entry(eid)
        conn.execute(
            """INSERT INTO continuum_entries
               (entry_id, tenant_id, agent_id, session_id, namespace, strategy, key, content, importance, tags, created_at, updated_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                eid, tenant_id, agent_id, session_id or None, namespace, strategy, key,
                content[:8000], importance, json.dumps(tags or []), now, now, expires,
            ),
        )
    return get_entry(eid)


def get_entry(entry_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM continuum_entries WHERE entry_id = ?", (entry_id,)).fetchone()
    return _ser(r) if r else {}


def _ser(r: Any) -> dict[str, Any]:
    return {
        "entryId": r["entry_id"],
        "tenantId": r["tenant_id"],
        "agentId": r["agent_id"],
        "sessionId": r["session_id"],
        "namespace": r["namespace"],
        "strategy": r["strategy"],
        "key": r["key"],
        "content": r["content"],
        "importance": r["importance"],
        "tags": json.loads(r["tags"] or "[]"),
        "createdAt": r["created_at"],
        "updatedAt": r["updated_at"],
        "expiresAt": r["expires_at"],
    }


def _purge_expired(conn) -> None:
    conn.execute(
        "DELETE FROM continuum_entries WHERE expires_at IS NOT NULL AND expires_at < ?",
        (time.time(),),
    )


def browse(
    tenant_id: str,
    agent_id: str = "",
    namespace: str | None = None,
    strategy: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    with get_conn() as conn:
        _purge_expired(conn)
        q = "SELECT * FROM continuum_entries WHERE tenant_id = ?"
        args: list[Any] = [tenant_id]
        if agent_id:
            q += " AND agent_id = ?"
            args.append(agent_id)
        if namespace:
            q += " AND namespace = ?"
            args.append(namespace)
        if strategy:
            q += " AND strategy = ?"
            args.append(strategy)
        q += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
        args.append(limit)
        rows = conn.execute(q, args).fetchall()
    return [_ser(r) for r in rows]


def search(tenant_id: str, query: str, agent_id: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """Keyword recall across Continuum layers."""
    tokens = [t for t in re.split(r"\W+", (query or "").lower()) if len(t) > 2][:8]
    if not tokens:
        return browse(tenant_id, agent_id, limit=limit)
    entries = browse(tenant_id, agent_id, limit=200)
    scored: list[tuple[float, dict[str, Any]]] = []
    for e in entries:
        blob = f"{e.get('key') or ''} {e['content']} {' '.join(e.get('tags') or [])}".lower()
        hits = sum(1 for t in tokens if t in blob)
        if hits:
            scored.append((hits + float(e.get("importance") or 0), e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:limit]]


def context_bundle(session_id: str, tenant_id: str, agent_id: str) -> dict[str, Any]:
    working = browse(tenant_id, agent_id, strategy="working", limit=15)
    episodic = [e for e in browse(tenant_id, agent_id, strategy="episodic", limit=20) if e.get("sessionId") == session_id or not session_id]
    semantic = browse(tenant_id, agent_id, strategy="semantic", limit=30)
    return {
        "product": "Continuum",
        "shortTerm": recall_short(session_id),
        "longTerm": recall_long(tenant_id, agent_id),
        "working": working,
        "episodic": episodic[:15],
        "semantic": semantic,
        "namespaces": sorted({e["namespace"] for e in working + episodic + semantic}),
    }


def dashboard(tenant_id: str = "default") -> dict[str, Any]:
    entries = browse(tenant_id, limit=500)
    by_strategy = {s: 0 for s in STRATEGIES}
    by_ns: dict[str, int] = {}
    for e in entries:
        by_strategy[e["strategy"]] = by_strategy.get(e["strategy"], 0) + 1
        by_ns[e["namespace"]] = by_ns.get(e["namespace"], 0) + 1
    return {
        "product": "Continuum",
        "openSource": True,
        "total": len(entries),
        "byStrategy": by_strategy,
        "byNamespace": by_ns,
        "strategies": list(STRATEGIES),
        "recent": entries[:12],
    }

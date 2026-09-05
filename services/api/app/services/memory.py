"""Managed agent memory — short-term session + long-term persistent store.

Closes the AgentCore Memory gap with an open, self-hosted equivalent:
- short-term: per-session working context (TTL)
- long-term: durable facts/preferences keyed by agent + tenant
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.database import get_conn
from app.services import audit as audit_svc


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
    audit_svc.write_event("memory_long_write", mid, {"agentId": agent_id, "key": key})
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


def context_bundle(session_id: str, tenant_id: str, agent_id: str) -> dict[str, Any]:
    return {
        "shortTerm": recall_short(session_id),
        "longTerm": recall_long(tenant_id, agent_id),
    }

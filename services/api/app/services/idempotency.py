"""Idempotency keys for mutating enterprise APIs.

Clients may safely retry POST/PUT by sending ``Idempotency-Key``. The first
successful response is stored and replayed for duplicate keys within the TTL,
preventing double-creates under network retries — a first-class enterprise
database / API concern.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.database import get_conn

DEFAULT_TTL_SEC = 24 * 3600


def init_idempotency_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                key_hash TEXT PRIMARY KEY,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                body_json TEXT NOT NULL,
                created_at REAL,
                expires_at REAL
            );
            """
        )


def lookup(key: str, method: str, path: str) -> dict[str, Any] | None:
    now = time.time()
    with get_conn() as conn:
        conn.execute("DELETE FROM idempotency_keys WHERE expires_at < ?", (now,))
        row = conn.execute(
            "SELECT status_code, body_json FROM idempotency_keys WHERE key_hash = ? AND method = ? AND path = ?",
            (key, method, path),
        ).fetchone()
    if not row:
        return None
    return {"statusCode": row["status_code"], "body": json.loads(row["body_json"])}


def store(key: str, method: str, path: str, status_code: int, body: Any, ttl: int = DEFAULT_TTL_SEC) -> None:
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO idempotency_keys (key_hash, method, path, status_code, body_json, created_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, method, path, status_code, json.dumps(body), now, now + ttl),
        )

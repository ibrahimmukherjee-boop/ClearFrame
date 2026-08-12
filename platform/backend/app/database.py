"""Database persistence — SQLite (dev) or PostgreSQL (production)."""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from app.config import DATABASE_URL, DB_PATH

USE_POSTGRES = DATABASE_URL.startswith("postgresql")

if USE_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row


class CompatRow(dict):
    """Row object supporting dict and index access like sqlite3.Row."""

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _pg_ddl(sql: str) -> str:
    sql = re.sub(r"\bINTEGER PRIMARY KEY AUTOINCREMENT\b", "SERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"\bAUTOINCREMENT\b", "", sql, flags=re.I)
    return sql


def _pg_dml(sql: str) -> str:
    original = sql
    if re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", sql, re.I):
        sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, flags=re.I)
        if "ON CONFLICT" not in sql.upper():
            sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    if re.search(r"INSERT\s+OR\s+REPLACE\s+INTO", sql, re.I):
        table_match = re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)", sql, re.I)
        cols_match = re.search(r"\(([^)]+)\)\s*VALUES", sql, re.I)
        if table_match and cols_match:
            table = table_match.group(1)
            cols = [c.strip() for c in cols_match.group(1).split(",")]
            pk = cols[0]
            updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != pk)
            sql = re.sub(r"INSERT\s+OR\s+REPLACE\s+INTO", "INSERT INTO", sql, flags=re.I)
            sql = sql.rstrip().rstrip(";") + f" ON CONFLICT ({pk}) DO UPDATE SET {updates}"
    sql = sql.replace("?", "%s")
    if sql != original and "ON CONFLICT" not in sql.upper() and "INSERT OR" in original.upper():
        pass
    return sql


class CompatConnection:
    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self._pg = USE_POSTGRES

    def execute(self, sql: str, params: tuple | list = ()) -> "CompatCursor":
        if self._pg:
            sql = _pg_dml(sql)
            cur = self._conn.cursor(row_factory=dict_row)
            cur.execute(sql, params)
            return CompatCursor(cur, True)
        cur = self._conn.execute(sql, params)
        return CompatCursor(cur, False)

    def executescript(self, sql: str) -> None:
        if self._pg:
            sql = _pg_ddl(sql)
            statements = [s.strip() for s in sql.split(";") if s.strip()]
            with self._conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)
            return
        self._conn.executescript(sql)

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class CompatCursor:
    def __init__(self, cursor: Any, pg: bool) -> None:
        self._cursor = cursor
        self._pg = pg

    def fetchone(self) -> CompatRow | sqlite3.Row | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        if self._pg:
            return CompatRow(row)
        return row

    def fetchall(self) -> list[Any]:
        rows = self._cursor.fetchall()
        if self._pg:
            return [CompatRow(r) for r in rows]
        return rows


SQLITE_CORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    capabilities TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    max_steps INTEGER,
    allow_web INTEGER,
    allow_fs INTEGER,
    allow_exec INTEGER,
    trust_score INTEGER,
    status TEXT,
    owner TEXT,
    registered_at TEXT,
    is_current INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS operators (
    operator_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    verified INTEGER,
    trust_score REAL,
    auth_method TEXT,
    profile TEXT,
    timestamp REAL
);
CREATE TABLE IF NOT EXISTS certificates (
    cert_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    trust_level TEXT,
    capabilities TEXT,
    issued_at REAL,
    expires_at REAL,
    revoked INTEGER,
    signature TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    status TEXT,
    started_at REAL,
    ended_at REAL,
    steps TEXT,
    alerts TEXT
);
CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    tool TEXT,
    args TEXT,
    alignment INTEGER,
    status TEXT
);
CREATE TABLE IF NOT EXISTS threat_events (
    id TEXT PRIMARY KEY,
    timestamp TEXT,
    agent TEXT,
    type TEXT,
    severity TEXT,
    description TEXT
);
CREATE TABLE IF NOT EXISTS pipeline_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS vault_secrets (
    key_name TEXT PRIMARY KEY,
    ciphertext TEXT NOT NULL,
    nonce TEXT NOT NULL,
    updated_at REAL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

PG_CORE_SCHEMA = SQLITE_CORE_SCHEMA.replace(
    "id INTEGER PRIMARY KEY AUTOINCREMENT", "id SERIAL PRIMARY KEY"
).replace(
    "CREATE TABLE IF NOT EXISTS sessions (\n    session_id TEXT PRIMARY KEY,\n    agent_id TEXT NOT NULL,\n    status TEXT,\n    started_at REAL,\n    ended_at REAL,\n    steps TEXT,\n    alerts TEXT\n);",
    """CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    status TEXT,
    started_at REAL,
    ended_at REAL,
    steps TEXT,
    alerts TEXT,
    runtime TEXT DEFAULT 'builtin'
);""",
).replace(
    "CREATE TABLE IF NOT EXISTS tool_calls (\n    id TEXT PRIMARY KEY,\n    session_id TEXT,\n    tool TEXT,\n    args TEXT,\n    alignment INTEGER,\n    status TEXT\n);",
    """CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    tool TEXT,
    args TEXT,
    alignment INTEGER,
    status TEXT,
    reasoning TEXT,
    hitl_decision TEXT,
    operator_note TEXT,
    created_at REAL
);""",
)


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(PG_CORE_SCHEMA if USE_POSTGRES else SQLITE_CORE_SCHEMA)
        if not USE_POSTGRES:
            for stmt in [
                "ALTER TABLE sessions ADD COLUMN runtime TEXT DEFAULT 'builtin'",
                "ALTER TABLE tool_calls ADD COLUMN reasoning TEXT",
                "ALTER TABLE tool_calls ADD COLUMN hitl_decision TEXT",
                "ALTER TABLE tool_calls ADD COLUMN operator_note TEXT",
                "ALTER TABLE tool_calls ADD COLUMN created_at REAL",
            ]:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass


@contextmanager
def get_conn() -> Iterator[CompatConnection]:
    if USE_POSTGRES:
        conn = psycopg.connect(DATABASE_URL)
        try:
            yield CompatConnection(conn)
            conn.commit()
        finally:
            conn.close()
    else:
        raw = sqlite3.connect(DB_PATH, timeout=30.0)
        raw.row_factory = sqlite3.Row
        # WAL + busy_timeout: readers never block the writer and a contended
        # writer waits instead of failing fast. Without this, nested
        # open/write/close cycles across services raised "database is locked".
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA busy_timeout=30000")
        raw.execute("PRAGMA synchronous=NORMAL")
        try:
            yield CompatConnection(raw)
            raw.commit()
        finally:
            raw.close()


def row_to_dict(row: CompatRow | sqlite3.Row | dict | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def backend_label() -> str:
    return "postgresql" if USE_POSTGRES else "sqlite"

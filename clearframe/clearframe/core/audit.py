"""
ClearFrame Audit Log
====================
HMAC-SHA256 chained, tamper-evident audit log.
Each entry's HMAC is computed over (prev_hmac || entry_json).
Tampering with any entry breaks every subsequent HMAC in the chain.

Storage backends
----------------
  flat-file (default)  — JSONL file at ~/.clearframe/audit.log
  sqlite               — SQLite DB at ~/.clearframe/audit.db
                         Set AuditConfig(backend="sqlite") to enable.
                         SQLite is recommended for production — supports
                         indexed queries, session filtering, and replay.

Fix 2: Removed hardcoded fallback HMAC secret.
        Secret is now auto-generated (32 random bytes) on first run and
        stored at ~/.clearframe/audit-secret (chmod 600).
        Override at any time via the CLEARFRAME_AUDIT_SECRET env var
        (value must be a 64-character hex string).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from clearframe.core.config import AuditConfig
from clearframe.core.errors import AuditError

__all__ = ["EventType", "AuditLog"]

# ── Event catalogue ───────────────────────────────────────────────────────────

class EventType(str, Enum):
    SESSION_START        = "session_start"
    SESSION_END          = "session_end"
    TOOL_CALL_REQUESTED  = "tool_call_requested"
    TOOL_CALL_APPROVED   = "tool_call_approved"
    TOOL_CALL_BLOCKED    = "tool_call_blocked"
    TOOL_CALL_COMPLETED  = "tool_call_completed"
    GOAL_SCORE           = "goal_score"
    CONTEXT_HASH         = "context_hash"
    VAULT_UNLOCK         = "vault_unlock"
    VAULT_LOCK           = "vault_lock"
    PLUGIN_LOADED        = "plugin_loaded"
    PLUGIN_REJECTED      = "plugin_rejected"
    # TrustRegistry events
    TRUST_CERT_VERIFIED  = "trust_cert_verified"
    TRUST_CERT_REJECTED  = "trust_cert_rejected"


# ── FIX 2: secret resolution ──────────────────────────────────────────────────

def _resolve_audit_secret(config: AuditConfig) -> bytes:
    """
    Resolve the HMAC secret using the following priority:
      1. CLEARFRAME_AUDIT_SECRET env var (64-char hex string).
      2. Persistent secret file at <log_dir>/audit-secret.
         Created on first run with os.urandom(32); chmod 600.
    A hardcoded fallback is intentionally absent — that would make
    the HMAC chain forgeable by anyone with the source code.
    """
    env_val = os.environ.get(config.hmac_secret_env, "").strip()
    if env_val:
        if len(env_val) != 64:
            raise AuditError(
                f"Environment variable {config.hmac_secret_env!r} must be a "
                "64-character hex string (32 bytes). "
                f"Got length {len(env_val)}."
            )
        return bytes.fromhex(env_val)

    config_dir  = Path(config.log_path).expanduser().parent
    secret_path = config_dir / "audit-secret"
    if secret_path.exists():
        return bytes.fromhex(secret_path.read_text().strip())

    new_secret = secrets.token_bytes(32)
    config_dir.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(new_secret.hex())
    secret_path.chmod(0o600)
    return new_secret


# ── SQLite backend ────────────────────────────────────────────────────────────

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL    NOT NULL,
    event      TEXT    NOT NULL,
    session_id TEXT    NOT NULL,
    data       TEXT    NOT NULL,
    entry_json TEXT    NOT NULL,
    hmac       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session ON audit_log(session_id);
CREATE INDEX IF NOT EXISTS idx_event   ON audit_log(event);
CREATE INDEX IF NOT EXISTS idx_ts      ON audit_log(ts);
"""

class _SQLiteBackend:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SQLITE_SCHEMA)
        conn.commit()
        conn.close()

    def append(self, entry: dict, entry_json: str, entry_hmac: str) -> None:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute(
            "INSERT INTO audit_log (ts, event, session_id, data, entry_json, hmac) "
            "VALUES (?,?,?,?,?,?)",
            (
                entry["ts"], entry["event"], entry["session_id"],
                json.dumps(entry["data"]), entry_json, entry_hmac,
            ),
        )
        conn.commit()
        conn.close()

    def iter_rows(self):
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT entry_json, hmac FROM audit_log ORDER BY id"
        ).fetchall()
        conn.close()
        return rows

    def query(self, session_id: str | None = None, event: str | None = None) -> list[dict]:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        q, params = "SELECT * FROM audit_log WHERE 1=1", []
        if session_id: q += " AND session_id=?"; params.append(session_id)
        if event:      q += " AND event=?";      params.append(event)
        rows = conn.execute(q + " ORDER BY id", params).fetchall()
        conn.close()
        return [dict(r) for r in rows]


# ── AuditLog ──────────────────────────────────────────────────────────────────

class AuditLog:
    """
    HMAC-SHA256 chained audit log.
    Supports flat-file (default) and SQLite backends.

    Usage
    -----
        # Flat-file (default):
        audit = AuditLog(AuditConfig())

        # SQLite (recommended for production):
        audit = AuditLog(AuditConfig(backend="sqlite"))

        audit.write(EventType.SESSION_START, session_id, {"goal": "..."})
        ok, errors = audit.verify_chain()

        # SQLite only — query by session:
        rows = audit.query(session_id="abc-123")
    """

    def __init__(self, config: AuditConfig) -> None:
        self._config     = config
        self._prev_hmac  = "0" * 64
        self._secret: bytes = _resolve_audit_secret(config)
        self._backend: Literal["file", "sqlite"] = getattr(config, "backend", "file")

        if config.enabled:
            if self._backend == "sqlite":
                db_path = Path(config.log_path).expanduser().with_suffix(".db")
                self._sqlite = _SQLiteBackend(db_path)
            else:
                Path(config.log_path).expanduser().parent.mkdir(
                    parents=True, exist_ok=True
                )

    # ── Write ─────────────────────────────────────────────────────────────

    def write(
        self,
        event_type: EventType,
        session_id: str,
        data: dict[str, Any],
    ) -> None:
        """Append a signed entry to the audit log."""
        if not self._config.enabled:
            return
        entry = {
            "ts":         time.time(),
            "event":      event_type.value,
            "session_id": session_id,
            "data":       data,
        }
        entry_json  = json.dumps(entry, separators=(",", ":"), sort_keys=True)
        chain_input = (self._prev_hmac + entry_json).encode()
        entry_hmac  = hmac.new(self._secret, chain_input, hashlib.sha256).hexdigest()

        if self._backend == "sqlite":
            self._sqlite.append(entry, entry_json, entry_hmac)
        else:
            line = json.dumps({"entry": entry, "hmac": entry_hmac}) + "\n"
            with open(Path(self._config.log_path).expanduser(), "a", encoding="utf-8") as f:
                f.write(line)

        self._prev_hmac = entry_hmac

    # ── Verify ────────────────────────────────────────────────────────────

    def verify_chain(self) -> tuple[bool, list[str]]:
        """
        Replay the audit log and verify every HMAC in the chain.

        Returns
        -------
        (is_intact, errors)
            is_intact — True if no errors found.
            errors    — Human-readable description of each violation.
        """
        errors: list[str] = []
        prev = "0" * 64

        if self._backend == "sqlite":
            rows = self._sqlite.iter_rows()
            for i, row in enumerate(rows, 1):
                chain_input = (prev + row["entry_json"]).encode()
                expected    = hmac.new(self._secret, chain_input, hashlib.sha256).hexdigest()
                if not hmac.compare_digest(expected, row["hmac"]):
                    errors.append(f"Row {i}: HMAC mismatch — possible tampering.")
                prev = row["hmac"]
        else:
            log_path = Path(self._config.log_path).expanduser()
            if not log_path.exists():
                return True, []
            with open(log_path, encoding="utf-8") as f:
                for lineno, raw in enumerate(f, 1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        record     = json.loads(raw)
                        entry_json = json.dumps(
                            record["entry"], separators=(",", ":"), sort_keys=True
                        )
                        chain_input = (prev + entry_json).encode()
                        expected    = hmac.new(
                            self._secret, chain_input, hashlib.sha256
                        ).hexdigest()
                        stored = record["hmac"]
                        if not hmac.compare_digest(expected, stored):
                            errors.append(
                                f"Line {lineno}: HMAC mismatch — "
                                "entry may have been tampered with."
                            )
                        prev = stored
                    except (KeyError, json.JSONDecodeError) as exc:
                        errors.append(f"Line {lineno}: parse error — {exc}")

        return len(errors) == 0, errors

    # ── Query (SQLite only) ───────────────────────────────────────────────

    def query(
        self,
        session_id: str | None = None,
        event: str | None = None,
    ) -> list[dict]:
        """
        Query audit entries by session or event type.
        Only available when backend="sqlite".
        """
        if self._backend != "sqlite":
            raise AuditError(
                "query() requires backend=\"sqlite\". "
                "Set AuditConfig(backend=\"sqlite\") to enable indexed queries."
            )
        return self._sqlite.query(session_id, event)

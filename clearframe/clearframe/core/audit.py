"""
ClearFrame HMAC-Chained Audit Log

Every event is linked to the previous via HMAC-SHA256.
Deleting or editing any entry breaks the chain — detectable immediately.

Contrast with OpenClaw/MCP: no audit trail exists. Post-incident
forensics is impossible.

Format: newline-delimited JSON (.jsonl)
Each line:
  {
    "seq": 1,
    "timestamp": "2026-04-12T03:00:00Z",
    "event_type": "SESSION_START",
    "session_id": "abc-123",
    "data": {...},
    "prev_hmac": "0000...0000",   // "0" * 64 for seq=1
    "hmac": "sha256-hex"
  }
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from enum import Enum
from pathlib import Path
from typing import Any

from clearframe.core.config import AuditConfig


class EventType(str, Enum):
    SESSION_START         = "SESSION_START"
    SESSION_END           = "SESSION_END"
    TOOL_CALL_REQUESTED   = "TOOL_CALL_REQUESTED"
    TOOL_CALL_APPROVED    = "TOOL_CALL_APPROVED"
    TOOL_CALL_BLOCKED     = "TOOL_CALL_BLOCKED"
    TOOL_CALL_COMPLETED   = "TOOL_CALL_COMPLETED"
    GOAL_SCORE            = "GOAL_SCORE"
    CONTEXT_HASH          = "CONTEXT_HASH"
    VAULT_ACCESS          = "VAULT_ACCESS"
    PLUGIN_LOADED         = "PLUGIN_LOADED"
    SECURITY_ALERT        = "SECURITY_ALERT"
    OPERATOR_DECISION     = "OPERATOR_DECISION"


_DEFAULT_SECRET = b"clearframe-default-audit-secret-change-in-production"


class AuditLog:
    """
    HMAC-SHA256 chained append-only audit log.

    Each entry's HMAC covers: seq + timestamp + event_type + session_id + data + prev_hmac.
    Verifying the chain detects any insertion, deletion, or modification.
    """

    def __init__(self, config: AuditConfig) -> None:
        self._config = config
        self._secret = os.environb.get(
            config.hmac_secret_env.encode(), _DEFAULT_SECRET
        )
        self._seq = 0
        self._prev_hmac = "0" * 64
        if config.enabled and config.log_path.exists():
            entries = self._read_all()
            if entries:
                last = entries[-1]
                self._seq = last.get("seq", 0)
                self._prev_hmac = last.get("hmac", "0" * 64)

    def write(
        self,
        event_type: EventType,
        session_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        self._seq += 1
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        entry: dict[str, Any] = {
            "seq": self._seq,
            "timestamp": timestamp,
            "event_type": event_type.value,
            "session_id": session_id,
            "data": data,
            "prev_hmac": self._prev_hmac,
        }
        entry["hmac"] = self._compute_hmac(entry)
        self._prev_hmac = entry["hmac"]
        if self._config.enabled:
            self._config.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        return entry

    def verify(self) -> tuple[bool, list[str]]:
        """Verify the full HMAC chain. Returns (ok, list_of_errors)."""
        errors: list[str] = []
        entries = self._read_all()
        prev = "0" * 64
        for entry in entries:
            stored_hmac = entry.get("hmac", "")
            check = {k: v for k, v in entry.items() if k != "hmac"}
            check["prev_hmac"] = prev
            expected = self._compute_hmac(check)
            if not hmac.compare_digest(stored_hmac, expected):
                errors.append(
                    f"Chain broken at seq={entry.get('seq')} "
                    f"event={entry.get('event_type')} — HMAC mismatch"
                )
            prev = stored_hmac
        return len(errors) == 0, errors

    def query(
        self,
        session_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        entries = self._read_all()
        if session_id:
            entries = [e for e in entries if e.get("session_id") == session_id]
        if event_type:
            entries = [e for e in entries if e.get("event_type") == event_type]
        return entries[-limit:]

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        return self._read_all()[-n:]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _compute_hmac(self, entry: dict[str, Any]) -> str:
        canonical = json.dumps(
            {k: entry[k] for k in sorted(entry.keys()) if k != "hmac"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hmac.new(self._secret, canonical, hashlib.sha256).hexdigest()

    def _read_all(self) -> list[dict[str, Any]]:
        if not self._config.log_path.exists():
            return []
        entries = []
        with open(self._config.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

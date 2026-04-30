"""
ClearFrame Audit Log
====================
HMAC-SHA256 chained, tamper-evident audit log.

Each entry's HMAC is computed over (prev_hmac || entry_json).
Tampering with any entry breaks every subsequent HMAC in the chain.

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
import time
from enum import Enum
from pathlib import Path
from typing import Any

from clearframe.core.config import AuditConfig
from clearframe.core.errors import AuditError


# ── Event catalogue ───────────────────────────────────────────────────────────

class EventType(str, Enum):
    SESSION_START         = "session_start"
    SESSION_END           = "session_end"
    TOOL_CALL_REQUESTED   = "tool_call_requested"
    TOOL_CALL_APPROVED    = "tool_call_approved"
    TOOL_CALL_BLOCKED     = "tool_call_blocked"
    TOOL_CALL_COMPLETED   = "tool_call_completed"
    GOAL_SCORE            = "goal_score"
    CONTEXT_HASH          = "context_hash"
    VAULT_UNLOCK          = "vault_unlock"
    VAULT_LOCK            = "vault_lock"
    PLUGIN_LOADED         = "plugin_loaded"
    PLUGIN_REJECTED       = "plugin_rejected"


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

    # ── Disk secret ───────────────────────────────────────────────────────
    config_dir  = Path(config.log_path).expanduser().parent
    secret_path = config_dir / "audit-secret"

    if secret_path.exists():
        raw = secret_path.read_text().strip()
        return bytes.fromhex(raw)

    # First run — generate and persist
    new_secret = secrets.token_bytes(32)
    config_dir.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(new_secret.hex())
    secret_path.chmod(0o600)
    return new_secret


# ── AuditLog ──────────────────────────────────────────────────────────────────

class AuditLog:
    """
    HMAC-SHA256 chained audit log.

    Usage
    -----
        config = AuditConfig()
        audit  = AuditLog(config)
        audit.write(EventType.SESSION_START, session_id, {"goal": "..."})
        ok, errors = audit.verify_chain()
    """

    def __init__(self, config: AuditConfig) -> None:
        self._config    = config
        self._prev_hmac = "0" * 64

        # FIX 2: resolve secret — no hardcoded fallback
        self._secret: bytes = _resolve_audit_secret(config)

        if config.enabled:
            Path(config.log_path).expanduser().parent.mkdir(
                parents=True, exist_ok=True
            )

    # ── Write ─────────────────────────────────────────────────────────────

    def write(
        self,
        event_type: EventType,
        session_id: str,
        data:       dict[str, Any],
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
        prev   = "0" * 64
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

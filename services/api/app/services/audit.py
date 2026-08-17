"""HMAC-chained tamper-evident audit log."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import AUDIT_PATH, AUDIT_SECRET_PATH


def _get_secret() -> bytes:
    if AUDIT_SECRET_PATH.exists():
        return AUDIT_SECRET_PATH.read_bytes()
    secret = hashlib.sha256(uuid.uuid4().bytes).digest()
    AUDIT_SECRET_PATH.write_bytes(secret)
    return secret


def _last_hash() -> str:
    if not AUDIT_PATH.exists():
        return "0" * 64
    last_line = ""
    with AUDIT_PATH.open() as f:
        for line in f:
            if line.strip():
                last_line = line
    if not last_line:
        return "0" * 64
    return json.loads(last_line)["hash"]


def write_event(event_type: str, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    secret = _get_secret()
    prev_hash = _last_hash()
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "event_type": event_type,
        "session_id": session_id,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    body = json.dumps({k: v for k, v in entry.items() if k != "hash"}, sort_keys=True)
    entry["hash"] = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_events(limit: int = 100) -> list[dict[str, Any]]:
    if not AUDIT_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    with AUDIT_PATH.open() as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events[-limit:]


def verify_chain() -> dict[str, Any]:
    secret = _get_secret()
    events = read_events(10_000)
    if not events:
        return {"valid": True, "count": 0, "message": "Empty audit log"}
    prev = "0" * 64
    for i, entry in enumerate(events):
        if entry.get("prev_hash") != prev:
            return {"valid": False, "count": i, "message": f"Chain break at entry {i}"}
        body = json.dumps({k: v for k, v in entry.items() if k != "hash"}, sort_keys=True)
        expected = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        if entry.get("hash") != expected:
            return {"valid": False, "count": i, "message": f"HMAC mismatch at entry {i}"}
        prev = entry["hash"]
    return {"valid": True, "count": len(events), "message": "HMAC chain verified"}

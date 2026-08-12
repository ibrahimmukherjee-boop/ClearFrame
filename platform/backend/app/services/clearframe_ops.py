"""ClearFrame AgentOps server lifecycle + HTTP proxy."""
from __future__ import annotations

import os
import threading
import time
from typing import Any

import httpx
import uvicorn

from app.config import CF_OPS_HOST, CF_OPS_PORT, CF_OPS_TOKEN_PATH, USE_CLEARFRAME_OPS

_ops_thread: threading.Thread | None = None
_ops_started = False


def start_ops_server() -> None:
    global _ops_thread, _ops_started
    if not USE_CLEARFRAME_OPS or _ops_started:
        return
    try:
        from clearframe.core.config import ClearFrameConfig, OpsConfig
        from clearframe.ops.server import create_ops_app
    except ImportError:
        return

    def _run() -> None:
        config = ClearFrameConfig(ops=OpsConfig(host=CF_OPS_HOST, port=CF_OPS_PORT))
        app, token = create_ops_app(config.ops)
        CF_OPS_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        CF_OPS_TOKEN_PATH.write_text(token)
        CF_OPS_TOKEN_PATH.chmod(0o600)
        uvicorn.run(app, host=CF_OPS_HOST, port=CF_OPS_PORT, log_level="warning")

    _ops_thread = threading.Thread(target=_run, daemon=True, name="clearframe-ops")
    _ops_thread.start()
    _ops_started = True
    for _ in range(30):
        if ops_health():
            return
        time.sleep(0.2)


def stop_ops_server() -> None:
    # Daemon thread stops with process
    pass


def _read_token() -> str | None:
    if CF_OPS_TOKEN_PATH.exists():
        return CF_OPS_TOKEN_PATH.read_text().strip()
    return os.environ.get("CF_OPS_TOKEN")


def ops_health() -> bool:
    try:
        r = httpx.get(f"http://{CF_OPS_HOST}:{CF_OPS_PORT}/health", timeout=1.0)
        return r.status_code == 200
    except Exception:
        return False


def ops_status() -> dict[str, Any]:
    return {
        "enabled": USE_CLEARFRAME_OPS,
        "running": ops_health(),
        "host": CF_OPS_HOST,
        "port": CF_OPS_PORT,
        "hasToken": bool(_read_token()),
    }


def register_session(session_id: str, manifest_goal: str, permitted_tools: list[str]) -> dict[str, Any]:
    if not ops_health():
        return {"ok": False, "message": "AgentOps not running"}
    token = _read_token()
    if not token:
        return {"ok": False, "message": "AgentOps token not found"}
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"session_id": session_id, "manifest_goal": manifest_goal, "permitted_tools": permitted_tools}
    try:
        r = httpx.post(
            f"http://{CF_OPS_HOST}:{CF_OPS_PORT}/sessions",
            json=payload,
            headers=headers,
            timeout=5.0,
        )
        if r.status_code >= 400:
            return {"ok": False, "message": r.text}
        return {"ok": True, "data": r.json()}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def list_queue(session_id: str | None = None) -> list[dict[str, Any]]:
    token = _read_token()
    if not token or not ops_health():
        return []
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/queue/{session_id}" if session_id else "/queue"
    try:
        r = httpx.get(f"http://{CF_OPS_HOST}:{CF_OPS_PORT}{path}", headers=headers, timeout=5.0)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else data.get("items", [])
    except Exception:
        pass
    return []


def approve_queue_item(session_id: str, queue_id: str, approved: bool) -> dict[str, Any]:
    token = _read_token()
    if not token or not ops_health():
        return {"ok": False, "message": "AgentOps not running"}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = httpx.post(
            f"http://{CF_OPS_HOST}:{CF_OPS_PORT}/approve",
            json={"session_id": session_id, "queue_id": queue_id, "approved": approved},
            headers=headers,
            timeout=5.0,
        )
        return {"ok": r.status_code < 400, "status": r.status_code}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}

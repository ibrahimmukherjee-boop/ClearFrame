"""
ClearFrame AgentOps Control Plane
REST + WebSocket server. Default: localhost:7477. Auth required.

Endpoints:
  GET  /sessions                    - list active sessions
  GET  /sessions/{id}/audit         - audit log tail
  GET  /sessions/{id}/rtl           - reasoning trace
  GET  /sessions/{id}/monitor       - goal monitor stats
  POST /sessions/{id}/approve/{seq} - approve queued tool call
  POST /sessions/{id}/block/{seq}   - block queued tool call
  POST /audit/verify                - verify audit log integrity
  WS   /ws/sessions/{id}            - live event stream
"""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from clearframe.core.config import OpsConfig

bearer_scheme = HTTPBearer()

_sessions: dict[str, Any] = {}
_approval_queue: dict[str, list[dict]] = {}
_ops_token: str = secrets.token_urlsafe(32)


def create_ops_app(config: OpsConfig) -> FastAPI:
    app = FastAPI(
        title="ClearFrame AgentOps",
        description="Live monitoring and control plane for ClearFrame agent sessions.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def verify_token(
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    ) -> str:
        if config.require_auth and credentials.credentials != _ops_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
        return credentials.credentials

    @app.get("/")
    async def root() -> dict:
        return {"service": "ClearFrame AgentOps", "version": "0.1.0"}

    @app.get("/sessions", dependencies=[Depends(verify_token)])
    async def list_sessions() -> dict:
        return {
            "sessions": [
                {"session_id": sid, "status": info.get("status", "unknown")}
                for sid, info in _sessions.items()
            ]
        }

    @app.get("/sessions/{session_id}/monitor", dependencies=[Depends(verify_token)])
    async def get_monitor_stats(session_id: str) -> dict:
        session = _sessions.get(session_id)
        if not session:
            raise HTTPException(404, f"Session {session_id} not found.")
        return session.get("monitor_stats", {})

    @app.get("/sessions/{session_id}/audit", dependencies=[Depends(verify_token)])
    async def get_audit_tail(session_id: str, n: int = 100) -> dict:
        session = _sessions.get(session_id)
        if not session:
            raise HTTPException(404, f"Session {session_id} not found.")
        audit_log = session.get("audit_log")
        if not audit_log:
            return {"entries": []}
        return {"entries": audit_log.query(session_id=session_id)}

    @app.get("/sessions/{session_id}/rtl", dependencies=[Depends(verify_token)])
    async def get_rtl(session_id: str) -> dict:
        session = _sessions.get(session_id)
        if not session:
            raise HTTPException(404, f"Session {session_id} not found.")
        rtl = session.get("rtl")
        if not rtl:
            return {"steps": []}
        steps = rtl.replay()
        return {"steps": [s.model_dump() for s in steps]}

    @app.post("/sessions/{session_id}/approve/{seq}", dependencies=[Depends(verify_token)])
    async def approve_queued_call(session_id: str, seq: int) -> dict:
        queue = _approval_queue.get(session_id, [])
        item = next((i for i in queue if i["seq"] == seq), None)
        if not item:
            raise HTTPException(404, f"No queued call with seq={seq}.")
        item["decision"] = "approved"
        return {"status": "approved", "seq": seq}

    @app.post("/sessions/{session_id}/block/{seq}", dependencies=[Depends(verify_token)])
    async def block_queued_call(session_id: str, seq: int) -> dict:
        queue = _approval_queue.get(session_id, [])
        item = next((i for i in queue if i["seq"] == seq), None)
        if not item:
            raise HTTPException(404, f"No queued call with seq={seq}.")
        item["decision"] = "blocked"
        return {"status": "blocked", "seq": seq}

    @app.post("/audit/verify", dependencies=[Depends(verify_token)])
    async def verify_audit(session_id: str | None = None) -> dict:
        session = _sessions.get(session_id or "")
        if not session:
            return {"ok": False, "error": "Session not found"}
        audit_log = session.get("audit_log")
        if not audit_log:
            return {"ok": True, "message": "No audit log for this session"}
        ok, errors = audit_log.verify()
        return {"ok": ok, "errors": errors}

    @app.websocket("/ws/sessions/{session_id}")
    async def session_ws(websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        try:
            while True:
                session = _sessions.get(session_id)
                if session:
                    await websocket.send_json({
                        "session_id": session_id,
                        "monitor": session.get("monitor_stats", {}),
                        "status": session.get("status", "unknown"),
                    })
                await asyncio.sleep(1.0)
        except Exception:
            await websocket.close()

    return app

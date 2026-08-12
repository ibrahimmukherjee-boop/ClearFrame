"""
ClearFrame AgentOps Server
===========================
REST + WebSocket API for real-time session inspection and tool-call approval.

Fix 3: WebSocket endpoint /ws/sessions/{session_id} now requires a valid
       ?token= query parameter. Unauthenticated connections are closed with
       code 4401 before the handshake completes.

Fix 6: _sessions, _approval_queue, and _ops_token were module-level globals,
       which broke multi-instance setups and made unit-testing impossible.
       All three are now stored on app.state inside create_ops_app() so each
       app instance has isolated state.
"""
from __future__ import annotations

import secrets
from typing import Any

import fastapi
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from clearframe.core.config import OpsConfig


# ── Request / response models ─────────────────────────────────────────────────

class ApprovalDecision(BaseModel):
    session_id: str
    tool_name:  str
    approved:   bool
    reason:     str = ""


class SessionRegistration(BaseModel):
    session_id:    str
    manifest_goal: str
    permitted_tools: list[str] = []


# ── Factory ───────────────────────────────────────────────────────────────────

def create_ops_app(config: OpsConfig) -> tuple[FastAPI, str]:
    """
    Create and configure the AgentOps FastAPI application.

    Returns
    -------
    (app, ops_token)
        app       — The FastAPI application instance.
        ops_token — The Bearer token required by all authenticated endpoints.
                    Write this to disk (chmod 600) — never log or print it.

    Fix 6
    -----
    All mutable runtime state lives on app.state, not in module globals:
      app.state.sessions        — dict[session_id, session_info]
      app.state.approval_queue  — dict[session_id, list[pending_items]]
      app.state.ops_token       — the secret bearer token for this instance
    """
    app = FastAPI(
        title    = "ClearFrame AgentOps",
        version  = "0.2.0",
        docs_url = None,   # Disable Swagger UI in production
        redoc_url= None,
    )

    # ── FIX 6: state scoped to this app instance ──────────────────────────
    app.state.sessions:       dict[str, Any]        = {}
    app.state.approval_queue: dict[str, list[dict]] = {}
    app.state.ops_token:      str = secrets.token_urlsafe(32)
    # ─────────────────────────────────────────────────────────────────────

    app.add_middleware(
        CORSMiddleware,
        allow_origins  = config.cors_origins,
        allow_methods  = ["GET", "POST"],
        allow_headers  = ["Authorization", "Content-Type"],
        allow_credentials = False,
    )

    # ── Auth dependency ───────────────────────────────────────────────────

    def _verify_token(request: Request) -> None:
        """Verify the Bearer token in the Authorization header."""
        if not config.require_auth:
            return
        auth  = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        # Use compare_digest to prevent timing attacks
        if not token or not secrets.compare_digest(token, request.app.state.ops_token):
            raise HTTPException(
                status_code = 401,
                detail      = "Invalid or missing ops token.",
                headers     = {"WWW-Authenticate": "Bearer"},
            )

    # ── REST endpoints ────────────────────────────────────────────────────

    @app.get("/health")
    def health() -> dict[str, str]:
        """Public health check — no auth required."""
        return {"status": "ok", "version": "0.2.0"}

    @app.get("/sessions", dependencies=[Depends(_verify_token)])
    def list_sessions(request: Request) -> list[dict]:
        """Return all active session records."""
        return list(request.app.state.sessions.values())

    @app.get("/sessions/{session_id}", dependencies=[Depends(_verify_token)])
    def get_session(session_id: str, request: Request) -> dict:
        """Return the record for a single session."""
        session = request.app.state.sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")
        return session

    @app.post("/sessions", dependencies=[Depends(_verify_token)])
    def register_session(reg: SessionRegistration, request: Request) -> dict[str, str]:
        """Register a new session (called by AgentSession.start())."""
        request.app.state.sessions[reg.session_id] = {
            "session_id":     reg.session_id,
            "manifest_goal":  reg.manifest_goal,
            "permitted_tools": reg.permitted_tools,
            "status":         "running",
        }
        return {"status": "registered", "session_id": reg.session_id}

    @app.delete("/sessions/{session_id}", dependencies=[Depends(_verify_token)])
    def close_session(session_id: str, request: Request) -> dict[str, str]:
        """Mark a session as completed and remove it from the active map."""
        request.app.state.sessions.pop(session_id, None)
        request.app.state.approval_queue.pop(session_id, None)
        return {"status": "closed", "session_id": session_id}

    @app.get("/queue", dependencies=[Depends(_verify_token)])
    def get_queue(request: Request) -> dict[str, list[dict]]:
        """Return all pending tool-call approval requests."""
        return request.app.state.approval_queue

    @app.get("/queue/{session_id}", dependencies=[Depends(_verify_token)])
    def get_session_queue(session_id: str, request: Request) -> list[dict]:
        """Return pending approvals for a specific session."""
        return request.app.state.approval_queue.get(session_id, [])

    @app.post("/queue/{session_id}", dependencies=[Depends(_verify_token)])
    def enqueue_approval(session_id: str, item: dict, request: Request) -> dict[str, str]:
        """Add a tool call to the approval queue (called by AgentSession)."""
        queue = request.app.state.approval_queue
        if session_id not in queue:
            queue[session_id] = []
        queue[session_id].append(item)
        return {"status": "queued"}

    @app.post("/approve", dependencies=[Depends(_verify_token)])
    def approve(decision: ApprovalDecision, request: Request) -> dict[str, str]:
        """Record an operator approval or rejection for a queued tool call."""
        queue = request.app.state.approval_queue
        sid   = decision.session_id

        if sid not in queue or not queue[sid]:
            raise HTTPException(
                status_code = 404,
                detail      = f"No pending approvals for session '{sid}'.",
            )

        updated = []
        for item in queue[sid]:
            if item.get("tool_name") == decision.tool_name and not item.get("resolved"):
                updated.append({**item, "approved": decision.approved,
                                 "reason": decision.reason, "resolved": True})
            else:
                updated.append(item)
        queue[sid] = updated

        return {"status": "recorded", "approved": str(decision.approved)}

    # ── WebSocket ─────────────────────────────────────────────────────────

    @app.websocket("/ws/sessions/{session_id}")
    async def session_ws(
        websocket:  WebSocket,
        session_id: str,
        token:      str | None = None,   # FIX 3: required query param
    ) -> None:
        """
        Real-time session feed.

        Fix 3: Connection is rejected with code 4401 if the token query
               parameter is absent or does not match app.state.ops_token.

        Connect with:
            ws://localhost:7477/ws/sessions/{id}?token=<ops_token>
        """
        # ── FIX 3: authenticate before accepting the connection ───────────
        if config.require_auth:
            expected = websocket.app.state.ops_token
            if not token or not secrets.compare_digest(token, expected):
                await websocket.close(code=4401, reason="Unauthorized — invalid or missing token.")
                return
        # ─────────────────────────────────────────────────────────────────

        await websocket.accept()
        try:
            while True:
                # Stream the latest session state on every client ping
                msg = await websocket.receive_text()   # blocks until client sends anything
                data = websocket.app.state.sessions.get(session_id, {})
                queue_data = websocket.app.state.approval_queue.get(session_id, [])
                await websocket.send_json({
                    "session": data,
                    "pending_approvals": queue_data,
                })
        except fastapi.WebSocketDisconnect:
            pass
        except Exception:
            pass

    return app, app.state.ops_token

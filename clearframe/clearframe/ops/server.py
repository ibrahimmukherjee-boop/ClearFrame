"""
ClearFrame AgentOps Server
===========================
REST + WebSocket API for real-time session inspection and tool-call approval.

Fix 3: WebSocket /ws/sessions/{session_id} requires ?token= before accept().
Fix 6: All state on app.state — no module globals.
Fix 7: slowapi rate limiting on all REST endpoints.
"""
from __future__ import annotations

import secrets
from typing import Any

import fastapi
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from clearframe.core.config import OpsConfig

# ── Rate limiter ──────────────────────────────────────────────────────────────
# key_func=get_remote_address rates by caller IP.
# All limits are per-IP per time window.
limiter = Limiter(
    key_func       = get_remote_address,
    default_limits = ["200/minute"],   # global fallback for any undecorated route
)

# ── Request / response models ─────────────────────────────────────────────────

class ApprovalDecision(BaseModel):
    session_id: str
    tool_name:  str
    approved:   bool
    reason:     str = ""


class SessionRegistration(BaseModel):
    session_id:      str
    manifest_goal:   str
    permitted_tools: list[str] = []


# ── Factory ───────────────────────────────────────────────────────────────────

def create_ops_app(config: OpsConfig) -> tuple[FastAPI, str]:
    """
    Create and configure the AgentOps FastAPI application.

    Returns
    -------
    (app, ops_token)
        app       — The FastAPI application instance.
        ops_token — Bearer token for authenticated endpoints.
                    Write to ~/.clearframe/ops-token (chmod 600). Never print.

    Fix 6 — all mutable state on app.state:
        app.state.sessions        dict[session_id, session_info]
        app.state.approval_queue  dict[session_id, list[pending_items]]
        app.state.ops_token       secret bearer token for this instance

    Fix 7 — slowapi rate limiting:
        200/min global  (all routes)
        120/min         /health, /sessions GET
         60/min         /sessions POST/DELETE, /queue
         30/min         /approve  (operator decisions — intentionally strict)
    """
    app = FastAPI(
        title    = "ClearFrame AgentOps",
        version  = "0.2.0",
        docs_url = None,   # Disable Swagger UI in production
        redoc_url= None,
    )

    # ── Fix 6: instance-scoped state ──────────────────────────────────────
    app.state.sessions:       dict[str, Any]        = {}
    app.state.approval_queue: dict[str, list[dict]] = {}
    app.state.ops_token:      str                   = secrets.token_urlsafe(32)
    app.state.limiter                               = limiter

    # ── Fix 7: register rate limit error handler ───────────────────────────
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins      = config.cors_origins,
        allow_methods      = ["GET", "POST", "DELETE"],
        allow_headers      = ["Authorization", "Content-Type"],
        allow_credentials  = False,
    )

    # ── Auth dependency ───────────────────────────────────────────────────

    def _verify_token(request: Request) -> None:
        """Verify the Bearer token in the Authorization header."""
        if not config.require_auth:
            return
        auth  = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if not token or not secrets.compare_digest(token, request.app.state.ops_token):
            raise HTTPException(
                status_code = 401,
                detail      = "Invalid or missing ops token.",
                headers     = {"WWW-Authenticate": "Bearer"},
            )

    # ── REST endpoints ────────────────────────────────────────────────────

    @app.get("/health")
    @limiter.limit("120/minute")
    def health(request: Request) -> dict[str, str]:
        """Public health check — no auth required."""
        return {"status": "ok", "version": "0.2.0"}

    @app.get("/sessions", dependencies=[Depends(_verify_token)])
    @limiter.limit("120/minute")
    def list_sessions(request: Request) -> list[dict]:
        """Return all active session records."""
        return list(request.app.state.sessions.values())

    @app.get("/sessions/{session_id}", dependencies=[Depends(_verify_token)])
    @limiter.limit("120/minute")
    def get_session(session_id: str, request: Request) -> dict:
        """Return the record for a single session."""
        session = request.app.state.sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")
        return session

    @app.post("/sessions", dependencies=[Depends(_verify_token)])
    @limiter.limit("60/minute")
    def register_session(reg: SessionRegistration, request: Request) -> dict[str, str]:
        """Register a new session (called by AgentSession.start())."""
        request.app.state.sessions[reg.session_id] = {
            "session_id":      reg.session_id,
            "manifest_goal":   reg.manifest_goal,
            "permitted_tools": reg.permitted_tools,
            "status":          "running",
        }
        return {"status": "registered", "session_id": reg.session_id}

    @app.delete("/sessions/{session_id}", dependencies=[Depends(_verify_token)])
    @limiter.limit("60/minute")
    def close_session(session_id: str, request: Request) -> dict[str, str]:
        """Mark a session as completed and remove it from the active map."""
        request.app.state.sessions.pop(session_id, None)
        request.app.state.approval_queue.pop(session_id, None)
        return {"status": "closed", "session_id": session_id}

    @app.get("/queue", dependencies=[Depends(_verify_token)])
    @limiter.limit("60/minute")
    def get_queue(request: Request) -> dict[str, list[dict]]:
        """Return all pending tool-call approval requests."""
        return request.app.state.approval_queue

    @app.get("/queue/{session_id}", dependencies=[Depends(_verify_token)])
    @limiter.limit("60/minute")
    def get_session_queue(session_id: str, request: Request) -> list[dict]:
        """Return pending approvals for a specific session."""
        return request.app.state.approval_queue.get(session_id, [])

    @app.post("/queue/{session_id}", dependencies=[Depends(_verify_token)])
    @limiter.limit("60/minute")
    def enqueue_approval(session_id: str, item: dict, request: Request) -> dict[str, str]:
        """Add a tool call to the approval queue (called by AgentSession)."""
        queue = request.app.state.approval_queue
        if session_id not in queue:
            queue[session_id] = []
        queue[session_id].append(item)
        return {"status": "queued"}

    @app.post("/approve", dependencies=[Depends(_verify_token)])
    @limiter.limit("30/minute")   # Strictest limit — operator decisions
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
                updated.append({
                    **item,
                    "approved": decision.approved,
                    "reason":   decision.reason,
                    "resolved": True,
                })
            else:
                updated.append(item)
        queue[sid] = updated
        return {"status": "recorded", "approved": str(decision.approved)}

    # ── WebSocket ─────────────────────────────────────────────────────────

    @app.websocket("/ws/sessions/{session_id}")
    async def session_ws(
        websocket:  WebSocket,
        session_id: str,
        token:      str | None = None,   # Fix 3: required query param
    ) -> None:
        """
        Real-time session feed.
        Fix 3: Rejected with code 4401 if token is missing or invalid.
        Connect: ws://localhost:7477/ws/sessions/{id}?token=<ops_token>
        """
        if config.require_auth:
            expected = websocket.app.state.ops_token
            if not token or not secrets.compare_digest(token, expected):
                await websocket.close(code=4401, reason="Unauthorized — invalid or missing token.")
                return

        await websocket.accept()
        try:
            while True:
                await websocket.receive_text()
                data       = websocket.app.state.sessions.get(session_id, {})
                queue_data = websocket.app.state.approval_queue.get(session_id, [])
                await websocket.send_json({
                    "session":          data,
                    "pending_approvals": queue_data,
                })
        except fastapi.WebSocketDisconnect:
            pass
        except Exception:
            pass

    return app, app.state.ops_token

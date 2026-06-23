from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from aegis.store import AegisStore, HITLRequest, HITLType


class EnqueueBody(BaseModel):
    agent_id: str
    agent_name: str
    session_id: str = ""
    type: HITLType = HITLType.APPROVAL
    payload: str
    timeout_seconds: int = 3600


class DecisionBody(BaseModel):
    approved: bool
    reviewer: str = "operator"
    note: str = ""


def create_app(state_path: Path) -> FastAPI:
    store = AegisStore(state_path)
    app = FastAPI(title="Nexus Aegis HITL", version="0.1.0")
    app.state.store = store

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "aegis"}

    @app.get("/queue")
    def queue() -> list[dict]:
        return [r.to_api_dict() for r in store.list_pending()]

    @app.get("/history")
    def history() -> list[dict]:
        return [r.to_api_dict() for r in store.list_all()]

    @app.post("/queue")
    def enqueue(body: EnqueueBody) -> dict:
        req = HITLRequest(
            agent_id=body.agent_id,
            agent_name=body.agent_name,
            session_id=body.session_id,
            type=body.type,
            payload=body.payload,
            timeout_at=time.time() + body.timeout_seconds,
        )
        store.enqueue(req)
        return req.to_api_dict()

    @app.post("/queue/{request_id}/approve")
    def approve(request_id: str, body: DecisionBody) -> dict:
        try:
            req = store.decide(request_id, approved=True, reviewer=body.reviewer, note=body.note)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Request not found.") from exc
        return req.to_api_dict()

    @app.post("/queue/{request_id}/reject")
    def reject(request_id: str, body: DecisionBody) -> dict:
        try:
            req = store.decide(request_id, approved=False, reviewer=body.reviewer, note=body.note)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Request not found.") from exc
        return req.to_api_dict()

    return app

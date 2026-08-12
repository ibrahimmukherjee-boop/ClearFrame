from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class HITLType(str, Enum):
    APPROVAL = "approval"
    REJECTION = "rejection"
    REVISION = "revision"


class HITLStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class HITLRequest(BaseModel):
    id: str = Field(default_factory=lambda: f"h-{uuid.uuid4().hex[:8]}")
    agent_id: str
    agent_name: str
    session_id: str = ""
    type: HITLType = HITLType.APPROVAL
    payload: str
    status: HITLStatus = HITLStatus.PENDING
    created_at: float = Field(default_factory=time.time)
    timeout_at: float = 0.0
    reviewed_at: float | None = None
    reviewer: str | None = None
    review_note: str = ""

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agentId": self.agent_id,
            "agentName": self.agent_name,
            "sessionId": self.session_id,
            "type": self.type.value,
            "payload": self.payload,
            "status": self.status.value,
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.created_at)),
            "timeoutAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.timeout_at)) if self.timeout_at else "",
            "reviewedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.reviewed_at)) if self.reviewed_at else None,
            "reviewer": self.reviewer,
            "reviewNote": self.review_note,
        }


class AegisStore:
    def __init__(self, state_path: Path | None = None) -> None:
        self._path = state_path
        self._requests: dict[str, HITLRequest] = {}
        if state_path and state_path.exists():
            self._load()

    def enqueue(self, req: HITLRequest) -> HITLRequest:
        self._requests[req.id] = req
        self._save()
        return req

    def list_pending(self) -> list[HITLRequest]:
        now = time.time()
        for req in self._requests.values():
            if req.status == HITLStatus.PENDING and req.timeout_at and now > req.timeout_at:
                req.status = HITLStatus.TIMEOUT
        self._save()
        return [r for r in self._requests.values() if r.status == HITLStatus.PENDING]

    def list_all(self) -> list[HITLRequest]:
        return list(self._requests.values())

    def decide(self, request_id: str, approved: bool, reviewer: str = "operator", note: str = "") -> HITLRequest:
        req = self._requests.get(request_id)
        if req is None:
            raise KeyError(request_id)
        req.status = HITLStatus.APPROVED if approved else HITLStatus.REJECTED
        req.reviewed_at = time.time()
        req.reviewer = reviewer
        req.review_note = note
        self._save()
        return req

    def _save(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps([r.model_dump() for r in self._requests.values()], indent=2))

    def _load(self) -> None:
        for item in json.loads(self._path.read_text()):
            req = HITLRequest.model_validate(item)
            self._requests[req.id] = req

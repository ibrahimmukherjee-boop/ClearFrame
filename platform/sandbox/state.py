"""sandbox/state.py — shared in-memory state for the sandbox session."""
from __future__ import annotations
import uuid
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentConfig:
    agent_id: str = ""
    name: str = ""
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    provider: str = "ollama"
    model: str = "llama3"
    max_steps: int = 10
    allow_web: bool = False
    allow_fs: bool = False
    allow_exec: bool = False


@dataclass
class OperatorSession:
    operator_id: str = ""
    name: str = ""
    verified: bool = False
    trust_score: float = 0.0
    auth_method: str = ""
    timestamp: float = 0.0


@dataclass
class TrustCert:
    cert_id: str = ""
    agent_id: str = ""
    trust_level: str = ""
    capabilities: List[str] = field(default_factory=list)
    issued_at: float = 0.0
    expires_at: float = 0.0
    revoked: bool = False
    signature: str = ""


@dataclass
class AgentSession:
    session_id: str = ""
    agent_id: str = ""
    status: str = "pending"  # pending | approved | running | terminated | denied
    steps: List[Dict[str, Any]] = field(default_factory=list)
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    audit_log: List[Dict[str, Any]] = field(default_factory=list)
    started_at: float = 0.0
    ended_at: float = 0.0


class SandboxState:
    """Singleton-like shared state for the Gradio sandbox."""

    def __init__(self) -> None:
        self.operator: OperatorSession = OperatorSession()
        self.agent: AgentConfig = AgentConfig()
        self.cert: Optional[TrustCert] = None
        self.session: Optional[AgentSession] = None
        self.sonar_events: List[Dict[str, Any]] = []
        self.aegis_queue: List[Dict[str, Any]] = []
        self.pipeline_log: List[str] = []

    # ------------------------------------------------------------------ helpers

    def reset(self) -> None:
        self.__init__()

    def new_agent_id(self) -> str:
        return "agent-" + uuid.uuid4().hex[:8]

    def new_session_id(self) -> str:
        return "sess-" + uuid.uuid4().hex[:8]

    def new_cert_id(self) -> str:
        return "cert-" + uuid.uuid4().hex[:8]

    def log_pipeline(self, step: str, detail: str = "") -> None:
        ts = time.strftime("%H:%M:%S")
        self.pipeline_log.append(f"[{ts}] {step}" + (f" — {detail}" if detail else ""))

    def pipeline_log_text(self) -> str:
        return "\n".join(self.pipeline_log) if self.pipeline_log else "No steps yet."

"""
ClearFrame AgentSession — the main runtime orchestrator.

Coordinates:
  1. GoalManifest declaration and lock
  2. Vault (credentials)
  3. Reader/Actor isolation layer
  4. Goal Monitor (alignment scoring on every tool call)
  5. RTL (reasoning trace recording)
  6. Audit log (HMAC-chained, every event)
  7. Context Feed Auditor (hash every context chunk)
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Callable

from clearframe.core.audit import AuditLog, EventType
from clearframe.core.config import ClearFrameConfig
from clearframe.core.manifest import GoalManifest
from clearframe.core.vault import Vault
from clearframe.monitor.goal_monitor import GoalMonitor, Disposition
from clearframe.monitor.rtl import RTL
from clearframe.gateway.isolation import MessagePipe, ReaderSandbox, ActorSandbox


class SessionError(Exception):
    pass


class AgentSession:
    """
    A single ClearFrame agent session.

    Usage:
        config = ClearFrameConfig()
        manifest = GoalManifest(
            goal="Search for AI safety papers and summarise them",
            permitted_tools=[ToolPermission(tool_name="web_search", max_calls_per_session=5)],
        )
        async with AgentSession(config, manifest) as session:
            result = await session.call_tool("web_search", query="AI safety 2026")
    """

    def __init__(
        self,
        config: ClearFrameConfig,
        manifest: GoalManifest,
        tool_registry: dict[str, Callable] | None = None,
    ) -> None:
        self._config = config
        self._manifest = manifest
        self._tools = tool_registry or {}
        self._session_id = str(uuid.uuid4())
        self._start_time = time.time()

        self._audit   = AuditLog(config.audit)
        self._vault   = Vault(config.vault)
        self._monitor = GoalMonitor(manifest, config.goal_monitor)
        self._rtl     = RTL(self._session_id, config.rtl)

        self._pipe   = MessagePipe()
        self._reader = ReaderSandbox(self._session_id, self._pipe)
        self._actor  = ActorSandbox(self._session_id, self._pipe, self._tools)

        self._context_chunks: list[dict] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._manifest.lock()
        self._audit.write(EventType.SESSION_START, self._session_id, {
            "manifest_goal": self._manifest.goal[:200],
            "permitted_tools": [p.tool_name for p in self._manifest.permitted_tools],
            "allow_file_write": self._manifest.allow_file_write,
            "allow_code_execution": self._manifest.allow_code_execution,
            "max_steps": self._manifest.max_steps,
        })

    async def end(self, outcome: str = "completed") -> None:
        elapsed = time.time() - self._start_time
        self._audit.write(EventType.SESSION_END, self._session_id, {
            "outcome": outcome,
            "elapsed_seconds": round(elapsed, 2),
            "monitor_stats": self._monitor.stats(),
            "context_chunks": len(self._context_chunks),
        })
        self._vault.lock()

    # ------------------------------------------------------------------
    # Tool call — main user-facing method
    # ------------------------------------------------------------------

    async def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """
        Request a tool call. The Goal Monitor evaluates alignment first.
        Only approved / auto-approved calls reach the Actor sandbox.
        """
        args = dict(kwargs)
        self._rtl.record("tool_call", f"{tool_name}({args})")

        scored = self._monitor.evaluate(tool_name, args)
        self._audit.write(EventType.GOAL_SCORE, self._session_id, {
            "tool_name": tool_name,
            "score": scored.alignment_score,
            "disposition": scored.disposition.value,
            "reasons": scored.reasons,
        })

        if scored.disposition == Disposition.BLOCK:
            self._audit.write(EventType.TOOL_CALL_BLOCKED, self._session_id, {
                "tool_name": tool_name, "reasons": scored.reasons,
            })
            raise SessionError(
                f"[ClearFrame] Tool '{tool_name}' BLOCKED. "
                f"Score: {scored.alignment_score}. Reasons: {scored.reasons}"
            )

        if scored.disposition == Disposition.QUEUE:
            self._audit.write(EventType.TOOL_CALL_REQUESTED, self._session_id, {
                "tool_name": tool_name,
                "score": scored.alignment_score,
                "status": "pending_operator_approval",
            })
            raise SessionError(
                f"[ClearFrame] Tool '{tool_name}' queued for operator approval "
                f"(score: {scored.alignment_score}). Check AgentOps dashboard."
            )

        # Approved — execute via Actor sandbox
        self._audit.write(EventType.TOOL_CALL_APPROVED, self._session_id, {
            "tool_name": tool_name, "score": scored.alignment_score,
        })
        result = await self._actor.execute_approved_call(tool_name, args)
        self._audit.write(EventType.TOOL_CALL_COMPLETED, self._session_id, {
            "tool_name": tool_name, "result_preview": str(result)[:200],
        })
        return result

    # ------------------------------------------------------------------
    # Context Feed Auditor
    # ------------------------------------------------------------------

    async def ingest_context(self, content: str, source: str) -> str:
        """
        Ingest untrusted content through the Reader sandbox.
        Source-tagged and SHA-256 hashed into the audit log.
        Returns the content hash.
        """
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        self._audit.write(EventType.CONTEXT_HASH, self._session_id, {
            "source": source, "length": len(content), "sha256": content_hash,
        })
        await self._reader.ingest_text(content, source)
        self._context_chunks.append({"source": source, "hash": content_hash})
        return content_hash

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "AgentSession":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, *_: Any) -> None:
        await self.end("error" if exc_type else "completed")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def audit(self) -> AuditLog:
        return self._audit

    @property
    def rtl(self) -> RTL:
        return self._rtl

    @property
    def monitor(self) -> GoalMonitor:
        return self._monitor

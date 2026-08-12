"""The NexusProtocol autonomous loop.

Runs the full plan→act→observe cycle **inside** the governed session: every
tool call the model requests passes the Policy Engine, Goal Monitor, Sonar
hooks, and lands in the HMAC audit chain. Every step is checkpointed.

Each action produces a ReasoningChunk answering WHAT / WHY / HOW:
  what — the model's intent (tool + rationale)
  why  — the governance verdict (policy rule, goal alignment score)
  how  — execution detail (args, observation, audit reference)
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from clearframe.core.checkpoint import Checkpoint, CheckpointStore
from clearframe.core.session import AgentSession, SessionError
from clearframe.loop.providers import LLMTurn


@dataclass
class ReasoningChunk:
    step: int
    kind: str                       # plan | action | blocked | hitl | answer
    what: str
    why: str
    how: str
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    policy: dict[str, Any] = field(default_factory=dict)
    alignment: float | None = None
    audit_ref: str = ""
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LoopResult:
    session_id: str
    status: str                     # completed | max_steps | awaiting_hitl | failed
    answer: str = ""
    steps: int = 0
    chunks: list[ReasoningChunk] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "answer": self.answer,
            "steps": self.steps,
            "chunks": [c.to_dict() for c in self.chunks],
        }


SYSTEM_PROMPT = (
    "You are a governed agent running on NexusProtocol. Work toward the "
    "declared goal using only the provided tools. Every tool call is policy-"
    "checked, alignment-scored, and audited. When the task is done, reply "
    "with the final answer and no tool calls."
)


class AgentLoop:
    """Autonomous, governed, checkpointed agent execution."""

    def __init__(
        self,
        session: AgentSession,
        provider: Any,                       # anything with .complete(messages, tools)
        tool_schemas: list[dict] | None = None,
        max_steps: int = 12,
        checkpoints: CheckpointStore | None = None,
    ) -> None:
        self._session = session
        self._provider = provider
        self._schemas = tool_schemas or []
        self._max_steps = max_steps
        self._checkpoints = checkpoints or CheckpointStore()
        self._loop_id = f"loop-{uuid.uuid4().hex[:10]}"

    @staticmethod
    def _audit_ref(tool: str, args: dict, step: int) -> str:
        raw = f"{tool}:{sorted(args.items())}:{step}:{time.time()//60}"
        return "audit:" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def run(self, task: str, resume_from: Checkpoint | None = None) -> LoopResult:
        history: list[dict[str, Any]]
        chunks: list[ReasoningChunk]
        start_step = 0

        if resume_from is not None:
            history = list(resume_from.history)
            chunks = [ReasoningChunk(**c) for c in resume_from.chunks]
            start_step = resume_from.step + 1
        else:
            history = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": task},
            ]
            chunks = []

        result = LoopResult(session_id=self._loop_id, status="running")

        for step in range(start_step, self._max_steps):
            turn: LLMTurn = await self._provider.complete(history, self._schemas)

            if turn.is_final:
                answer = turn.content or ""
                chunks.append(ReasoningChunk(
                    step=step, kind="answer",
                    what="Deliver final answer",
                    why="Model signalled completion; goal satisfied within manifest.",
                    how=f"Answer of {len(answer)} chars returned to caller; session closed in audit chain.",
                    observation=answer[:400],
                    audit_ref=self._audit_ref("__answer__", {"step": step}, step),
                ))
                self._save(step, "completed", task, history, chunks)
                result.status, result.answer = "completed", answer
                break

            for tc in turn.tool_calls:
                ref = self._audit_ref(tc.name, tc.args, step)
                try:
                    observation = await self._session.call_tool(tc.name, **tc.args)
                    decision = getattr(self._session, "last_decision", {}) or {}
                    chunks.append(ReasoningChunk(
                        step=step, kind="action",
                        what=turn.thought or f"Call tool '{tc.name}' to progress the goal.",
                        why=self._why(decision),
                        how=f"Executed {tc.name}({tc.args}) in Actor sandbox; result appended to context.",
                        tool=tc.name, args=tc.args,
                        observation=str(observation)[:400],
                        policy=decision.get("policy", {}),
                        alignment=decision.get("alignment"),
                        audit_ref=ref,
                    ))
                    history.append({"role": "assistant", "content": None, "tool_calls": [{
                        "id": ref, "type": "function",
                        "function": {"name": tc.name, "arguments": str(tc.args)},
                    }]})
                    history.append({
                        "role": "tool", "tool_call_id": ref, "content": str(observation)[:2000],
                    })
                except SessionError as exc:
                    reason = str(exc)
                    kind = "hitl" if ("approval" in reason or "queued" in reason.lower()) else "blocked"
                    decision = getattr(self._session, "last_decision", {}) or {}
                    chunks.append(ReasoningChunk(
                        step=step, kind=kind,
                        what=turn.thought or f"Attempted tool '{tc.name}'.",
                        why=reason,
                        how=("Queued for Aegis human review; loop pauses fail-closed."
                             if kind == "hitl" else
                             "Execution refused before the Actor sandbox; nothing ran."),
                        tool=tc.name, args=tc.args,
                        policy=decision.get("policy", {}),
                        alignment=decision.get("alignment"),
                        audit_ref=ref,
                    ))
                    history.append({"role": "tool", "tool_call_id": ref,
                                    "content": f"GOVERNANCE: {reason}"})
                    if kind == "hitl":
                        self._save(step, "awaiting_hitl", task, history, chunks)
                        result.status = "awaiting_hitl"
                        result.steps = step + 1
                        result.chunks = chunks
                        return result

            self._save(step, "running", task, history, chunks)
        else:
            result.status = "max_steps"
            self._save(self._max_steps, "max_steps", task, history, chunks)

        result.steps = len({c.step for c in chunks})
        result.chunks = chunks
        return result

    def _why(self, decision: dict[str, Any]) -> str:
        policy = decision.get("policy") or {}
        parts = []
        if policy:
            parts.append(
                f"Policy '{policy.get('pack', 'baseline')}' → {policy.get('decision', 'allow')}"
                + (f" ({policy.get('rule')})" if policy.get("rule") else "")
            )
        if decision.get("alignment") is not None:
            parts.append(f"goal alignment {decision['alignment']:.2f} → {decision.get('disposition', 'approve')}")
        return "; ".join(parts) or "Within manifest scope; no policy objection."

    def _save(self, step: int, status: str, task: str,
              history: list[dict], chunks: list[ReasoningChunk]) -> None:
        self._checkpoints.save(Checkpoint(
            session_id=self._loop_id, step=step, status=status, task=task,
            history=history, chunks=[c.to_dict() for c in chunks],
        ))

    @property
    def loop_id(self) -> str:
        return self._loop_id

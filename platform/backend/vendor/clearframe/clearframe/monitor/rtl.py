"""
ClearFrame Reasoning Transparency Layer (RTL)

Captures every reasoning step as tamper-evident, hashed, queryable JSON.
SHA-256 content hash per step. Full forensic replay always possible.

Contrast with OpenClaw/MCP: chain-of-thought is never captured.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from clearframe.core.config import RTLConfig


class ReasoningStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    seq: int
    timestamp: float = Field(default_factory=time.time)
    step_type: str   # "thought" | "tool_call" | "observation" | "final_answer"
    content: str
    content_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RTL:
    """Records every reasoning step for a session as newline-delimited JSON."""

    def __init__(self, session_id: str, config: RTLConfig) -> None:
        self._session_id = session_id
        self._config = config
        self._seq = 0
        self._path = Path(config.rtl_path) / f"{session_id}.jsonl"
        if config.enabled:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, step_type: str, content: str, metadata: dict[str, Any] | None = None) -> ReasoningStep:
        self._seq += 1
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        step = ReasoningStep(
            session_id=self._session_id,
            seq=self._seq,
            step_type=step_type,
            content=content,
            content_hash=content_hash,
            metadata=metadata or {},
        )
        if self._config.enabled:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(step.model_dump_json() + "\n")
        return step

    def replay(self) -> list[ReasoningStep]:
        if not self._path.exists():
            return []
        steps = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    steps.append(ReasoningStep.model_validate_json(line))
        return steps

    def verify_hashes(self) -> tuple[bool, list[str]]:
        errors = []
        for step in self.replay():
            expected = hashlib.sha256(step.content.encode()).hexdigest()
            if step.content_hash != expected:
                errors.append(f"Step {step.seq} ({step.step_type}): content hash mismatch")
        return len(errors) == 0, errors

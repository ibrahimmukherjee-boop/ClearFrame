from __future__ import annotations

import json
import re
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ThreatType(str, Enum):
    PROMPT_INJECTION = "prompt_injection"
    DATA_LEAK = "data_leak"
    POLICY_VIOLATION = "policy_violation"
    HALLUCINATION = "hallucination"
    ANOMALY = "anomaly"
    OK = "ok"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(your\s+)?system\s+prompt",
    r"you\s+are\s+now\s+",
    r"jailbreak",
    r"<\s*script",
    r"sudo\s+rm\s+-rf",
]

PII_PATTERNS = [
    r"\b\d{3}-\d{2}-\d{4}\b",          # SSN-like
    r"\b\d{16}\b",                      # card-like
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
]


class ThreatEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    time: str = Field(default_factory=lambda: time.strftime("%H:%M:%S"))
    agent: str = "unknown"
    type: ThreatType = ThreatType.OK
    severity: Severity = Severity.INFO
    message: str = ""
    model: str = "unknown"
    blocked: bool = False

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump()


class SonarEngine:
    def __init__(self, state_path: Path | None = None, block_on_critical: bool = True) -> None:
        self._path = state_path
        self._block_on_critical = block_on_critical
        self._events: list[ThreatEvent] = []
        if state_path and state_path.exists():
            self._load()

    def scan(self, *, agent: str, prompt: str, response: str = "", model: str = "gpt-4o") -> dict[str, Any]:
        events: list[ThreatEvent] = []
        blocked = False

        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, prompt, re.IGNORECASE):
                evt = ThreatEvent(
                    agent=agent, type=ThreatType.PROMPT_INJECTION, severity=Severity.CRITICAL,
                    message="Prompt injection pattern detected in user-supplied context",
                    model=model, blocked=True,
                )
                events.append(evt)
                blocked = True
                break

        scan_text = f"{prompt}\n{response}"
        for pattern in PII_PATTERNS:
            if re.search(pattern, scan_text):
                events.append(ThreatEvent(
                    agent=agent, type=ThreatType.DATA_LEAK, severity=Severity.HIGH,
                    message="PII pattern matched in agent input/output",
                    model=model, blocked=self._block_on_critical,
                ))
                if self._block_on_critical:
                    blocked = True
                break

        if "password" in prompt.lower() and "exfiltrate" in prompt.lower():
            events.append(ThreatEvent(
                agent=agent, type=ThreatType.POLICY_VIOLATION, severity=Severity.MEDIUM,
                message="Tool call attempted outside declared capability scope",
                model=model,
            ))

        if not events:
            events.append(ThreatEvent(
                agent=agent, type=ThreatType.OK, severity=Severity.INFO,
                message="Routine scan passed — output within policy bounds",
                model=model,
            ))

        self._events = (events + self._events)[:200]
        self._save()
        return {
            "safe": not blocked,
            "blocked": blocked,
            "alerts": [e.to_api_dict() for e in events],
            "safe_prompt": prompt if not blocked else "[BLOCKED BY SONAR]",
        }

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return [e.to_api_dict() for e in self._events[:limit]]

    def _save(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps([e.model_dump() for e in self._events], indent=2))

    def _load(self) -> None:
        self._events = [ThreatEvent.model_validate(x) for x in json.loads(self._path.read_text())]

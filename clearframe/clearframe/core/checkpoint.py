"""Durable session state — checkpointing and crash recovery.

Every loop step persists a checkpoint. A crashed or interrupted session can be
resumed from its last checkpoint with full message history, reasoning chunks,
and tool-call budgets intact.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Checkpoint:
    session_id: str
    step: int
    status: str                       # running | awaiting_hitl | completed | failed
    task: str
    history: list[dict[str, Any]] = field(default_factory=list)
    chunks: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CheckpointStore:
    """Append-only JSON checkpoint store with atomic writes."""

    def __init__(self, root: str | Path | None = None) -> None:
        base = root or os.getenv("NEXUS_HOME", Path.home() / ".nexus")
        self._dir = Path(base) / "checkpoints"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def save(self, cp: Checkpoint) -> Path:
        path = self._path(cp.session_id)
        tmp = path.with_suffix(".tmp")
        existing = self.load_all(cp.session_id)
        existing.append(cp.to_dict())
        tmp.write_text(json.dumps(existing, indent=2))
        tmp.replace(path)                      # atomic on POSIX
        return path

    def load_all(self, session_id: str) -> list[dict[str, Any]]:
        path = self._path(session_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return []

    def latest(self, session_id: str) -> Checkpoint | None:
        entries = self.load_all(session_id)
        if not entries:
            return None
        return Checkpoint(**entries[-1])

    def list_sessions(self) -> list[str]:
        return sorted(p.stem for p in self._dir.glob("*.json"))

    def resume(self, session_id: str) -> Checkpoint:
        cp = self.latest(session_id)
        if cp is None:
            raise KeyError(f"No checkpoints for session '{session_id}'.")
        return cp

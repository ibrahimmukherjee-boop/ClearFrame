"""
ClearFrame Goal Monitor — alignment scoring engine.

Scores every proposed tool call against the declared GoalManifest.
  score >= auto_approve_threshold  → AUTO_APPROVE
  score >= alignment_threshold     → APPROVE
  score <  alignment_threshold     → BLOCK or QUEUE (operator approval)
  hard violation                   → BLOCK (score 0.0, immediate)

Contrast with OpenClaw/MCP: no concept of a declared goal exists.
The runtime cannot detect agent drift.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from clearframe.core.manifest import GoalManifest, ToolPermission
from clearframe.core.config import GoalMonitorConfig


class Disposition(str, Enum):
    AUTO_APPROVE = "auto_approve"
    APPROVE      = "approve"
    QUEUE        = "queue"          # Awaiting operator decision
    BLOCK        = "block"


@dataclass
class ScoredCall:
    tool_name: str
    args: dict[str, Any]
    alignment_score: float
    disposition: Disposition
    reasons: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class GoalMonitor:
    """Scores each proposed tool call for alignment with the GoalManifest."""

    def __init__(self, manifest: GoalManifest, config: GoalMonitorConfig) -> None:
        self._manifest = manifest
        self._config = config
        self._call_counts: dict[str, int] = {}
        self._consecutive_low: int = 0
        self._suspended: bool = False

    def evaluate(self, tool_name: str, args: dict[str, Any]) -> ScoredCall:
        """Evaluate a proposed tool call. Returns a ScoredCall with disposition."""
        reasons: list[str] = []

        # Session suspended after repeated low-alignment calls
        if self._suspended:
            return ScoredCall(
                tool_name=tool_name, args=args,
                alignment_score=0.0, disposition=Disposition.BLOCK,
                reasons=["Session suspended after repeated low-alignment calls."],
            )

        # Hard block: tool not in permitted list
        if not self._manifest.is_tool_permitted(tool_name):
            return ScoredCall(
                tool_name=tool_name, args=args,
                alignment_score=0.0, disposition=Disposition.BLOCK,
                reasons=[f"Tool '{tool_name}' is not in permitted_tools."],
            )

        permission: ToolPermission = self._manifest.get_tool_permission(tool_name)  # type: ignore

        # Hard block: call count limit
        count = self._call_counts.get(tool_name, 0)
        if permission.max_calls_per_session is not None and count >= permission.max_calls_per_session:
            return ScoredCall(
                tool_name=tool_name, args=args,
                alignment_score=0.0, disposition=Disposition.BLOCK,
                reasons=[f"Call limit ({permission.max_calls_per_session}) reached for '{tool_name}'."],
            )

        # Hard block: file write not permitted
        if tool_name in ("write_file", "create_file", "append_file", "delete_file"):
            if not self._manifest.allow_file_write:
                return ScoredCall(
                    tool_name=tool_name, args=args,
                    alignment_score=0.0, disposition=Disposition.BLOCK,
                    reasons=["File write not permitted in GoalManifest."],
                )

        # Hard block: code execution not permitted
        if tool_name in ("run_shell", "execute_python", "run_bash", "exec", "subprocess"):
            if not self._manifest.allow_code_execution:
                return ScoredCall(
                    tool_name=tool_name, args=args,
                    alignment_score=0.0, disposition=Disposition.BLOCK,
                    reasons=["Code execution not permitted in GoalManifest."],
                )

        # --- Soft scoring (0.0 – 1.0) ---
        score = 1.0

        # Domain scope check
        if tool_name in ("web_fetch", "web_search", "http_get", "http_post", "read_url"):
            url = args.get("url") or args.get("query") or ""
            if self._manifest.resource_scope.allowed_domains:
                matched = any(
                    self._domain_matches(url, d)
                    for d in self._manifest.resource_scope.allowed_domains
                )
                if not matched:
                    score -= 0.30
                    reasons.append(f"Target '{url[:80]}' is outside declared allowed_domains.")

        # Goal keyword overlap
        goal_words = set(self._manifest.goal.lower().split())
        call_words = set(
            (tool_name.replace("_", " ") + " " + " ".join(str(v) for v in args.values())).lower().split()
        )
        overlap = goal_words & call_words
        if overlap:
            score = min(1.0, score + 0.04 * len(overlap))
            reasons.append(f"Goal keyword overlap: {sorted(overlap)[:5]}")
        else:
            score -= 0.10
            reasons.append("No keyword overlap with declared goal.")

        # Operator-flagged tool: always queue regardless of score
        if permission.require_approval:
            self._call_counts[tool_name] = count + 1
            reasons.append("Operator approval required for this tool.")
            return ScoredCall(
                tool_name=tool_name, args=args,
                alignment_score=round(max(0.0, min(1.0, score)), 3),
                disposition=Disposition.QUEUE,
                reasons=reasons,
            )

        score = round(max(0.0, min(1.0, score)), 3)

        # Decide disposition
        if score >= self._config.auto_approve_threshold:
            disposition = Disposition.AUTO_APPROVE
            self._consecutive_low = 0
        elif score >= self._config.alignment_threshold:
            disposition = Disposition.APPROVE
            self._consecutive_low = 0
        else:
            self._consecutive_low += 1
            if self._consecutive_low >= self._config.max_consecutive_low_scores:
                self._suspended = True
                reasons.append(
                    f"Session suspended: {self._config.max_consecutive_low_scores} "
                    "consecutive low-alignment calls."
                )
                disposition = Disposition.BLOCK
            elif self._config.pause_on_ambiguous:
                disposition = Disposition.QUEUE
            else:
                disposition = Disposition.BLOCK

        self._call_counts[tool_name] = count + 1
        return ScoredCall(
            tool_name=tool_name, args=args,
            alignment_score=score,
            disposition=disposition,
            reasons=reasons,
        )

    def _domain_matches(self, url: str, pattern: str) -> bool:
        regex = re.escape(pattern).replace(r"\*", ".*")
        return bool(re.search(regex, url))

    def stats(self) -> dict[str, Any]:
        return {
            "call_counts": self._call_counts,
            "consecutive_low_scores": self._consecutive_low,
            "suspended": self._suspended,
        }

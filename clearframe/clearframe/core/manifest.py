"""
ClearFrame GoalManifest

Every agent session MUST declare:
  - A plain-English goal
  - The exact set of tools it is permitted to use
  - Resource scope (allowed domains, paths)
  - Whether file writes and code execution are permitted

This declaration is written to the audit log at session start and
evaluated by the Goal Monitor on every tool call.

Contrast with OpenClaw/MCP: there is no concept of a declared goal.
The runtime has no idea what the agent is supposed to be doing,
so it cannot detect drift.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class ResourceScope(BaseModel):
    """Defines the external resources an agent is permitted to access."""
    allowed_domains: list[str] = Field(
        default_factory=list,
        description=(
            "Domains the agent may fetch. Supports * wildcard. "
            "Empty list = unrestricted (logged but not blocked)."
        ),
    )
    allowed_paths: list[str] = Field(
        default_factory=list,
        description="Filesystem paths the agent may read. Empty = none.",
    )
    allowed_write_paths: list[str] = Field(
        default_factory=list,
        description="Filesystem paths the agent may write. Empty = none.",
    )


class ToolPermission(BaseModel):
    """Declares permission for a single tool."""
    tool_name: str
    max_calls_per_session: Optional[int] = None   # None = unlimited
    require_approval: bool = False                 # True = always queue for operator
    allowed_arg_patterns: dict[str, str] = Field(
        default_factory=dict,
        description="Optional regex patterns for arg validation. e.g. {'query': '^[a-zA-Z ]+$'}",
    )


class GoalManifest(BaseModel):
    """
    The complete declaration of what an agent session is allowed to do.

    Immutable once a session starts. Any attempt to modify it after
    session start raises ManifestLockError.
    """

    goal: str = Field(
        ...,
        description="Plain-English statement of what this agent session should accomplish.",
        min_length=10,
        max_length=2000,
    )
    permitted_tools: list[ToolPermission] = Field(
        default_factory=list,
        description="Explicit allowlist of tools. Tools not listed are blocked.",
    )
    resource_scope: ResourceScope = Field(default_factory=ResourceScope)
    allow_file_write: bool = False
    allow_code_execution: bool = False
    max_steps: Optional[int] = 50
    auto_pause_on_drift: bool = True

    # Internal — set by AgentSession on start
    _locked: bool = False

    def lock(self) -> None:
        object.__setattr__(self, "_locked", True)

    def is_tool_permitted(self, tool_name: str) -> bool:
        return any(p.tool_name == tool_name for p in self.permitted_tools)

    def get_tool_permission(self, tool_name: str) -> Optional[ToolPermission]:
        return next((p for p in self.permitted_tools if p.tool_name == tool_name), None)

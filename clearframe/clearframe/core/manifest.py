"""
ClearFrame GoalManifest
=======================
Declares the agent's stated goal and capability constraints before session start.
Immutably locked once AgentSession.start() is called.

Fix 4: Added schema_version as the first field so audit replay tools can
       identify the manifest format without parsing the full document.

Fix 5: __setattr__ guard raises ManifestLockError on any mutation after lock()
       is called. Previously lock() set a flag that was never checked.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from clearframe.core.errors import ManifestLockError


# ── Sub-models ────────────────────────────────────────────────────────────────

class ToolPermission(BaseModel):
    """Permission entry for a single tool."""
    tool_name:             str
    max_calls_per_session: Optional[int] = None   # None = unlimited
    require_approval:      bool          = False  # True = queue for operator approval
    allowed_arg_patterns:  list[str]     = Field(default_factory=list)


class ResourceScope(BaseModel):
    """Network and filesystem boundaries the agent is allowed to operate within."""
    allowed_domains:    list[str] = Field(default_factory=list)   # Empty = no restriction
    allowed_file_paths: list[str] = Field(default_factory=list)   # Empty = no restriction
    max_response_bytes: int       = 10 * 1024 * 1024              # 10 MB default


# ── GoalManifest ──────────────────────────────────────────────────────────────

class GoalManifest(BaseModel):
    """
    Declares the agent's goal and capability constraints.

    Must be constructed before starting an AgentSession.
    Once AgentSession.start() calls lock(), the manifest is frozen —
    any mutation raises ManifestLockError.

    Example
    -------
        manifest = GoalManifest(
            goal="Summarise the latest AI safety papers",
            permitted_tools=[
                ToolPermission(tool_name="web_search", max_calls_per_session=10),
            ],
            allow_file_write=False,
        )
    """

    # ── FIX 4: schema_version is the FIRST field ──────────────────────────
    # Audit replay tools check this field first to determine how to parse
    # the rest of the manifest. Bump this value on any breaking schema change.
    schema_version: str = "1.0"

    # ── Core goal ─────────────────────────────────────────────────────────
    goal: str

    # ── Capability gates (all OFF by default) ─────────────────────────────
    permitted_tools:      list[ToolPermission] = Field(default_factory=list)
    allow_file_write:     bool                 = False
    allow_code_execution: bool                 = False
    max_steps:            int                  = 100
    resource_scope:       ResourceScope        = Field(default_factory=ResourceScope)

    model_config = {"validate_assignment": True, "arbitrary_types_allowed": True}

    # Internal lock state — never serialised, initialised via object.__setattr__
    # to avoid triggering our own __setattr__ guard during construction.
    def model_post_init(self, __context: object) -> None:
        object.__setattr__(self, "_locked", False)

    # ── FIX 5: immutability enforcement ───────────────────────────────────

    def lock(self) -> None:
        """
        Freeze the manifest.

        Called automatically by AgentSession.start().
        After this, any attempt to mutate a field raises ManifestLockError.
        Calling lock() more than once is safe (idempotent).
        """
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        # Allow private / dunder attributes so pydantic internals always work.
        if not name.startswith("_"):
            try:
                locked: bool = object.__getattribute__(self, "_locked")
            except AttributeError:
                locked = False
            if locked:
                raise ManifestLockError(
                    f"GoalManifest is locked — cannot modify '{name}' after "
                    "AgentSession.start() has been called. "
                    "Construct a new GoalManifest for each session."
                )
        super().__setattr__(name, value)

    # ── Helpers ───────────────────────────────────────────────────────────

    def is_tool_permitted(self, tool_name: str) -> bool:
        """Return True if tool_name appears in permitted_tools."""
        return any(p.tool_name == tool_name for p in self.permitted_tools)

    def get_tool_permission(self, tool_name: str) -> Optional[ToolPermission]:
        """Return the ToolPermission for tool_name, or None if not found."""
        for p in self.permitted_tools:
            if p.tool_name == tool_name:
                return p
        return None

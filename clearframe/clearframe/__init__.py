"""
ClearFrame — Open-source AI agent protocol with auditability,
goal monitoring, Reader/Actor isolation, and safety controls.

A production-grade alternative to OpenClaw and MCP.
"""

from clearframe.core.config import ClearFrameConfig
from clearframe.core.manifest import GoalManifest
from clearframe.core.session import AgentSession

__version__ = "0.1.0"
__all__ = ["ClearFrameConfig", "GoalManifest", "AgentSession", "__version__"]

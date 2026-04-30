"""
ClearFrame — Open-source AI agent protocol with auditability,
goal monitoring, Reader/Actor isolation, and safety controls.
A production-grade alternative to OpenClaw and MCP.
"""
from clearframe.core.config   import ClearFrameConfig
from clearframe.core.manifest import GoalManifest
from clearframe.core.session  import AgentSession

__version__ = "0.1.0"
__all__     = ["ClearFrameConfig", "GoalManifest", "AgentSession", "__version__"]

# ── Optional TrustRegistry integration ───────────────────────────────────────
# Available when installed with:  pip install clearframe[trust]
# If trust-registry is not installed, ClearFrame works standalone as normal.
try:
    from trust_registry.integrations.clearframe_plugin import (  # type: ignore[import]
        TrustGate,
        TrustGateError,
    )
    __all__ += ["TrustGate", "TrustGateError"]
except ImportError:
    pass

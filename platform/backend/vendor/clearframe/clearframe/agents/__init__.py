"""Agent creation for ClearFrame.

An AgentSpec is a portable YAML/JSON document that fully describes a governed
agent: its goal, model provider, tools (from any adapter ecosystem), policy
packs, and trust requirements. Anyone can create an agent from a spec —
via CLI (`clearframe agent new/validate`), API (POST /api/agents), or code.
"""

from clearframe.agents.spec import AgentSpec, ToolBinding, load_spec, TEMPLATE

__all__ = ["AgentSpec", "ToolBinding", "load_spec", "TEMPLATE"]

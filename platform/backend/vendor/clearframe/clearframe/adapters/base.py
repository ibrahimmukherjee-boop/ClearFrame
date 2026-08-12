from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


class AdapterError(Exception):
    pass


@dataclass
class ToolSpec:
    """Normalised description of a tool from any ecosystem."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON Schema
    source: str = "native"  # mcp | langchain | openai | bedrock | http | native
    fn: Callable[..., Awaitable[Any]] | Callable[..., Any] | None = None

    def openai_schema(self) -> dict[str, Any]:
        """Export as an OpenAI function-calling tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }


class ToolAdapter:
    """Base adapter. Subclasses discover tools and expose them as ToolSpecs."""

    source = "native"

    def discover(self) -> list[ToolSpec]:  # pragma: no cover - interface
        raise NotImplementedError

    def as_tool_registry(self) -> dict[str, Callable]:
        """Return {tool_name: callable} for AgentSession(tool_registry=...)."""
        registry: dict[str, Callable] = {}
        for spec in self.discover():
            if spec.fn is None:
                raise AdapterError(f"Tool '{spec.name}' has no callable binding.")
            registry[spec.name] = spec.fn
        return registry

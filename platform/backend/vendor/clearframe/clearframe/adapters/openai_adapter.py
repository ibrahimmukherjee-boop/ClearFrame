"""OpenAI-compatible tools adapter.

Two directions:
  1. `export(registry)`   — publish ClearFrame tools as OpenAI function-calling
     schemas (works with OpenAI Agents SDK, Azure OpenAI, Microsoft Agent
     Framework, and any OpenAI-compatible runtime such as NVIDIA NIM,
     Ollama, or vLLM).
  2. `OpenAIToolsAdapter(defs, dispatcher)` — import tool definitions from an
     OpenAI-style manifest and bind them to a dispatcher callable.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from clearframe.adapters.base import ToolAdapter, ToolSpec

Dispatcher = Callable[[str, dict[str, Any]], Awaitable[Any]]


class OpenAIToolsAdapter(ToolAdapter):
    source = "openai"

    def __init__(self, tool_defs: list[dict[str, Any]], dispatcher: Dispatcher) -> None:
        """
        tool_defs  — list of {"type": "function", "function": {...}} entries.
        dispatcher — async fn(tool_name, arguments) that executes the tool.
        """
        self._defs = tool_defs
        self._dispatch = dispatcher

    def discover(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for entry in self._defs:
            fn_def = entry.get("function", entry)
            name = fn_def["name"]
            specs.append(ToolSpec(
                name=name,
                description=fn_def.get("description", ""),
                parameters=fn_def.get("parameters", {}),
                source=self.source,
                fn=self._make_caller(name),
            ))
        return specs

    def _make_caller(self, name: str):
        async def call(**kwargs: Any) -> Any:
            return await self._dispatch(name, kwargs)
        call.__name__ = name
        return call


def export(tool_specs: list[ToolSpec]) -> list[dict[str, Any]]:
    """Export ClearFrame ToolSpecs as OpenAI function-calling definitions."""
    return [s.openai_schema() for s in tool_specs]

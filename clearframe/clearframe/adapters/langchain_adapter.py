"""LangChain / LangGraph adapter.

Wraps LangChain `BaseTool` instances (the tool layer used by LangGraph,
CrewAI, and most Python agent frameworks) into ClearFrame tool callables,
so every call flows through the Goal Monitor, Policy Engine, and audit log.

Usage:
    from langchain_community.tools import DuckDuckGoSearchRun
    adapter = LangChainAdapter([DuckDuckGoSearchRun()])
    registry = adapter.as_tool_registry()
"""

from __future__ import annotations

from typing import Any, Iterable

from clearframe.adapters.base import AdapterError, ToolAdapter, ToolSpec


class LangChainAdapter(ToolAdapter):
    source = "langchain"

    def __init__(self, tools: Iterable[Any]) -> None:
        self._tools = list(tools)
        for t in self._tools:
            if not hasattr(t, "name") or not (hasattr(t, "invoke") or hasattr(t, "run")):
                raise AdapterError(
                    f"Object {t!r} does not look like a LangChain tool "
                    "(needs .name and .invoke/.run)."
                )

    def discover(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for tool in self._tools:
            params: dict[str, Any] = {"type": "object", "properties": {}}
            schema = getattr(tool, "args_schema", None)
            if schema is not None:
                try:
                    params = schema.model_json_schema()  # pydantic v2
                except AttributeError:
                    try:
                        params = schema.schema()  # pydantic v1
                    except Exception:
                        pass
            specs.append(ToolSpec(
                name=tool.name,
                description=getattr(tool, "description", "") or "",
                parameters=params,
                source=self.source,
                fn=self._make_caller(tool),
            ))
        return specs

    @staticmethod
    def _make_caller(tool: Any):
        async def call(**kwargs: Any) -> Any:
            payload: Any = kwargs
            if list(kwargs.keys()) == ["input"]:
                payload = kwargs["input"]
            if hasattr(tool, "ainvoke"):
                return await tool.ainvoke(payload)
            if hasattr(tool, "invoke"):
                return tool.invoke(payload)
            return tool.run(payload)
        call.__name__ = tool.name
        return call

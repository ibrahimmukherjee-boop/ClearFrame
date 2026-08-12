"""Generic HTTP/OpenAPI tool adapter.

Covers any REST tool surface: NVIDIA NIM endpoints, IBM watsonx Orchestrate
skills, internal microservices, or plain webhooks. Each route becomes one
governed ClearFrame tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from clearframe.adapters.base import ToolAdapter, ToolSpec


@dataclass
class HTTPTool:
    name: str
    url: str
    method: str = "POST"
    description: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON schema
    timeout: float = 30.0


class HTTPToolAdapter(ToolAdapter):
    source = "http"

    def __init__(self, tools: list[HTTPTool]) -> None:
        self._tools = tools

    def discover(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=t.name,
                description=t.description,
                parameters=t.parameters or {"type": "object", "properties": {}},
                source=self.source,
                fn=self._make_caller(t),
            )
            for t in self._tools
        ]

    @staticmethod
    def _make_caller(tool: HTTPTool):
        async def call(**kwargs: Any) -> Any:
            async with httpx.AsyncClient(timeout=tool.timeout) as client:
                if tool.method.upper() == "GET":
                    resp = await client.get(tool.url, params=kwargs, headers=tool.headers)
                else:
                    resp = await client.request(
                        tool.method.upper(), tool.url, json=kwargs, headers=tool.headers
                    )
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            return resp.json() if "json" in ctype else resp.text
        call.__name__ = tool.name
        return call

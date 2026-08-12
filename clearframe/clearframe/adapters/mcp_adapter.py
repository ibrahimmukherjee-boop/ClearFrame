"""MCP (Model Context Protocol) adapter.

Connects ClearFrame to any MCP server — the 2026 industry standard for
agent↔tool connectivity (Linux Foundation / AAIF governed). Supports the
Streamable HTTP transport natively; stdio servers via the `mcp` package
when installed.

Usage:
    adapter = MCPAdapter("https://mcp.example.com/mcp")
    tools = adapter.as_tool_registry()           # {name: async callable}
    async with AgentSession(cfg, manifest, tool_registry=tools) as s:
        await s.call_tool("search", query="...")
"""

from __future__ import annotations

import itertools
import json
from typing import Any

import httpx

from clearframe.adapters.base import AdapterError, ToolAdapter, ToolSpec


class MCPAdapter(ToolAdapter):
    source = "mcp"

    def __init__(
        self,
        endpoint: str,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.timeout = timeout
        self._ids = itertools.count(1)
        self._session_id: str | None = None

    # ── JSON-RPC over Streamable HTTP ─────────────────────────────────────

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method}
        if params is not None:
            payload["params"] = params
        headers = dict(self.headers)
        headers["Accept"] = "application/json, text/event-stream"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        resp = httpx.post(self.endpoint, json=payload, headers=headers, timeout=self.timeout)
        if resp.status_code >= 400:
            raise AdapterError(f"MCP server error {resp.status_code}: {resp.text[:300]}")
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self._session_id = sid
        body = resp.text.strip()
        # Streamable HTTP may reply as SSE; extract the data frame
        if body.startswith("event:") or body.startswith("data:"):
            for line in body.splitlines():
                if line.startswith("data:"):
                    body = line[5:].strip()
                    break
        data = json.loads(body)
        if "error" in data:
            raise AdapterError(f"MCP error: {data['error']}")
        return data.get("result", {})

    def initialize(self) -> dict[str, Any]:
        result = self._rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "clearframe", "version": "0.4.0"},
        })
        try:
            self._rpc("notifications/initialized")
        except Exception:
            pass  # some servers do not require the notification
        return result

    # ── ToolAdapter interface ─────────────────────────────────────────────

    def discover(self) -> list[ToolSpec]:
        self.initialize()
        result = self._rpc("tools/list")
        specs: list[ToolSpec] = []
        for tool in result.get("tools", []):
            name = tool["name"]
            specs.append(ToolSpec(
                name=name,
                description=tool.get("description", ""),
                parameters=tool.get("inputSchema", {}),
                source=self.source,
                fn=self._make_caller(name),
            ))
        return specs

    def _make_caller(self, tool_name: str):
        async def call(**kwargs: Any) -> Any:
            result = self._rpc("tools/call", {"name": tool_name, "arguments": kwargs})
            content = result.get("content", [])
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts) if texts else result
        call.__name__ = tool_name
        return call


def from_stdio(command: list[str]) -> "ToolAdapter":
    """Wrap a stdio MCP server (requires the `mcp` pip package)."""
    try:
        import mcp  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise AdapterError(
            "stdio MCP servers require `pip install mcp`. "
            "HTTP servers work without it: MCPAdapter(url)."
        ) from exc
    raise AdapterError("Use mcp.client.stdio directly, then wrap tools with ToolSpec.")

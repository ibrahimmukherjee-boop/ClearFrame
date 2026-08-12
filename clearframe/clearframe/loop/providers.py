"""LLM providers for the autonomous loop.

All providers speak one contract: `complete(messages, tools) -> LLMTurn`.
A turn either requests tool calls or produces a final answer.

  - OpenAICompatProvider — any /v1/chat/completions endpoint: OpenAI, Azure
    OpenAI, NVIDIA NIM, vLLM, Together, Groq, LM Studio.
  - OllamaChatProvider   — local Ollama with native tool calling.
  - ScriptedPlanner      — deterministic planner for tests, benchmarks, and
    offline demos. No network, fully reproducible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMTurn:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    thought: str = ""            # short rationale surfaced in reasoning chunks

    @property
    def is_final(self) -> bool:
        return not self.tool_calls


class OpenAICompatProvider:
    """Any OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def complete(self, messages: list[dict], tools: list[dict]) -> LLMTurn:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        calls = [
            ToolCall(
                name=tc["function"]["name"],
                args=json.loads(tc["function"].get("arguments") or "{}"),
            )
            for tc in msg.get("tool_calls") or []
        ]
        return LLMTurn(content=msg.get("content"), tool_calls=calls)


class OllamaChatProvider:
    """Local Ollama /api/chat with native tool calling."""

    def __init__(self, model: str = "llama3.1", host: str = "http://localhost:11434",
                 timeout: float = 120.0) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    async def complete(self, messages: list[dict], tools: list[dict]) -> LLMTurn:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.host}/api/chat", json=payload)
        resp.raise_for_status()
        msg = resp.json().get("message", {})
        calls = [
            ToolCall(name=tc["function"]["name"], args=tc["function"].get("arguments") or {})
            for tc in msg.get("tool_calls") or []
        ]
        return LLMTurn(content=msg.get("content"), tool_calls=calls)


class ScriptedPlanner:
    """Deterministic planner: replays a fixed list of turns.

    Used by the governance benchmark and the offline demo so results are
    reproducible and audit-comparable across runs.
    """

    def __init__(self, turns: list[LLMTurn]) -> None:
        self._turns = list(turns)
        self._i = 0

    async def complete(self, messages: list[dict], tools: list[dict]) -> LLMTurn:
        if self._i >= len(self._turns):
            return LLMTurn(content="Task complete.", thought="Script exhausted.")
        turn = self._turns[self._i]
        self._i += 1
        return turn

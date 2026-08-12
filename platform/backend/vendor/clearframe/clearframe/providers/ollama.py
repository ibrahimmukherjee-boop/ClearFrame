"""
ClearFrame — Ollama LLM Provider
==================================
Allows ClearFrame AgentSession to use any local or cloud Ollama model
as its reasoning backend.

Usage
-----
    from clearframe.providers.ollama import OllamaProvider
    from clearframe import ClearFrameConfig, GoalManifest, AgentSession

    config = ClearFrameConfig(
        provider=OllamaProvider(model="qwen3.5", host="http://localhost:11434")
    )
    async with AgentSession(config, manifest) as session:
        result = await session.call_tool("web_search", query="AI safety")
"""
from __future__ import annotations

import json
from typing import AsyncIterator, Any

import httpx
from pydantic import BaseModel


class OllamaMessage(BaseModel):
    role:    str
    content: str


class OllamaProvider:
    """
    ClearFrame provider for Ollama local/cloud models.
    Compatible with any model on ollama.com/search.

    Parameters
    ----------
    model
        Ollama model tag, e.g. "qwen3.5", "llama3.2", "kimi-k2.5:cloud"
    host
        Ollama server URL. Default: http://localhost:11434
    context_length
        Context window in tokens. Ollama recommends 64k+ for agentic tasks.
    temperature
        Sampling temperature (0.0–1.0).
    """

    def __init__(
        self,
        model:          str   = "qwen3.5",
        host:           str   = "http://localhost:11434",
        context_length: int   = 65536,
        temperature:    float = 0.7,
    ) -> None:
        self.model          = model
        self.host           = host.rstrip("/")
        self.context_length = context_length
        self.temperature    = temperature

    async def chat(
        self,
        messages: list[dict],
        tools:    list[dict] | None = None,
        stream:   bool = False,
    ) -> dict[str, Any]:
        """
        Send a chat request to the Ollama /api/chat endpoint.
        Returns the full response dict.
        """
        payload: dict[str, Any] = {
            "model":   self.model,
            "messages": messages,
            "stream":  stream,
            "options": {
                "temperature":    self.temperature,
                "num_ctx":        self.context_length,
            },
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.host}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def stream_chat(
        self,
        messages: list[dict],
        tools:    list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """Stream tokens from Ollama as they are generated."""
        payload: dict[str, Any] = {
            "model":    self.model,
            "messages": messages,
            "stream":   True,
            "options":  {"temperature": self.temperature, "num_ctx": self.context_length},
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", f"{self.host}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.strip():
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token

    def list_local_models(self) -> list[str]:
        """Return all models currently downloaded on this Ollama instance."""
        resp = httpx.get(f"{self.host}/api/tags", timeout=10.0)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]

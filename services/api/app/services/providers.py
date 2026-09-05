"""Multi-provider LLM gateways — Ollama/SLMs, OpenAI, Anthropic, Azure, hosted OpenAI-compatible.

ClearFrame agents declare a provider + model; this module routes chat
completions through the correct gateway with a uniform response shape.
Open source ClearFrame — no proprietary cloud lock-in required.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from app.config import OLLAMA_HOST, USE_OLLAMA

PROVIDERS = ("ollama", "openai", "anthropic", "hosted", "azure_openai", "custom")


def list_providers() -> list[dict[str, Any]]:
    return [
        {"id": "ollama", "label": "Ollama (local SLM/LLM)", "configured": USE_OLLAMA, "openSource": True},
        {"id": "openai", "label": "OpenAI", "configured": bool(os.environ.get("OPENAI_API_KEY")), "openSource": False},
        {"id": "anthropic", "label": "Anthropic Claude", "configured": bool(os.environ.get("ANTHROPIC_API_KEY")), "openSource": False},
        {
            "id": "hosted",
            "label": "Hosted OpenAI-compatible gateway",
            "configured": bool(os.environ.get("HOSTED_LLM_ENDPOINT") or os.environ.get("CUSTOM_LLM_BASE_URL")),
            "openSource": True,
        },
        {"id": "azure_openai", "label": "Azure OpenAI", "configured": bool(os.environ.get("AZURE_OPENAI_API_KEY")), "openSource": False},
        {"id": "custom", "label": "Custom OpenAI-compatible", "configured": bool(os.environ.get("CUSTOM_LLM_BASE_URL")), "openSource": True},
    ]


async def chat(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
) -> dict[str, Any]:
    provider = (provider or "ollama").lower()
    if provider == "ollama":
        return await _ollama(model, messages)
    if provider == "openai":
        return await _openai(model, messages, temperature)
    if provider == "anthropic":
        return await _anthropic(model, messages, temperature)
    if provider in {"hosted", "custom", "azure_openai"}:
        return await _openai_compatible(provider, model, messages, temperature)
    raise ValueError(f"Unknown provider: {provider}")


async def _ollama(model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    if not USE_OLLAMA:
        return {"ok": False, "error": "Ollama disabled", "content": "", "provider": "ollama"}
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{OLLAMA_HOST}/api/chat", json={"model": model, "messages": messages, "stream": False})
        r.raise_for_status()
        data = r.json()
    return {"ok": True, "content": data.get("message", {}).get("content", ""), "provider": "ollama", "model": model, "raw": data}


async def _openai(model: str, messages: list[dict[str, str]], temperature: float) -> dict[str, Any]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return {"ok": False, "error": "OPENAI_API_KEY not set", "content": "", "provider": "openai"}
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model or "gpt-4o-mini", "messages": messages, "temperature": temperature},
        )
        if r.status_code >= 400:
            return {"ok": False, "error": r.text[:500], "content": "", "provider": "openai"}
        data = r.json()
    content = data["choices"][0]["message"]["content"]
    return {"ok": True, "content": content, "provider": "openai", "model": model, "raw": data}


async def _anthropic(model: str, messages: list[dict[str, str]], temperature: float) -> dict[str, Any]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"ok": False, "error": "ANTHROPIC_API_KEY not set", "content": "", "provider": "anthropic"}
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msgs = [m for m in messages if m["role"] != "system"]
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": model or "claude-3-5-haiku-latest",
                "max_tokens": 2048,
                "system": system,
                "messages": user_msgs,
                "temperature": temperature,
            },
        )
        if r.status_code >= 400:
            return {"ok": False, "error": r.text[:500], "content": "", "provider": "anthropic"}
        data = r.json()
    content = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return {"ok": True, "content": content, "provider": "anthropic", "model": model, "raw": data}


async def _openai_compatible(provider: str, model: str, messages: list[dict[str, str]], temperature: float) -> dict[str, Any]:
    if provider == "azure_openai":
        base = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        deployment = model or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        url = f"{base}/openai/deployments/{deployment}/chat/completions?api-version=2024-06-01"
        headers = {"api-key": key}
    elif provider == "hosted":
        base = (os.environ.get("HOSTED_LLM_ENDPOINT") or os.environ.get("CUSTOM_LLM_BASE_URL") or "").rstrip("/")
        key = os.environ.get("HOSTED_LLM_API_KEY") or os.environ.get("CUSTOM_LLM_API_KEY") or ""
        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {key}"} if key else {}
    else:
        base = os.environ.get("CUSTOM_LLM_BASE_URL", "").rstrip("/")
        key = os.environ.get("CUSTOM_LLM_API_KEY", "")
        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {key}"} if key else {}
    if not base:
        return {"ok": False, "error": f"{provider} base URL not set", "content": "", "provider": provider}
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, headers=headers, json={"model": model, "messages": messages, "temperature": temperature})
        if r.status_code >= 400:
            return {"ok": False, "error": r.text[:500], "content": "", "provider": provider}
        data = r.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {"ok": True, "content": content, "provider": provider, "model": model, "raw": data}


def validate_provider_config(provider: str) -> dict[str, Any]:
    """Config check without calling external networks."""
    p = (provider or "").lower()
    info = next((x for x in list_providers() if x["id"] == p), None)
    if not info:
        return {"ok": False, "provider": provider, "error": "unknown provider"}
    return {"ok": True, "provider": p, "configured": info["configured"], "label": info["label"]}

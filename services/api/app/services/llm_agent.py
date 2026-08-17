"""Ollama-powered agent reasoning loop with ClearFrame governance."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx

from app.config import OLLAMA_HOST, USE_OLLAMA
from app.services import hitl_gate
from app.services import policy as policy_svc
from app.services import tools as tools_svc

SYSTEM_PROMPT = """You are a governed enterprise AI agent operating under ISO 42001 controls.
You may only use the tools provided. Respond with JSON: {"thought": "...", "tool": "tool_name", "args": {...}} or {"thought": "...", "done": true, "answer": "..."}.
Never attempt actions outside your permitted capabilities."""


async def ollama_available() -> bool:
    if not USE_OLLAMA:
        return False
    try:
        r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def list_models() -> list[str]:
    try:
        r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


async def run_agent_loop(
    agent: dict[str, Any],
    goal: str,
    max_steps: int | None = None,
) -> dict[str, Any]:
    """Run governed LLM agent loop with pre-execution policy + HITL gating."""
    session_id = f"sess-{uuid.uuid4().hex[:8]}"
    model = agent.get("model", "llama3")
    caps = agent.get("capabilities") or ["web_search"]
    steps_limit = max_steps or int(agent.get("maxSteps", 5))
    trace: list[dict[str, Any]] = []
    audit_entries: list[dict[str, Any]] = []
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Goal: {goal}\nPermitted tools: {', '.join(caps)}"},
    ]

    available = await ollama_available()
    if not available:
        return await _fallback_plan(agent, goal, session_id)

    final_answer = ""
    for step in range(steps_limit):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{OLLAMA_HOST}/api/chat",
                    json={"model": model, "messages": messages, "stream": False, "format": "json"},
                )
                data = resp.json()
        except Exception as exc:
            trace.append({"step": step, "error": str(exc)})
            break

        content = data.get("message", {}).get("content", "{}")
        try:
            decision = json.loads(content)
        except json.JSONDecodeError:
            decision = {"thought": content, "done": True, "answer": content}

        trace.append({"step": step, "decision": decision})
        messages.append({"role": "assistant", "content": content})

        if decision.get("done"):
            final_answer = decision.get("answer", "")
            break

        tool = decision.get("tool")
        args = decision.get("args") or {}
        thought = decision.get("thought", "")

        if not tool or tool not in caps:
            messages.append({"role": "user", "content": f"Tool '{tool}' not permitted. Use only: {caps}"})
            continue

        entry = await hitl_gate.governed_execute(session_id, agent, tool, args, step, reasoning=thought)
        audit_entries.append(entry)

        if entry.get("status") == "blocked":
            reasons = entry.get("policyReasons", [])
            messages.append({"role": "user", "content": f"BLOCKED: {reasons or entry.get('status')}"})
            continue

        if entry.get("executed") and entry.get("result") is not None:
            messages.append({"role": "user", "content": f"Tool result: {entry.get('result', '')[:500]}"})

    return {
        "sessionId": session_id,
        "agentId": agent["agentId"],
        "status": "completed",
        "startedAt": time.time(),
        "auditLog": audit_entries,
        "trace": trace,
        "answer": final_answer,
        "runtime": "ollama",
    }


async def _fallback_plan(agent: dict[str, Any], goal: str, session_id: str | None = None) -> dict[str, Any]:
    from app.services.clearframe_runtime import (
        CLEARFRAME_AVAILABLE,
        build_session_plan,
    )

    session_id = session_id or f"sess-{uuid.uuid4().hex[:8]}"
    audit_entries: list[dict[str, Any]] = []
    plan = build_session_plan(agent)

    for i, (tool, kwargs, _expected) in enumerate(plan):
        thought = f"Governed step {i + 1}: {tool}"
        entry = await hitl_gate.governed_execute(session_id, agent, tool, kwargs, i, reasoning=thought)
        audit_entries.append(entry)

    runtime = "clearframe" if CLEARFRAME_AVAILABLE else "builtin"
    return {
        "sessionId": session_id,
        "agentId": agent["agentId"],
        "status": "completed",
        "startedAt": time.time(),
        "auditLog": audit_entries,
        "trace": [],
        "answer": f"Completed governed session for: {goal}",
        "runtime": runtime,
    }

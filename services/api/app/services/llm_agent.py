"""Multi-provider agent reasoning loop with ClearFrame governance.

Routes through OpenAI, Anthropic, Bedrock, Azure, custom OpenAI-compatible,
or Ollama/SLMs via ``providers``. Injects managed memory and OTEL spans.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.config import USE_OLLAMA
from app.services import hitl_gate
from app.services import memory as memory_svc
from app.services import otel as otel_svc
from app.services import providers as providers_svc
from app.services import tenancy as tenancy_svc

SYSTEM_PROMPT = """You are a governed enterprise AI agent operating under ISO 42001 controls.
You may only use the tools provided. Respond with JSON: {"thought": "...", "tool": "tool_name", "args": {...}} or {"thought": "...", "done": true, "answer": "..."}.
Never attempt actions outside your permitted capabilities.
For enterprise data questions use data_fetch or data_visualize — never invent SQL for the operator."""


async def ollama_available() -> bool:
    if not USE_OLLAMA:
        return False
    import httpx
    from app.config import OLLAMA_HOST
    try:
        r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def list_models() -> list[str]:
    import httpx
    from app.config import OLLAMA_HOST
    try:
        r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


async def run_agent_loop(
    agent: dict[str, Any],
    goal: str,
    max_steps: int | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Run governed LLM agent loop across any configured provider."""
    session_id = f"sess-{uuid.uuid4().hex[:8]}"
    provider = (agent.get("provider") or "ollama").lower()
    model = agent.get("model", "llama3")
    caps = list(agent.get("capabilities") or ["web_search"])
    # Ensure data tools available when agent is data-oriented
    for t in ("data_fetch", "data_visualize"):
        if t not in caps and any(k in (agent.get("description") or "").lower() for k in ("data", "analy", "sql", "crm")):
            caps.append(t)
    steps_limit = max_steps or int(agent.get("maxSteps", 5))
    tenant = tenant_id or tenancy_svc.DEFAULT_TENANT
    agent_id = agent.get("agentId", "")

    # Managed memory context
    mem = memory_svc.context_bundle(session_id, tenant, agent_id)
    mem_blob = ""
    if mem["longTerm"]:
        mem_blob = "\nLong-term memory:\n" + "\n".join(f"- {m['key']}: {m['value']}" for m in mem["longTerm"][:8])

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + mem_blob},
        {"role": "user", "content": f"Goal: {goal}\nPermitted tools: {', '.join(caps)}"},
    ]
    memory_svc.remember_short(session_id, f"goal:{goal}", agent_id=agent_id, role="goal")

    cfg = providers_svc.validate_provider_config(provider)
    # Fall back to plan if provider not configured (except ollama which has local fallback)
    if provider != "ollama" and not cfg.get("configured"):
        # Try ollama, else builtin plan
        if not await ollama_available():
            return await _fallback_plan(agent, goal, session_id, provider=provider)
        provider, model = "ollama", agent.get("model") or "llama3"

    if provider == "ollama" and not await ollama_available():
        return await _fallback_plan(agent, goal, session_id, provider=provider)

    trace: list[dict[str, Any]] = []
    audit_entries: list[dict[str, Any]] = []
    final_answer = ""
    t0 = time.time()

    for step in range(steps_limit):
        try:
            resp = await providers_svc.chat(provider, model, messages, temperature=0.2)
        except Exception as exc:
            trace.append({"step": step, "error": str(exc)})
            break

        if not resp.get("ok"):
            # Provider error — try fallback plan once
            if step == 0:
                return await _fallback_plan(agent, goal, session_id, provider=provider, error=resp.get("error"))
            trace.append({"step": step, "error": resp.get("error")})
            break

        content = resp.get("content") or "{}"
        try:
            # Strip markdown fences if present
            cleaned = content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:].strip()
            decision = json.loads(cleaned)
        except json.JSONDecodeError:
            decision = {"thought": content, "done": True, "answer": content}

        trace.append({"step": step, "decision": decision, "provider": provider})
        messages.append({"role": "assistant", "content": content if isinstance(content, str) else json.dumps(decision)})

        if decision.get("done"):
            final_answer = decision.get("answer", "")
            break

        tool = decision.get("tool")
        args = decision.get("args") or {}
        thought = decision.get("thought", "")

        if not tool or tool not in caps:
            messages.append({"role": "user", "content": f"Tool '{tool}' not permitted. Use only: {caps}"})
            continue

        args = {**args, "agent_id": agent_id}
        entry = await hitl_gate.governed_execute(session_id, agent, tool, args, step, reasoning=thought)
        audit_entries.append(entry)
        memory_svc.remember_short(session_id, f"{tool}:{entry.get('status')}", agent_id=agent_id, role="tool")

        if entry.get("status") == "blocked":
            reasons = entry.get("policyReasons", [])
            messages.append({"role": "user", "content": f"BLOCKED: {reasons or entry.get('status')}"})
            continue

        if entry.get("executed") and entry.get("result") is not None:
            messages.append({"role": "user", "content": f"Tool result: {entry.get('result', '')[:500]}"})

    # Persist a summary fact to long-term memory
    if final_answer:
        memory_svc.remember_long(tenant, agent_id, "last_goal_summary", final_answer[:500], importance=0.7)

    duration = (time.time() - t0) * 1000
    otel_svc.emit_span(
        "agent.loop",
        {"sessionId": session_id, "provider": provider, "model": model, "steps": len(trace)},
        duration_ms=duration,
    )
    otel_svc.emit_metric("agent.loop.duration_ms", duration, {"provider": provider})

    return {
        "sessionId": session_id,
        "agentId": agent_id,
        "status": "completed",
        "startedAt": t0,
        "auditLog": audit_entries,
        "trace": trace,
        "answer": final_answer,
        "runtime": provider,
        "memory": memory_svc.context_bundle(session_id, tenant, agent_id),
    }


async def _fallback_plan(
    agent: dict[str, Any],
    goal: str,
    session_id: str | None = None,
    provider: str = "builtin",
    error: str | None = None,
) -> dict[str, Any]:
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

    runtime = provider if provider else ("clearframe" if CLEARFRAME_AVAILABLE else "builtin")
    return {
        "sessionId": session_id,
        "agentId": agent["agentId"],
        "status": "completed",
        "startedAt": time.time(),
        "auditLog": audit_entries,
        "trace": [{"fallback": True, "error": error}] if error else [],
        "answer": f"Completed governed session for: {goal}",
        "runtime": runtime,
    }

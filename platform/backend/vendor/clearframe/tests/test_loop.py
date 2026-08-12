"""Tests for the autonomous loop, checkpoints, and the governance benchmark."""

import asyncio

import pytest

from clearframe.core.checkpoint import CheckpointStore
from clearframe.core.config import ClearFrameConfig
from clearframe.core.manifest import GoalManifest, ToolPermission
from clearframe.core.session import AgentSession
from clearframe.loop import AgentLoop, LLMTurn, ScriptedPlanner, ToolCall
from clearframe.policy import Decision, PolicyEngine, packaged_packs


def _make_session(tmp_path=None, packs=("baseline",)):
    async def web_search(query: str = "") -> str:
        return f"results:{query}"

    async def send_email(to: str = "", body: str = "") -> str:
        return f"sent:{to}"

    async def delete_database(name: str = "") -> str:
        raise AssertionError("must never run")

    manifest = GoalManifest(
        goal="Research and reply",
        permitted_tools=[
            ToolPermission(tool_name="web_search", max_calls_per_session=3),
            ToolPermission(tool_name="send_email", max_calls_per_session=1),
        ],
    )
    return AgentSession(
        ClearFrameConfig(), manifest,
        tool_registry={
            "web_search": web_search,
            "send_email": send_email,
            "delete_database": delete_database,
        },
        policy_engine=PolicyEngine.with_packs(*packs),
    )


def _run(coro):
    return asyncio.run(coro)


async def _drive(session, turns, max_steps=6):
    await session.start()
    loop = AgentLoop(session, ScriptedPlanner(turns), max_steps=max_steps)
    try:
        return await loop.run("test task")
    finally:
        await session.end()


def test_loop_completes_and_records_chunks():
    result = _run(_drive(_make_session(), [
        LLMTurn(tool_calls=[ToolCall("web_search", {"query": "nexus"})],
                thought="Gather sources."),
        LLMTurn(content="All done.", thought="Work complete."),
    ]))
    assert result.status == "completed"
    assert result.answer == "All done."
    kinds = [c.kind for c in result.chunks]
    assert "action" in kinds and "answer" in kinds


def test_loop_chunks_have_what_why_how():
    result = _run(_drive(_make_session(), [
        LLMTurn(tool_calls=[ToolCall("web_search", {"query": "x"})]),
        LLMTurn(content="done"),
    ]))
    for chunk in result.chunks:
        assert chunk.what and chunk.why and chunk.how
        assert chunk.audit_ref.startswith("audit:")


def test_loop_policy_block_is_fail_closed():
    session = _make_session()
    result = _run(_drive(session, [
        LLMTurn(tool_calls=[ToolCall("delete_database", {"name": "prod"})]),
        LLMTurn(content="done"),
    ]))
    blocked = [c for c in result.chunks if c.kind == "blocked"]
    assert blocked and "DENIED by policy" in blocked[0].why


def test_loop_hitl_pauses_fail_closed():
    result = _run(_drive(_make_session(), [
        LLMTurn(tool_calls=[ToolCall("send_email", {"to": "a@b.c", "body": "hi"})]),
    ]))
    assert result.status == "awaiting_hitl"
    hitl = [c for c in result.chunks if c.kind == "hitl"]
    assert hitl and "Aegis" in hitl[0].why or hitl[0].why


def test_checkpoints_written_and_resumable(tmp_path):
    store = CheckpointStore(tmp_path)

    async def go():
        session = _make_session()
        await session.start()
        loop = AgentLoop(session, ScriptedPlanner([
            LLMTurn(tool_calls=[ToolCall("web_search", {"query": "a"})]),
            LLMTurn(content="ok"),
        ]), checkpoints=store)
        try:
            return await loop.run("task"), loop.loop_id
        finally:
            await session.end()

    result, loop_id = _run(go())
    cp = store.latest(loop_id)
    assert cp is not None and cp.status == "completed"
    resumed = store.resume(loop_id)
    assert resumed.session_id == loop_id and len(resumed.chunks) >= 2
    assert len(store.load_all(loop_id)) >= 2


def test_iso_42001_pack_present_and_enforces():
    assert "iso-42001" in packaged_packs()
    engine = PolicyEngine.with_packs("iso-42001")
    verdict = engine.evaluate("profile_person", {}, trust_level="STANDARD")
    assert verdict.decision == Decision.REQUIRE_HITL
    verdict2 = engine.evaluate("profile_person", {}, trust_level="SANDBOX")
    assert verdict2.decision == Decision.DENY  # trust.min_level


def test_benchmark_all_controls_pass():
    from clearframe.bench import run_benchmark

    report = _run(run_benchmark())
    assert report["nexusprotocol"]["passed"] == report["nexusprotocol"]["total"]
    for name, s in report["scenarios"].items():
        assert s["passed"], f"{name}: {s['detail']}"
    # NexusProtocol must conclusively beat every tracked provider
    ours = report["nexusprotocol"]["passed"]
    for vendor, score in report["competitors_out_of_the_box"].items():
        assert score["passed"] < ours, vendor

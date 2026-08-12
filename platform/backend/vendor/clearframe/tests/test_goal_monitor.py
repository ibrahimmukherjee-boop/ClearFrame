"""Tests for the Goal Monitor alignment scoring engine."""

import pytest
from clearframe.core.manifest import GoalManifest, ToolPermission, ResourceScope
from clearframe.core.config import GoalMonitorConfig
from clearframe.monitor.goal_monitor import GoalMonitor, Disposition


@pytest.fixture
def monitor() -> GoalMonitor:
    manifest = GoalManifest(
        goal="Search for AI safety research papers and summarise them",
        permitted_tools=[
            ToolPermission(tool_name="web_search", max_calls_per_session=3),
            ToolPermission(tool_name="web_fetch", max_calls_per_session=5),
            ToolPermission(tool_name="send_email", require_approval=True),
        ],
        allow_file_write=False,
        allow_code_execution=False,
        resource_scope=ResourceScope(allowed_domains=["arxiv.org", "*.openai.com"]),
    )
    config = GoalMonitorConfig(
        alignment_threshold=0.5,
        auto_approve_threshold=0.85,
        pause_on_ambiguous=True,
        max_consecutive_low_scores=3,
    )
    return GoalMonitor(manifest, config)


def test_permitted_tool_approved(monitor: GoalMonitor) -> None:
    result = monitor.evaluate("web_search", {"query": "AI safety papers"})
    assert result.disposition in (Disposition.APPROVE, Disposition.AUTO_APPROVE)
    assert result.alignment_score > 0.0


def test_unpermitted_tool_blocked(monitor: GoalMonitor) -> None:
    result = monitor.evaluate("send_sms", {"to": "+1234", "body": "hi"})
    assert result.disposition == Disposition.BLOCK
    assert result.alignment_score == 0.0


def test_file_write_blocked(monitor: GoalMonitor) -> None:
    result = monitor.evaluate("write_file", {"path": "/tmp/x.txt", "content": "x"})
    assert result.disposition == Disposition.BLOCK


def test_code_execution_blocked(monitor: GoalMonitor) -> None:
    result = monitor.evaluate("run_shell", {"command": "ls -la"})
    assert result.disposition == Disposition.BLOCK


def test_call_limit_enforced(monitor: GoalMonitor) -> None:
    for _ in range(3):
        monitor.evaluate("web_search", {"query": "test"})
    result = monitor.evaluate("web_search", {"query": "one more"})
    assert result.disposition == Disposition.BLOCK


def test_require_approval_queued(monitor: GoalMonitor) -> None:
    result = monitor.evaluate("send_email", {"to": "x@x.com", "body": "summary"})
    assert result.disposition == Disposition.QUEUE


def test_out_of_scope_domain_penalised(monitor: GoalMonitor) -> None:
    result_in = monitor.evaluate("web_fetch", {"url": "https://arxiv.org/paper"})
    result_out = monitor.evaluate("web_fetch", {"url": "https://unrelated-site.com"})
    assert result_in.alignment_score >= result_out.alignment_score

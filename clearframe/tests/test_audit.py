"""Tests for the HMAC-chained audit log."""

import pytest
from pathlib import Path
from clearframe.core.audit import AuditLog, EventType
from clearframe.core.config import AuditConfig


@pytest.fixture
def audit(tmp_path: Path) -> AuditLog:
    cfg = AuditConfig(log_path=tmp_path / "audit.log", enabled=True)
    return AuditLog(cfg)


def test_write_and_verify(audit: AuditLog) -> None:
    audit.write(EventType.SESSION_START, "sess-001", {"goal": "test goal"})
    audit.write(EventType.TOOL_CALL_APPROVED, "sess-001", {"tool": "web_search"})
    audit.write(EventType.SESSION_END, "sess-001", {"outcome": "completed"})
    ok, errors = audit.verify()
    assert ok is True
    assert errors == []


def test_tail_returns_correct_count(audit: AuditLog) -> None:
    for i in range(10):
        audit.write(EventType.GOAL_SCORE, "sess-001", {"score": i * 0.1})
    entries = audit.tail(5)
    assert len(entries) == 5


def test_query_by_session(audit: AuditLog) -> None:
    audit.write(EventType.SESSION_START, "sess-A", {})
    audit.write(EventType.SESSION_START, "sess-B", {})
    audit.write(EventType.TOOL_CALL_APPROVED, "sess-A", {})
    results = audit.query(session_id="sess-A")
    assert all(e.get("session_id") == "sess-A" for e in results)
    assert len(results) == 2


def test_empty_log_verifies_clean(audit: AuditLog) -> None:
    ok, errors = audit.verify()
    assert ok is True
    assert errors == []

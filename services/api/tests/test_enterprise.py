"""Enterprise data-management features: CRUD, versioned history, rollback,
soft delete + restore, atomic backup/restore, and transactional integrity."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("CLEARFRAME_AUTH", "false")
os.environ.setdefault("CLEARFRAME_DATA_DIR", "/tmp/clearframe-test-enterprise")

from app.bootstrap import init_all
from app.database import get_conn
from app.services import agents as agents_svc
from app.services import backup as backup_svc
from app.services import history as history_svc
from app.services import policy as policy_svc

import pytest


def setup_module() -> None:
    init_all()


def test_transaction_rolls_back_on_error():
    marker = "tx-rollback-probe"
    with pytest.raises(RuntimeError):
        with get_conn() as conn:
            conn.execute("INSERT INTO pipeline_log (message, created_at) VALUES (?, 0)", (marker,))
            raise RuntimeError("boom")
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM pipeline_log WHERE message = ?", (marker,)).fetchone()
    assert row["c"] == 0, "write survived a failed transaction"


def test_agent_update_and_history():
    agent = agents_svc.save_agent({"name": "crud-bot", "description": "v1", "capabilities": ["web_search"]})
    aid = agent["agentId"]

    updated = agents_svc.update_agent(aid, {"description": "v2", "maxSteps": 20}, actor="tester")
    assert updated["description"] == "v2" and updated["maxSteps"] == 20

    entries = history_svc.list_history("agent", aid)
    assert [e["action"] for e in entries] == ["updated", "created"]
    assert entries[-1]["snapshot"]["description"] == "v1"
    assert entries[0]["actor"] == "tester"


def test_agent_rollback_restores_prior_version():
    agent = agents_svc.save_agent({"name": "rollback-bot", "description": "original", "capabilities": ["web_search"]})
    aid = agent["agentId"]
    agents_svc.update_agent(aid, {"description": "changed", "allowExec": True})

    rolled = agents_svc.rollback_agent(aid, 1, actor="tester")
    assert rolled["description"] == "original"
    assert rolled["allowExec"] is False

    entries = history_svc.list_history("agent", aid)
    assert entries[0]["action"] == "rollback_to_v1"
    assert len(entries) == 3, "rollback must append, never rewrite history"


def test_agent_soft_delete_and_restore():
    agent = agents_svc.save_agent({"name": "delete-bot", "capabilities": []})
    aid = agent["agentId"]

    agents_svc.revoke_agent(aid)
    revoked = agents_svc.get_agent(aid)
    assert revoked["status"] == "revoked" and revoked["trustScore"] == 0

    restored = agents_svc.restore_agent(aid, actor="tester")
    assert restored["status"] == "active"
    assert restored["trustScore"] == 100


def test_restore_requires_revoked_status():
    agent = agents_svc.save_agent({"name": "active-bot", "capabilities": []})
    assert agents_svc.restore_agent(agent["agentId"]) is None


def test_policy_update_delete_rollback():
    policy = policy_svc.create_policy("test-pol", {"tool": "email_send", "action": "require_approval"}, 60)
    pid = policy["policyId"]

    updated = policy_svc.update_policy(pid, {"priority": 90})
    assert updated["priority"] == 90

    assert policy_svc.delete_policy(pid)
    assert policy_svc.get_policy(pid)["enabled"] is False
    assert pid not in [p["policyId"] for p in policy_svc.list_policies()]

    rolled = policy_svc.rollback_policy(pid, 1)
    assert rolled["enabled"] is True and rolled["priority"] == 60
    assert pid in [p["policyId"] for p in policy_svc.list_policies()]


def test_backup_restore_roundtrip():
    agent = agents_svc.save_agent({"name": "backup-bot", "description": "keep me", "capabilities": []})
    aid = agent["agentId"]
    snapshot = backup_svc.export_all()
    assert snapshot["formatVersion"] == 1
    assert any(r["agent_id"] == aid for r in snapshot["tables"]["agents"])

    agents_svc.update_agent(aid, {"description": "damaged"})
    agents_svc.revoke_agent(aid)
    result = backup_svc.restore_all(snapshot)
    assert result["ok"]

    restored = agents_svc.get_agent(aid)
    assert restored["description"] == "keep me"
    assert restored["status"] == "active"


def test_restore_rejects_bad_format():
    with pytest.raises(ValueError):
        backup_svc.restore_all({"formatVersion": 99, "tables": {"agents": []}})
    with pytest.raises(ValueError):
        backup_svc.restore_all({"formatVersion": 1, "tables": {}})


def test_restore_never_touches_auth_tables():
    snapshot = backup_svc.export_all()
    assert "users" not in snapshot["tables"]
    assert "vault_secrets" not in snapshot["tables"]

    with get_conn() as conn:
        before = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    malicious = {"formatVersion": 1, "tables": {**snapshot["tables"], "users": []}}
    backup_svc.restore_all(malicious)
    with get_conn() as conn:
        after = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    assert after == before, "restore wrote to a non-allowlisted table"


def test_restore_is_atomic_on_bad_row():
    snapshot = backup_svc.export_all()
    agents_before = agents_svc.list_agents()
    bad = {"formatVersion": 1, "tables": {"agents": snapshot["tables"]["agents"] + ["not-a-dict"]}}
    with pytest.raises(ValueError):
        backup_svc.restore_all(bad)
    assert agents_svc.list_agents() == agents_before, "failed restore must leave state untouched"

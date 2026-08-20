"""Regression tests: suspended-agent pipeline recovery and login lockout."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("CLEARFRAME_AUTH", "false")
os.environ.setdefault("CLEARFRAME_DATA_DIR", "/tmp/clearframe-test-regressions")

from app.database import init_db
from app.services import auth as auth_svc
from app.services import agents as agents_svc
from app.services import governance as gov_svc
from app.services import pipeline as pipeline_svc
from app.services import policy as policy_svc
from app.services import tools as tools_svc

import pytest


def setup_module() -> None:
    init_db()
    auth_svc.init_auth_db()
    tools_svc.init_tools_db()
    gov_svc.init_governance_db()
    policy_svc.init_policy_db()
    agents_svc.seed_defaults()


def test_pipeline_recovers_from_suspended_current_agent():
    """A suspended current agent must not break the pipeline — and must not be
    silently reactivated. The pipeline provisions a fresh active agent."""
    agent = agents_svc.save_agent({"name": "to-suspend", "description": "x", "capabilities": ["web_search"]})
    agents_svc.suspend_agent(agent["agentId"])

    result = pipeline_svc.run_full_pipeline()
    assert result["ok"], result.get("message")

    current = agents_svc.get_current_agent()
    assert current["status"] == "active"
    assert current["agentId"] != agent["agentId"], "suspended agent must not be reactivated"
    suspended = next(a for a in agents_svc.list_agents() if a["agentId"] == agent["agentId"])
    assert suspended["status"] == "suspended"


def test_login_lockout_after_repeated_failures():
    email = "admin@erasys.local"
    for _ in range(auth_svc.LOGIN_MAX_ATTEMPTS):
        assert auth_svc.login(email, "wrong-password") is None
    with pytest.raises(auth_svc.LoginLocked) as exc:
        auth_svc.login(email, "wrong-password")
    assert exc.value.retry_after > 0


def test_lockout_clears_on_successful_login():
    email = "operator@erasys.local"
    for _ in range(auth_svc.LOGIN_MAX_ATTEMPTS - 1):
        assert auth_svc.login(email, "wrong-password") is None
    result = auth_svc.login(email, "operator")
    assert result and result["user"]["email"] == email
    # Counter reset: previous failures no longer count toward the limit.
    assert auth_svc.login(email, "wrong-password") is None
    assert auth_svc.login(email, "operator")

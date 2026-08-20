"""Single entry point for initializing every database table.

Used by both application startup (app.main lifespan) and the test suites, so
schema initialization can never drift between the two.
"""
from __future__ import annotations

from app.database import init_db
from app.services import action_audit as action_audit_svc
from app.services import agents as agents_svc
from app.services import auth as auth_svc
from app.services import governance as governance_svc
from app.services import policy as policy_svc
from app.services import policy_hub as policy_hub_svc
from app.services import sonar as sonar_svc
from app.services import tools as tools_svc
from app.services import workflows as workflows_svc


def init_all(seed: bool = True) -> None:
    init_db()
    auth_svc.init_auth_db()
    tools_svc.init_tools_db()
    governance_svc.init_governance_db()
    policy_svc.init_policy_db()
    workflows_svc.init_workflows_db()
    policy_hub_svc.init_policy_hub_db()
    action_audit_svc.init_action_audit_db()
    if seed:
        agents_svc.seed_defaults()
        sonar_svc.seed_defaults()

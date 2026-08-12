"""Compliance evidence export for ISO 42001 / EU AI Act audits."""
from __future__ import annotations

import json
import time
from typing import Any

from app.services import audit as audit_svc
from app.services import eu_ai_act as eu_svc
from app.services import governance as gov_svc
from app.services import sonar as sonar_svc
from app.services import agents as agents_svc
from app.services import policy as policy_svc
from app.services import aegis as aegis_svc


def build_evidence_pack() -> dict[str, Any]:
    gov_svc.collect_evidence()
    return {
        "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "standard": "ISO 42001:2023",
        "framework": "Erasys ClearFrame Stack",
        "governance": gov_svc.get_dashboard(),
        "auditChain": audit_svc.verify_chain(),
        "agents": agents_svc.list_agents(),
        "policies": {
            "governance": gov_svc.list_policies(),
            "runtime": policy_svc.list_policies(),
        },
        "euAiAct": eu_svc.assess_portfolio(),
        "threats": {"events": sonar_svc.list_threats(), "score": sonar_svc.threat_score()},
        "hitlQueue": aegis_svc.list_tool_calls(),
    }


def export_json() -> str:
    return json.dumps(build_evidence_pack(), indent=2, default=str)

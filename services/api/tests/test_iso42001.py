"""ISO/IEC 42001:2023 compliance verification tests."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("CLEARFRAME_AUTH", "false")
os.environ.setdefault("CLEARFRAME_DATA_DIR", "/tmp/clearframe-test-compliance")

from app.database import init_db
from app.services import auth as auth_svc
from app.services import governance as gov_svc
from app.services import policy as policy_svc
from app.services import tools as tools_svc
from app.services import agents as agents_svc
from app.services import safepulse as safepulse_svc
from app.services import trust as trust_svc
from app.services import pipeline as pipeline_svc
from app.services import compliance as compliance_svc
from app.services import audit as audit_svc


def setup():
    init_db()
    auth_svc.init_auth_db()
    tools_svc.init_tools_db()
    gov_svc.init_governance_db()
    policy_svc.init_policy_db()
    agents_svc.seed_defaults()


def test_iso42001_all_controls_assessed():
    setup()
    result = compliance_svc.run_iso42001_assessment()
    assert result["standard"] == "ISO/IEC 42001:2023"
    assert result["totalControls"] >= 18
    assert "complianceScore" in result
    assert "controls" in result
    for ctrl in result["controls"]:
        assert "controlId" in ctrl
        assert "passed" in ctrl
        assert "evidence" in ctrl
    print(f"  PASS: {result['passedControls']}/{result['totalControls']} controls assessed, score={result['complianceScore']}%")


def test_iso42001_audit_chain_integrity():
    setup()
    audit_svc.write_event("test", "sess-test", {"action": "compliance_check"})
    chain = audit_svc.verify_chain()
    assert chain["valid"] is True
    print(f"  PASS: Audit HMAC chain valid ({chain['count']} entries)")


def test_iso42001_hitl_policy_enforced():
    setup()
    pol = policy_svc.evaluate("email_send", {"to": "x@y.com"}, {"trustScore": 100, "agentStatus": "active"})
    assert pol["disposition"] in ("require_approval", "allow", "deny")
    blocked = policy_svc.evaluate("file_delete", {"path": "/x"}, {"trustScore": 100, "agentStatus": "active"})
    assert blocked["disposition"] == "deny"
    print("  PASS: Runtime policy engine blocks file_delete, governs email_send")


def test_iso42001_full_pipeline_produces_evidence():
    os.environ["CLEARFRAME_DATA_DIR"] = f"/tmp/clearframe-test-pipeline-{os.getpid()}"
    setup()
    pipeline_svc.run_full_pipeline()
    gov_svc.collect_evidence()
    result = compliance_svc.run_iso42001_assessment()
    assert result["complianceScore"] >= 70, f"Score too low after pipeline: {result['complianceScore']}"
    audit_ctrl = next(c for c in result["controls"] if c["controlId"] == "9.2")
    assert audit_ctrl["passed"] is True, f"Audit control failed: {audit_ctrl['detail']}"
    print(f"  PASS: Post-pipeline ISO score={result['complianceScore']}%, audit control passed")


def test_iso42001_governance_policies_exist():
    setup()
    policies = gov_svc.list_policies()
    assert len(policies) >= 4
    titles = {p["title"] for p in policies}
    assert "Human Oversight Policy" in titles
    assert "Data Handling Policy" in titles
    print(f"  PASS: {len(policies)} governance policies seeded")


def test_production_blocks_default_secrets():
    os.environ["CLEARFRAME_ENV"] = "production"
    from app.production import validate_production_config
    errors = validate_production_config()
    assert len(errors) > 0, "Production must reject default secrets"
    os.environ.pop("CLEARFRAME_ENV", None)
    print(f"  PASS: Production rejects {len(errors)} insecure defaults")


if __name__ == "__main__":
    tests = [
        test_iso42001_all_controls_assessed,
        test_iso42001_audit_chain_integrity,
        test_iso42001_hitl_policy_enforced,
        test_iso42001_governance_policies_exist,
        test_iso42001_full_pipeline_produces_evidence,
        test_production_blocks_default_secrets,
    ]
    passed = failed = 0
    print("\n=== ISO/IEC 42001:2023 Compliance Test Suite ===\n")
    for t in tests:
        try:
            print(f"[{t.__name__}]")
            t()
            passed += 1
        except Exception as exc:
            print(f"  FAIL: {exc}")
            failed += 1
    print(f"\n=== Results: {passed} passed, {failed} failed ===\n")
    sys.exit(1 if failed else 0)

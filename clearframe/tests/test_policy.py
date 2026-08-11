"""Tests for the ClearFrame Policy Engine and packaged policy packs."""

import pytest

from clearframe.policy import Decision, PolicyEngine, packaged_packs


def test_packaged_packs_present():
    packs = packaged_packs()
    for expected in ("baseline", "eu-ai-act", "nist-ai-rmf", "owasp-llm"):
        assert expected in packs


def test_baseline_denies_destructive_tools():
    engine = PolicyEngine.baseline()
    verdict = engine.evaluate("delete_database", {})
    assert verdict.decision == Decision.DENY


def test_baseline_requires_hitl_for_email():
    engine = PolicyEngine.baseline()
    verdict = engine.evaluate("send_email", {"to": "a@b.com", "body": "hi"})
    assert verdict.decision == Decision.REQUIRE_HITL


def test_baseline_allows_normal_tool():
    engine = PolicyEngine.baseline()
    verdict = engine.evaluate("web_search", {"query": "AI safety"})
    assert verdict.decision == Decision.ALLOW


def test_secret_pattern_blocked():
    engine = PolicyEngine.baseline()
    verdict = engine.evaluate("http_get", {"body": "password: hunter2secret"})
    assert verdict.decision == Decision.DENY
    assert "password-in-args" in verdict.rule


def test_call_budget_enforced():
    engine = PolicyEngine([{
        "name": "tiny", "rules": {"limits": {"max_calls_per_tool": 2}},
    }])
    assert engine.evaluate("t", {}).decision == Decision.ALLOW
    assert engine.evaluate("t", {}).decision == Decision.ALLOW
    assert engine.evaluate("t", {}).decision == Decision.DENY


def test_domain_scoping():
    engine = PolicyEngine([{
        "name": "domains", "rules": {"domains": {"allow": ["*.example.com"]}},
    }])
    ok = engine.evaluate("web_fetch", {"url": "https://api.example.com/x"})
    assert ok.decision == Decision.ALLOW
    bad = engine.evaluate("web_fetch", {"url": "https://evil.io/x"})
    assert bad.decision == Decision.DENY


def test_trust_level_gate():
    engine = PolicyEngine([{
        "name": "trust", "rules": {"trust": {"min_level": "ELEVATED"}},
    }])
    low = engine.evaluate("t", {}, trust_level="STANDARD")
    assert low.decision == Decision.DENY
    high = engine.evaluate("t", {}, trust_level="CRITICAL")
    assert high.decision == Decision.ALLOW


def test_eu_ai_act_blocks_prohibited_practices():
    engine = PolicyEngine.with_packs("eu-ai-act")
    verdict = engine.evaluate("social_scoring_citizens", {})
    assert verdict.decision == Decision.DENY


def test_owasp_blocks_api_key_leak():
    engine = PolicyEngine.with_packs("owasp-llm")
    verdict = engine.evaluate("http_get", {"q": "api_key=sk_live_0123456789abcdef01"})
    assert verdict.decision == Decision.DENY

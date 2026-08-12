"""API stress and security tests."""
from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.request

import pytest

API = os.environ.get("STRESS_API_URL", "http://127.0.0.1:8080")
RESULTS: list[str] = []


@pytest.fixture(scope="module")
def token() -> str:
    """Log in once so pytest-collected tests that need auth get a token."""
    return login()


def req(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if hasattr(e, "read") else "{}"
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {}


def login() -> str:
    code, data = req("POST", "/api/auth/login", {"email": "admin@erasys.local", "password": "admin"})
    assert code == 200, f"Login failed: {code} {data}"
    return data["accessToken"]


def test_auth_blocks_unauthenticated():
    code, _ = req("GET", "/api/state")
    assert code == 401, f"Expected 401 without token, got {code}"
    RESULTS.append("PASS: Unauthenticated requests blocked (401)")


def test_auth_allows_health():
    code, data = req("GET", "/api/health")
    assert code == 200
    assert data.get("status") == "ok"
    RESULTS.append("PASS: Health endpoint public")


def test_concurrent_state_reads(token: str, n: int = 50):
    def one():
        code, _ = req("GET", "/api/state", token=token)
        return code

    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        codes = list(ex.map(lambda _: one(), range(n)))
    elapsed = time.time() - start
    ok = sum(1 for c in codes if c == 200)
    assert ok == n, f"Only {ok}/{n} succeeded"
    rps = n / elapsed
    RESULTS.append(f"PASS: {n} concurrent /api/state in {elapsed:.2f}s ({rps:.0f} req/s)")


def test_concurrent_compliance_checks(token: str, n: int = 30):
    def one():
        code, data = req("GET", "/api/compliance/iso42001", token=token)
        return code, data.get("complianceScore", 0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as ex:
        results = list(ex.map(lambda _: one(), range(n)))
    ok = sum(1 for c, _ in results if c == 200)
    scores = [s for _, s in results if s > 0]
    assert ok == n
    RESULTS.append(f"PASS: {n} concurrent ISO assessments, scores {min(scores)}-{max(scores)}%")


def test_pipeline_under_load(token: str, n: int = 5):
    successes = 0
    for i in range(n):
        code, data = req("POST", "/api/pipeline/run", token=token)
        if code == 200 and data.get("ok"):
            successes += 1
    assert successes >= n - 1, f"Pipeline failed {n - successes}/{n} times"
    RESULTS.append(f"PASS: Pipeline {successes}/{n} runs succeeded")


def test_audit_chain_after_stress(token: str):
    code, data = req("GET", "/api/audit/verify", token=token)
    assert code == 200
    assert data.get("valid") is True, f"Audit chain broken: {data}"
    RESULTS.append(f"PASS: Audit chain intact ({data.get('count')} entries)")


def test_iso_compliance_score(token: str):
    code, data = req("GET", "/api/compliance/production", token=token)
    assert code == 200
    score = data["iso42001"]["score"]
    assert score >= 75, f"ISO score {score}% below production threshold (75%)"
    RESULTS.append(f"PASS: Production readiness score={score}%, level={data['iso42001']['level']}")


def test_policy_blocks_dangerous_tool(token: str):
    code, data = req("POST", "/api/tools/execute", {"tool": "file_delete", "args": {"path": "/etc/passwd"}}, token=token)
    assert code == 200
    assert data.get("blocked") is True or data.get("ok") is False
    RESULTS.append("PASS: Policy engine blocks file_delete")


def test_security_headers():
    r = urllib.request.Request(f"{API}/api/health")
    with urllib.request.urlopen(r, timeout=5) as resp:
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
    RESULTS.append("PASS: Security headers present")


if __name__ == "__main__":
    print(f"\n=== Stress & Security Test Suite → {API} ===\n")
    try:
        token = login()
        print("Logged in as admin\n")
        test_auth_blocks_unauthenticated()
        test_auth_allows_health()
        test_security_headers()
        test_concurrent_state_reads(token, 50)
        test_concurrent_compliance_checks(token, 30)
        test_policy_blocks_dangerous_tool(token)
        test_pipeline_under_load(token, 3)
        test_audit_chain_after_stress(token)
        test_iso_compliance_score(token)
    except Exception as exc:
        print(f"\nFAIL: {exc}\n")
        sys.exit(1)

    print()
    for r in RESULTS:
        print(r)
    print(f"\n=== All {len(RESULTS)} stress tests passed ===\n")

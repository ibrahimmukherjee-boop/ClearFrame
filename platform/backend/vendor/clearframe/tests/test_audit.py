"""
Tests for AuditLog — covers Fix 2 (no hardcoded HMAC secret)
and general HMAC chain integrity + tamper detection.
"""
import json
import os
import pytest
from pathlib import Path

from clearframe.core.audit  import AuditLog, EventType
from clearframe.core.config import AuditConfig


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_audit(tmp_path: Path, secret_hex: str | None = None) -> AuditLog:
    log_path = tmp_path / "audit.log"
    config   = AuditConfig(log_path=log_path)
    if secret_hex:
        os.environ[config.hmac_secret_env] = secret_hex
    else:
        os.environ.pop(config.hmac_secret_env, None)
    return AuditLog(config)


# ── Fix 2: secret generation ──────────────────────────────────────────────────

class TestSecretResolution:
    def test_env_var_secret_used_when_set(self, tmp_path):
        secret = os.urandom(32).hex()
        audit  = make_audit(tmp_path, secret_hex=secret)
        assert audit._secret == bytes.fromhex(secret)

    def test_disk_secret_created_when_no_env(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config  = AuditConfig(log_path=tmp_path / "audit.log")
        monkeypatch.delenv(config.hmac_secret_env, raising=False)

        audit1 = AuditLog(config)
        secret_path = tmp_path / "audit-secret"
        assert secret_path.exists(), "audit-secret file must be created"
        assert len(audit1._secret) == 32

    def test_disk_secret_reused_across_instances(self, tmp_path, monkeypatch):
        config = AuditConfig(log_path=tmp_path / "audit.log")
        monkeypatch.delenv(config.hmac_secret_env, raising=False)

        audit1 = AuditLog(config)
        audit2 = AuditLog(config)
        assert audit1._secret == audit2._secret, "Same secret must be loaded on second init"

    def test_disk_secret_chmod_600(self, tmp_path, monkeypatch):
        config = AuditConfig(log_path=tmp_path / "audit.log")
        monkeypatch.delenv(config.hmac_secret_env, raising=False)
        AuditLog(config)

        secret_path = tmp_path / "audit-secret"
        mode = oct(secret_path.stat().st_mode)[-3:]
        assert mode == "600", f"Expected chmod 600, got {mode}"

    def test_no_hardcoded_default_secret(self, tmp_path, monkeypatch):
        """The old hardcoded default must not exist in the source."""
        import clearframe.core.audit as audit_module
        source = Path(audit_module.__file__).read_text()
        assert "clearframe-default-audit-secret" not in source, (
            "Hardcoded default secret found in audit.py — Fix 2 not applied."
        )


# ── Chain integrity ────────────────────────────────────────────────────────────

class TestChainIntegrity:
    def test_empty_log_is_valid(self, tmp_path):
        config = AuditConfig(log_path=tmp_path / "audit.log")
        audit  = AuditLog(config)
        ok, errors = audit.verify_chain()
        assert ok
        assert errors == []

    def test_single_entry_chain_valid(self, tmp_path):
        audit = make_audit(tmp_path)
        audit.write(EventType.SESSION_START, "s1", {"goal": "test"})
        ok, errors = audit.verify_chain()
        assert ok, errors

    def test_multi_entry_chain_valid(self, tmp_path):
        audit = make_audit(tmp_path)
        audit.write(EventType.SESSION_START,      "s1", {"goal": "research"})
        audit.write(EventType.TOOL_CALL_APPROVED, "s1", {"tool": "web_search"})
        audit.write(EventType.TOOL_CALL_COMPLETED,"s1", {"tool": "web_search", "result": "ok"})
        audit.write(EventType.GOAL_SCORE,         "s1", {"score": 0.92})
        audit.write(EventType.SESSION_END,        "s1", {"outcome": "completed"})
        ok, errors = audit.verify_chain()
        assert ok, errors

    def test_multiple_sessions_in_one_log(self, tmp_path):
        audit = make_audit(tmp_path)
        for session_id in ["s1", "s2", "s3"]:
            audit.write(EventType.SESSION_START, session_id, {"goal": f"goal-{session_id}"})
            audit.write(EventType.SESSION_END,   session_id, {"outcome": "completed"})
        ok, errors = audit.verify_chain()
        assert ok, errors


# ── Tamper detection ──────────────────────────────────────────────────────────

class TestTamperDetection:
    def test_modified_event_type_detected(self, tmp_path):
        audit    = make_audit(tmp_path)
        log_path = tmp_path / "audit.log"
        audit.write(EventType.SESSION_START, "s1", {"goal": "test"})
        raw = log_path.read_text()
        log_path.write_text(raw.replace("session_start", "session_end"))
        ok, errors = audit.verify_chain()
        assert not ok
        assert len(errors) >= 1

    def test_modified_goal_detected(self, tmp_path):
        audit    = make_audit(tmp_path)
        log_path = tmp_path / "audit.log"
        audit.write(EventType.SESSION_START, "s1", {"goal": "legitimate goal"})
        raw = log_path.read_text()
        log_path.write_text(raw.replace("legitimate goal", "INJECTED GOAL"))
        ok, errors = audit.verify_chain()
        assert not ok

    def test_deleted_entry_detected(self, tmp_path):
        audit    = make_audit(tmp_path)
        log_path = tmp_path / "audit.log"
        audit.write(EventType.SESSION_START,      "s1", {"goal": "test"})
        audit.write(EventType.TOOL_CALL_APPROVED, "s1", {"tool": "web_search"})
        audit.write(EventType.SESSION_END,        "s1", {"outcome": "completed"})
        lines = log_path.read_text().splitlines()
        # Remove middle entry
        lines.pop(1)
        log_path.write_text("\n".join(lines) + "\n")
        ok, errors = audit.verify_chain()
        assert not ok

    def test_appended_fake_entry_detected(self, tmp_path):
        audit    = make_audit(tmp_path)
        log_path = tmp_path / "audit.log"
        audit.write(EventType.SESSION_START, "s1", {"goal": "test"})
        # Append a forged entry with a fake HMAC
        fake = json.dumps({
            "entry": {
                "ts": 9999999999.0,
                "event": "session_end",
                "session_id": "s1",
                "data": {"outcome": "completed"},
            },
            "hmac": "a" * 64,  # forged HMAC
        })
        with open(log_path, "a") as f:
            f.write(fake + "\n")
        ok, errors = audit.verify_chain()
        assert not ok

    def test_hmac_field_zeroed_detected(self, tmp_path):
        audit    = make_audit(tmp_path)
        log_path = tmp_path / "audit.log"
        audit.write(EventType.SESSION_START, "s1", {"goal": "test"})
        raw = log_path.read_text()
        # Zero out the HMAC value
        data = json.loads(raw.strip())
        data["hmac"] = "0" * 64
        log_path.write_text(json.dumps(data) + "\n")
        ok, errors = audit.verify_chain()
        assert not ok


# ── Disabled audit log ────────────────────────────────────────────────────────

class TestDisabledAudit:
    def test_disabled_audit_writes_nothing(self, tmp_path):
        log_path = tmp_path / "audit.log"
        config   = AuditConfig(log_path=log_path, enabled=False)
        audit    = AuditLog(config)
        audit.write(EventType.SESSION_START, "s1", {"goal": "test"})
        assert not log_path.exists(), "Disabled audit must not create a file"

    def test_disabled_audit_verify_returns_valid(self, tmp_path):
        log_path = tmp_path / "audit.log"
        config   = AuditConfig(log_path=log_path, enabled=False)
        audit    = AuditLog(config)
        ok, errors = audit.verify_chain()
        assert ok
        assert errors == []

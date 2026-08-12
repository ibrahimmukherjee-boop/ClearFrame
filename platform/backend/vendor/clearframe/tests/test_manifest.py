"""
Tests for GoalManifest — covers Fix 4 (schema_version) and Fix 5 (lock enforcement).
"""
import pytest

from clearframe.core.errors   import ManifestLockError
from clearframe.core.manifest import GoalManifest, ResourceScope, ToolPermission


# ── Fix 4: schema_version ─────────────────────────────────────────────────────

class TestSchemaVersion:
    def test_default_schema_version(self):
        m = GoalManifest(goal="Summarise documents")
        assert m.schema_version == "1.0"

    def test_custom_schema_version(self):
        m = GoalManifest(goal="test", schema_version="2.0")
        assert m.schema_version == "2.0"

    def test_schema_version_serialised_in_json(self):
        m = GoalManifest(goal="test")
        data = m.model_dump()
        assert "schema_version" in data
        assert data["schema_version"] == "1.0"

    def test_schema_version_first_field(self):
        """schema_version must be the first key so audit replays can identify format early."""
        m    = GoalManifest(goal="test")
        keys = list(m.model_dump().keys())
        assert keys[0] == "schema_version"


# ── Fix 5: lock enforcement ───────────────────────────────────────────────────

class TestManifestLock:
    def test_mutable_before_lock(self):
        m = GoalManifest(goal="test", allow_file_write=False)
        m.allow_file_write = True   # must NOT raise
        assert m.allow_file_write is True

    def test_goal_mutable_before_lock(self):
        m = GoalManifest(goal="original")
        m.goal = "updated"
        assert m.goal == "updated"

    def test_immutable_after_lock_bool_field(self):
        m = GoalManifest(goal="test", allow_file_write=False)
        m.lock()
        with pytest.raises(ManifestLockError, match="allow_file_write"):
            m.allow_file_write = True

    def test_immutable_after_lock_goal(self):
        m = GoalManifest(goal="original")
        m.lock()
        with pytest.raises(ManifestLockError, match="goal"):
            m.goal = "tampered"

    def test_immutable_after_lock_max_steps(self):
        m = GoalManifest(goal="test", max_steps=50)
        m.lock()
        with pytest.raises(ManifestLockError):
            m.max_steps = 9999

    def test_immutable_after_lock_permitted_tools(self):
        perm = ToolPermission(tool_name="web_search")
        m    = GoalManifest(goal="test", permitted_tools=[perm])
        m.lock()
        with pytest.raises(ManifestLockError):
            m.permitted_tools = []

    def test_lock_is_idempotent(self):
        """Calling lock() twice must not raise."""
        m = GoalManifest(goal="test")
        m.lock()
        m.lock()   # second lock — no error

    def test_private_fields_not_blocked(self):
        """Internal _locked attribute must be settable even when locked."""
        m = GoalManifest(goal="test")
        m.lock()
        # __setattr__ must allow _ prefixed names so pydantic internals work
        object.__setattr__(m, "_locked", True)   # must not raise

    def test_locked_flag_not_in_serialisation(self):
        """_locked is internal state and must not appear in model_dump()."""
        m = GoalManifest(goal="test")
        m.lock()
        data = m.model_dump()
        assert "_locked" not in data

    def test_locked_manifest_still_readable(self):
        """Fields remain readable after lock — only writes are blocked."""
        m = GoalManifest(goal="test", max_steps=42, allow_file_write=True)
        m.lock()
        assert m.goal            == "test"
        assert m.max_steps       == 42
        assert m.allow_file_write is True


# ── Integration: tool permission helpers ─────────────────────────────────────

class TestToolPermissions:
    def test_is_tool_permitted_true(self):
        m = GoalManifest(
            goal="test",
            permitted_tools=[ToolPermission(tool_name="web_search")],
        )
        assert m.is_tool_permitted("web_search") is True

    def test_is_tool_permitted_false(self):
        m = GoalManifest(goal="test")
        assert m.is_tool_permitted("write_file") is False

    def test_get_tool_permission_returns_correct(self):
        perm = ToolPermission(tool_name="db_query", max_calls_per_session=10)
        m    = GoalManifest(goal="test", permitted_tools=[perm])
        result = m.get_tool_permission("db_query")
        assert result is not None
        assert result.max_calls_per_session == 10

    def test_get_tool_permission_missing_returns_none(self):
        m = GoalManifest(goal="test")
        assert m.get_tool_permission("nonexistent") is None

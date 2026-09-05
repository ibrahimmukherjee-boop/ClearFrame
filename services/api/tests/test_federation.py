"""Enterprise federation, tenancy, lineage, migrations, probes."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("CLEARFRAME_AUTH", "false")
os.environ.setdefault("CLEARFRAME_DATA_DIR", "/tmp/clearframe-test-federation")

from app.bootstrap import init_all
from app.services import federation as federation_svc
from app.services import idempotency as idem_svc
from app.services import lineage as lineage_svc
from app.services import migrations as migrations_svc
from app.services import tenancy as tenancy_svc

import pytest


def setup_module() -> None:
    init_all()


def test_migrations_applied():
    applied = {m["version"] for m in migrations_svc.applied()}
    assert "001_tenants" in applied
    assert "002_federation" in applied
    assert "003_lineage" in applied
    assert "004_idempotency" in applied


def test_default_tenant_and_catalogs():
    tenants = tenancy_svc.list_tenants()
    assert any(t["tenantId"] == tenancy_svc.DEFAULT_TENANT for t in tenants)
    cats = federation_svc.list_catalogs()
    names = {c["name"] for c in cats}
    assert {"crm", "warehouse", "clearframe"} <= names


def test_federated_select_with_column_masking():
    result = federation_svc.execute_query("SELECT * FROM crm.customers LIMIT 10", actor="tester")
    assert result["ok"] and result["rowCount"] >= 1
    emails = [r.get("email", "") for r in result["rows"]]
    assert all("***" in e for e in emails), emails
    lin = lineage_svc.get(result["queryId"])
    assert lin and lin["entityType"] == "federated_query"


def test_federated_join_across_catalogs():
    result = federation_svc.execute_query(
        "SELECT * FROM crm.customers JOIN warehouse.orders LIMIT 20",
        actor="tester",
    )
    assert result["ok"]
    assert set(result["catalogs"]) == {"crm", "warehouse"}
    assert result["rowCount"] >= 1


def test_federation_rejects_mutations():
    with pytest.raises(ValueError):
        federation_svc.execute_query("DELETE FROM crm.customers")
    with pytest.raises(ValueError):
        federation_svc.execute_query("SELECT * FROM unknown.table")


def test_idempotency_replay():
    idem_svc.store("k1", "POST", "/api/federation/query", 200, {"ok": True, "n": 1})
    cached = idem_svc.lookup("k1", "POST", "/api/federation/query")
    assert cached and cached["body"]["n"] == 1


def test_create_tenant():
    t = tenancy_svc.create_tenant("Acme Regulated", {"maxAgents": 10})
    assert t["tenantId"].startswith("ten-")
    assert tenancy_svc.get_tenant(t["tenantId"])["name"] == "Acme Regulated"

# ClearFrame — TrustRegistry Integration Changes

Five targeted changes to wire TrustRegistry into ClearFrame.
Apply them in order.

## Files Changed

### 1. `clearframe/pyproject.toml` ← REPLACE
- Added `slowapi>=0.1.9` to core dependencies (rate limiting)
- Added `[project.optional-dependencies] trust` pointing to the
  private TrustRegistry GitHub repo
- Added `[tool.hatch.build.targets.wheel] packages = ["clearframe"]`
  (fixes the double-nesting build issue)

Install the trust stack:
```bash
# Requires a GitHub token or SSH key with read access to TrustRegistry repo
pip install clearframe[trust]

# Or with a Personal Access Token (PAT):
pip install "clearframe[trust]" \
  --extra-index-url https://<your-PAT>@github.com/ibrahimmukherjee-boop/TrustRegistry
```

### 2. `clearframe/clearframe/__init__.py` ← REPLACE
- Optional TrustGate / TrustGateError import
- If `trust-registry` is not installed, ClearFrame works standalone unchanged

### 3. `clearframe/clearframe/core/manifest.py` ← REPLACE
- Added `__all__ = ["ToolPermission", "ResourceScope", "GoalManifest"]`
- All other logic unchanged (schema_version + lock guard already confirmed live)

### 4. `clearframe/clearframe/core/audit.py` ← REPLACE
- Added `__all__ = ["EventType", "AuditLog"]`
- Added SQLite backend (`AuditConfig(backend="sqlite")`)
- Added two new EventTypes: `TRUST_CERT_VERIFIED`, `TRUST_CERT_REJECTED`
- Added `audit.query(session_id=..., event=...)` method (SQLite only)
- Flat-file behaviour unchanged — existing deployments unaffected

### 5. `clearframe/clearframe/ops/server.py` ← PATCH (see rate_limiting_patch.py)
- Add slowapi rate limiting (see `ops/rate_limiting_patch.py` for exact lines)
- 200/minute global limit; 60/minute on control endpoints

## Testing the Integration

```python
# After: pip install clearframe[trust]
from clearframe import TrustGate            # only available with [trust]
from clearframe import GoalManifest         # always available

from trust_registry import TrustRegistry, IssuanceRequest, TrustLevel, LicenseTier
from trust_registry import AgentIdentity, CapabilityScope

registry = TrustRegistry()
cert     = registry.issue_certificate(IssuanceRequest(
    agent=AgentIdentity(
        name="MyAgent", version="1.0.0",
        owner="Erasys", public_key_pem=agent_pub_key,
    ),
    requested_trust_level = TrustLevel.STANDARD,
    license_tier          = LicenseTier.ENTERPRISE,
    capability_scope      = CapabilityScope(can_make_http_requests=True),
    validity_days         = 1,
))

gate = TrustGate(registry, min_trust_level=TrustLevel.STANDARD)
gate.verify(cert.certificate_id)  # raises TrustGateError if invalid

manifest = GoalManifest(
    goal            = "Research AI safety papers",
    allow_file_write = False,
)
# ... AgentSession as normal
```

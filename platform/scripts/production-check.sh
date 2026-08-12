#!/usr/bin/env bash
# Pre-production deployment checklist for Erasys ClearFrame Stack
set -euo pipefail

API="${CHECK_URL:-http://127.0.0.1:8080}"
EMAIL="${ADMIN_EMAIL:-admin@erasys.local}"
PASSWORD="${ADMIN_PASSWORD:-admin}"

echo "=== Erasys ClearFrame Production Readiness Check ==="
echo "Target: $API"
echo ""

fail=0

check() {
  local name="$1"
  local result="$2"
  if [ "$result" = "ok" ]; then
    echo "  [PASS] $name"
  else
    echo "  [FAIL] $name — $result"
    fail=$((fail + 1))
  fi
}

# Health
code=$(curl -s -o /dev/null -w "%{http_code}" "$API/api/health")
[ "$code" = "200" ] && check "Health endpoint" ok || check "Health endpoint" "HTTP $code"

# Auth required
code=$(curl -s -o /dev/null -w "%{http_code}" "$API/api/state")
[ "$code" = "401" ] && check "Auth enforcement" ok || check "Auth enforcement" "HTTP $code (expected 401)"

# Login
TOKEN=$(curl -s -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('accessToken',''))" 2>/dev/null || echo "")
[ -n "$TOKEN" ] && check "Admin login" ok || check "Admin login" "failed"

# ISO 42001
if [ -n "$TOKEN" ]; then
  SCORE=$(curl -s "$API/api/compliance/iso42001" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('complianceScore',0))" 2>/dev/null || echo "0")
  [ "$SCORE" -ge 75 ] && check "ISO 42001 score >= 75%" "$SCORE%" || check "ISO 42001 score >= 75%" "score=$SCORE%"

  PROD=$(curl -s "$API/api/compliance/production" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d.get('productionReady') else 'no')" 2>/dev/null || echo "no")
  [ "$PROD" = "ok" ] && check "Production readiness" ok || check "Production readiness" "not ready"

  AUDIT=$(curl -s "$API/api/audit/verify" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print('ok' if json.load(sys.stdin).get('valid') else 'broken')" 2>/dev/null || echo "broken")
  [ "$AUDIT" = "ok" ] && check "Audit chain integrity" ok || check "Audit chain integrity" "$AUDIT"
fi

# Security headers
HSTS=$(curl -sI "$API/api/health" | grep -i "x-content-type-options" || true)
[ -n "$HSTS" ] && check "Security headers" ok || check "Security headers" "missing"

# Production env (if set)
if [ "${CLEARFRAME_ENV:-}" = "production" ]; then
  cd "$(dirname "$0")/../backend"
  python3 -c "from app.production import validate_production_config; e=validate_production_config(); exit(0 if not e else 1)" 2>/dev/null \
    && check "Production secrets" ok || check "Production secrets" "default/insecure values detected"
fi

echo ""
if [ "$fail" -eq 0 ]; then
  echo "=== ALL CHECKS PASSED — ready for production deploy ==="
  exit 0
else
  echo "=== $fail CHECK(S) FAILED — resolve before production deploy ==="
  exit 1
fi

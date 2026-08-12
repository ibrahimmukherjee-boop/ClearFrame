#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "==> Erasys ClearFrame Stack — local startup"

if [ ! -d backend/.venv ]; then
  echo "==> Creating Python virtualenv..."
  python3 -m venv backend/.venv
fi

backend/.venv/bin/pip install -q -r backend/requirements.txt

if [ ! -d node_modules ]; then
  echo "==> Installing frontend dependencies..."
  npm install
fi

echo ""
echo "  API:      http://127.0.0.1:8080/api/health"
echo "  AgentOps: http://127.0.0.1:7477/health"
echo "  UI:       http://127.0.0.1:5173"
echo ""
echo "==> Starting API + UI..."
npm run dev:all

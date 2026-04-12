#!/usr/bin/env bash
# smoke-test.sh — end-to-end test against the GCP Nomad platform-api
#
# Usage:
#   ./smoke-test.sh [API_BASE_URL]
#
# Defaults to http://34.143.174.106:8080 if no URL is given.

set -euo pipefail

API="${1:-http://34.143.174.106:8080}"

echo "=== Smoke test: $API ==="
echo ""

echo "[1/3] Health check..."
curl -fsS "$API/health" | python3 -m json.tool
echo ""

echo "[2/3] Create session..."
SESSION=$(curl -fsS -X POST "$API/sessions" \
  -H "Content-Type: application/json" \
  -d '{"runtime":"microvm"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['session_id'])")
echo "session: $SESSION"
echo ""

echo "[3/3] Execute Python in real Firecracker VM..."
curl -fsS -X POST "$API/execute" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION\",\"tool\":\"python_run\",\"input\":{\"code\":\"print('hello from real VM on GCP!')\\nprint(2**10)\"}}" \
  | python3 -m json.tool

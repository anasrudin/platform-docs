#!/usr/bin/env bash
# smoke-test.sh — end-to-end test against the GCP Nomad platform-api
#
# Tests: health → session → execute (real VM) → Consul UI → Jaeger UI
#
# Usage:
#   ./smoke-test.sh [API_BASE_URL]
#
# Defaults to http://34.143.174.106:8080 if no URL is given.

set -euo pipefail

API="${1:-http://34.143.174.106:8080}"
VM_HOST="${API%%:*}"
VM_HOST="${VM_HOST#http://}"

CONSUL_URL="http://${VM_HOST}:8500"
JAEGER_URL="http://${VM_HOST}:16686"
MINIO_URL="http://${VM_HOST}:9001"
NOMAD_URL="http://${VM_HOST}:4646"

pass() { echo "  [OK] $*"; }
fail() { echo "  [FAIL] $*"; exit 1; }

echo "=== Smoke test: $API ==="
echo ""

# ── 1. API health ─────────────────────────────────────────────────────────────
echo "[1/5] API health check..."
HEALTH=$(curl -fsS "$API/health")
echo "$HEALTH" | python3 -m json.tool
pass "API is up"
echo ""

# ── 2. Create session ─────────────────────────────────────────────────────────
echo "[2/5] Create session (microvm runtime)..."
SESSION=$(curl -fsS -X POST "$API/sessions" \
  -H "Content-Type: application/json" \
  -d '{"runtime":"microvm"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['session_id'])")
echo "  session_id: $SESSION"
pass "Session created"
echo ""

# ── 3. Execute Python in Firecracker VM ───────────────────────────────────────
echo "[3/5] Execute Python in real Firecracker VM..."
RESULT=$(curl -fsS -X POST "$API/execute" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION\",\"tool\":\"python_run\",\"input\":{\"code\":\"import sys; print('hello from real VM on GCP!'); print('python', sys.version.split()[0]); print(2**10)\"}}")
echo "$RESULT" | python3 -m json.tool
OUTPUT=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('output',''))")
if echo "$OUTPUT" | grep -q "hello from real VM"; then
  pass "Code ran in Firecracker VM"
else
  fail "Unexpected output: $OUTPUT"
fi
echo ""

# ── 4. Consul health ──────────────────────────────────────────────────────────
echo "[4/5] Consul status..."
if curl -fsS "${CONSUL_URL}/v1/status/leader" >/dev/null 2>&1; then
  LEADER=$(curl -fsS "${CONSUL_URL}/v1/status/leader")
  pass "Consul leader: $LEADER"
  echo "  UI: ${CONSUL_URL}/ui"
else
  echo "  [WARN] Consul not reachable at ${CONSUL_URL} — may need --skip-firewall=false"
fi
echo ""

# ── 5. Jaeger health ──────────────────────────────────────────────────────────
echo "[5/5] Jaeger status..."
if curl -fsS "${JAEGER_URL}/" >/dev/null 2>&1; then
  pass "Jaeger UI is reachable"
  echo "  UI: ${JAEGER_URL}"
else
  echo "  [WARN] Jaeger not reachable at ${JAEGER_URL} — may need firewall open or OTEL_ENABLED=true"
fi
echo ""

echo "=== Smoke test complete ==="
echo ""
echo "  Dashboards:"
echo "    Nomad:   ${NOMAD_URL}"
echo "    Consul:  ${CONSUL_URL}/ui"
echo "    Jaeger:  ${JAEGER_URL}"
echo "    MinIO:   ${MINIO_URL}  (minioadmin / minioadmin)"

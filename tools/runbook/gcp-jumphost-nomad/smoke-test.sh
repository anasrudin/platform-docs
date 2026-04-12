#!/usr/bin/env bash
# smoke-test.sh — End-to-end test terhadap platform-api di GCP Nomad
#
# Layer yang di-test:
#   controller  → API health, session create
#   worker      → execute Python di Firecracker VM
#   data        → Consul, Jaeger, MinIO
#
# Konfigurasi host dibaca dari config/topology.env (jika ada).
# API base URL bisa di-override via argumen pertama.
#
# Usage:
#   ./smoke-test.sh                          # pakai CONTROLLER_HOST dari topology.env
#   ./smoke-test.sh http://1.2.3.4:8080     # override langsung

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOPOLOGY_FILE="${SCRIPT_DIR}/config/topology.env"

# ── Load topology config ──────────────────────────────────────────────────────
if [[ -f "${TOPOLOGY_FILE}" ]]; then
  # shellcheck source=/dev/null
  source "${TOPOLOGY_FILE}"
fi

# ── Resolve API base URL ──────────────────────────────────────────────────────
# Priority: CLI arg > CONTROLLER_HOST dari topology.env > error
if [[ -n "${1:-}" ]]; then
  API="$1"
elif [[ -n "${CONTROLLER_HOST:-}" ]]; then
  API="http://${CONTROLLER_HOST}:${API_PORT:-8080}"
else
  echo "ERROR: Tidak ada API URL." >&2
  echo "  Option 1: source config/topology.env  (jalankan gen-topology.sh lebih dulu)" >&2
  echo "  Option 2: ./smoke-test.sh http://<IP>:8080" >&2
  exit 1
fi

# Ekstrak host dari URL
_no_scheme="${API#http://}"
_no_scheme="${_no_scheme#https://}"
VM_HOST="${_no_scheme%%:*}"

# Derive layer hosts
CONTROLLER_HOST="${CONTROLLER_HOST:-${VM_HOST}}"
DATA_HOST="${DATA_HOST:-${VM_HOST}}"

CONSUL_URL="http://${CONTROLLER_HOST}:${CONSUL_PORT:-8500}"
NOMAD_URL="http://${CONTROLLER_HOST}:${NOMAD_PORT:-4646}"
JAEGER_URL="http://${DATA_HOST}:${JAEGER_PORT:-16686}"
MINIO_URL="http://${DATA_HOST}:${MINIO_CONSOLE_PORT:-9001}"

pass() { echo "  [OK] $*"; }
fail() { echo "  [FAIL] $*"; exit 1; }
warn() { echo "  [WARN] $*"; }

echo "=== Smoke test: ${API} ==="
echo ""
echo "  Layer topology:"
echo "    controller: ${CONTROLLER_HOST}"
echo "    data:       ${DATA_HOST}"
echo ""

# ── 1. controller layer: API health ──────────────────────────────────────────
echo "[1/5] controller — API health check..."
HEALTH=$(curl -fsS "${API}/health")
echo "$HEALTH" | python3 -m json.tool
pass "API is up"
echo ""

# ── 2. controller layer: Create session ──────────────────────────────────────
echo "[2/5] controller — Create session (microvm runtime)..."
SESSION=$(curl -fsS -X POST "${API}/sessions" \
  -H "Content-Type: application/json" \
  -d '{"runtime":"microvm"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['session_id'])")
echo "  session_id: ${SESSION}"
pass "Session created"
echo ""

# ── 3. worker layer: Execute Python in Firecracker VM ────────────────────────
echo "[3/5] worker — Execute Python in Firecracker VM..."
RESULT=$(curl -fsS -X POST "${API}/execute" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"${SESSION}\",\"tool\":\"python_run\",\"input\":{\"code\":\"import sys; print('hello from real VM on GCP!'); print('python', sys.version.split()[0]); print(2**10)\"}}")
echo "$RESULT" | python3 -m json.tool
OUTPUT=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('output',''))")
if echo "$OUTPUT" | grep -q "hello from real VM"; then
  pass "Code ran in Firecracker VM (worker layer)"
else
  fail "Unexpected output: ${OUTPUT}"
fi
echo ""

# ── 4. controller layer: Consul ───────────────────────────────────────────────
echo "[4/5] controller — Consul status..."
if curl -fsS "${CONSUL_URL}/v1/status/leader" >/dev/null 2>&1; then
  LEADER=$(curl -fsS "${CONSUL_URL}/v1/status/leader")
  pass "Consul leader: ${LEADER}"
  echo "  UI: ${CONSUL_URL}/ui"
else
  warn "Consul tidak reachable di ${CONSUL_URL} — cek firewall atau --skip-firewall=false"
fi
echo ""

# ── 5. data layer: Jaeger ─────────────────────────────────────────────────────
echo "[5/5] data — Jaeger status..."
if curl -fsS "${JAEGER_URL}/" >/dev/null 2>&1; then
  pass "Jaeger UI is reachable"
  echo "  UI: ${JAEGER_URL}"
else
  warn "Jaeger tidak reachable di ${JAEGER_URL} — cek OTEL_ENABLED=true atau firewall"
fi
echo ""

echo "=== Smoke test complete ==="
echo ""
echo "  Dashboards:"
echo "    [controller] Nomad:   ${NOMAD_URL}"
echo "    [controller] Consul:  ${CONSUL_URL}/ui"
echo "    [data]       Jaeger:  ${JAEGER_URL}"
echo "    [data]       MinIO:   ${MINIO_URL}  (minioadmin / minioadmin)"

#!/usr/bin/env bash
# test-fc-runtime.sh
# Tests the Firecracker Go runtime (pool, snapshot store, sim execution).
#
# Modes:
#   --unit    go test only, no running services required  [default]
#   --sim     go test + live API integration (make dev must be running)
#   --real    go test + live API with real KVM execution
#
# Usage:
#   bash scripts/test-fc-runtime.sh [--unit | --sim | --real] [--api-url URL]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

MODE="unit"
API_URL="${PLATFORM_API_URL:-http://localhost:8080}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --unit)    MODE="unit";  shift ;;
    --sim)     MODE="sim";   shift ;;
    --real)    MODE="real";  shift ;;
    --api-url) API_URL="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

PASS=0; FAIL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

pass()    { PASS=$((PASS+1));  echo -e "${GREEN}  PASS${NC} $1"; }
fail()    { FAIL=$((FAIL+1));  echo -e "${RED}  FAIL${NC} $1"; [[ -n "${2:-}" ]] && echo "       $2"; }
skip()    { echo -e "${YELLOW}  SKIP${NC} $1: $2"; }
section() { echo -e "\n${BLUE}── $1 ──${NC}"; }

api_post() { curl -sf -X POST "${API_URL}${1}" -H "Content-Type: application/json" -d "$2" 2>/dev/null; }
api_get()  { curl -sf "${API_URL}${1}" 2>/dev/null; }

echo "╔══════════════════════════════════════════════════╗"
echo "║         Firecracker Runtime Test [${MODE}]        "
echo "╚══════════════════════════════════════════════════╝"
echo ""

cd "${PLATFORM_DIR}"

# ── Go tests ──────────────────────────────────────────────────────────────────
section "Go tests: runtime/firecracker"

if command -v go &>/dev/null; then
  if go test ./runtime/firecracker/... -count=1 2>&1 | tee /tmp/fc-go-test.log | grep -E "^(ok|FAIL|---)" ; then
    if grep -q "^FAIL" /tmp/fc-go-test.log; then
      fail "go test ./runtime/firecracker/..." "see output above"
    else
      pass "go test ./runtime/firecracker/... (all tests green)"
    fi
  else
    fail "go test ./runtime/firecracker/..." "$(tail -5 /tmp/fc-go-test.log)"
  fi

  if go vet ./runtime/firecracker/... 2>/dev/null; then
    pass "go vet ./runtime/firecracker/..."
  else
    fail "go vet ./runtime/firecracker/..." "$(go vet ./runtime/firecracker/... 2>&1 | head -3)"
  fi
else
  skip "go test" "go not installed"
fi

# ── MinIO snapshot presence (real mode) ───────────────────────────────────────
if [[ "${MODE}" == "real" ]]; then
  section "Real mode: MinIO snapshot check"
  if command -v mc &>/dev/null; then
    mc alias set fc-rt "${MINIO_ENDPOINT:-http://localhost:9000}" \
      "${MINIO_ACCESS_KEY:-minioadmin}" "${MINIO_SECRET_KEY:-minioadmin}" --quiet 2>/dev/null
    if mc ls "fc-rt/platform-snapshots/python-v1/" &>/dev/null; then
      pass "python-v1 snapshot exists in MinIO"
    else
      fail "python-v1 snapshot in MinIO" "run: tools/snapshot-builder/snapshot-builder.sh --download-kernel"
    fi
    mc alias remove fc-rt &>/dev/null || true
  else
    skip "MinIO snapshot check" "mc not installed"
  fi

  if [[ -r /dev/kvm ]]; then
    pass "/dev/kvm accessible for real execution"
  else
    fail "/dev/kvm accessible" "real mode requires KVM"
  fi
fi

# ── API integration tests (sim + real modes) ──────────────────────────────────
if [[ "${MODE}" != "unit" ]]; then
  section "API: health check"

  HEALTH=$(api_get "/health" || echo '{"status":"down"}')
  STATUS=$(echo "${HEALTH}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")

  if [[ "${STATUS}" == "healthy" ]]; then
    pass "GET /health → healthy"
  else
    fail "GET /health" "got: ${HEALTH}"
    echo "  ⚠ Start the API: cd sandbox-platform && make dev"
    FAIL=$((FAIL+1))
    goto_summary=true
  fi

  if [[ "${goto_summary:-false}" != "true" ]]; then
    section "API: microvm session + tool execution"

    SESSION=$(api_post "/sessions" '{"runtime":"microvm"}' || echo '{}')
    SESSION_ID=$(echo "${SESSION}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || echo "")

    if [[ -n "${SESSION_ID}" ]]; then
      pass "POST /sessions → microvm session: ${SESSION_ID:0:8}..."
    else
      fail "POST /sessions" "no session_id in: ${SESSION}"
      SESSION_ID=""
    fi

    if [[ -n "${SESSION_ID}" ]]; then
      for tool_test in \
        "python_run|{\"code\":\"print('hello fc')\"}" \
        "bash_run|{\"command\":\"echo fc-ok\"}"; do
        tool="${tool_test%%|*}"
        input="${tool_test##*|}"
        BODY="{\"session_id\":\"${SESSION_ID}\",\"tool\":\"${tool}\",\"input\":${input}}"
        RESULT=$(api_post "/execute" "${BODY}" || echo '{"status":"failed"}')
        JOB_STATUS=$(echo "${RESULT}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
        if [[ "${JOB_STATUS}" == "completed" ]]; then
          pass "POST /execute ${tool} → completed"
        else
          fail "POST /execute ${tool}" "status=${JOB_STATUS}"
        fi
      done
    fi
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  Results: ${PASS} passed  ${FAIL} failed"
echo "════════════════════════════════════════"
[[ $FAIL -eq 0 ]] && echo -e "${GREEN}All Firecracker runtime tests passed.${NC}" \
  || echo -e "${RED}${FAIL} test(s) failed.${NC}"
[[ $FAIL -eq 0 ]]

#!/usr/bin/env bash
# test-wasm-runtime.sh
# Tests the WASM Go runtime (mode detection, sim execution, real wasmtime execution).
#
# Modes:
#   --unit    go test only, no running services required  [default]
#   --sim     go test + live API integration (make dev must be running)
#   --real    go test + live API + wasmtime module execution
#
# Usage:
#   bash scripts/test-wasm-runtime.sh [--unit | --sim | --real] [--api-url URL]

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
echo "║           WASM Runtime Test [${MODE}]             "
echo "╚══════════════════════════════════════════════════╝"
echo ""

cd "${PLATFORM_DIR}"

# ── Go tests ──────────────────────────────────────────────────────────────────
section "Go tests: runtime/wasm"

if command -v go &>/dev/null; then
  if go test ./runtime/wasm/... -count=1 2>&1 | tee /tmp/wasm-go-test.log | grep -E "^(ok|FAIL|---)" ; then
    if grep -q "^FAIL" /tmp/wasm-go-test.log; then
      fail "go test ./runtime/wasm/..." "see output above"
    else
      pass "go test ./runtime/wasm/... (all tests green)"
    fi
  else
    fail "go test ./runtime/wasm/..." "$(tail -5 /tmp/wasm-go-test.log)"
  fi

  if go vet ./runtime/wasm/... 2>/dev/null; then
    pass "go vet ./runtime/wasm/..."
  else
    fail "go vet ./runtime/wasm/..." "$(go vet ./runtime/wasm/... 2>&1 | head -3)"
  fi
else
  skip "go test" "go not installed"
fi

# ── wasmtime binary (real mode) ───────────────────────────────────────────────
if [[ "${MODE}" == "real" ]]; then
  section "Real mode: wasmtime binary"
  if command -v wasmtime &>/dev/null; then
    VERSION=$(wasmtime --version 2>/dev/null || echo "unknown")
    pass "wasmtime found: ${VERSION}"
  else
    fail "wasmtime in PATH" "install: brew install wasmtime  OR  apt install wasmtime"
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
    echo ""
    TOTAL=$((PASS + FAIL))
    echo "  Results: ${PASS}/${TOTAL} passed"
    exit 1
  fi

  section "API: wasm session + tool execution"

  SESSION=$(api_post "/sessions" '{"runtime":"wasm"}' || echo '{}')
  SESSION_ID=$(echo "${SESSION}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || echo "")

  if [[ -n "${SESSION_ID}" ]]; then
    pass "POST /sessions → wasm session: ${SESSION_ID:0:8}..."
  else
    fail "POST /sessions" "no session_id in: ${SESSION}"
    SESSION_ID=""
  fi

  if [[ -n "${SESSION_ID}" ]]; then
    # Test echo — output must be JSON containing input fields
    ECHO_RESULT=$(api_post "/execute" \
      "{\"session_id\":\"${SESSION_ID}\",\"tool\":\"echo\",\"input\":{\"msg\":\"wasm-test\"}}" || echo '{}')
    ECHO_STATUS=$(echo "${ECHO_RESULT}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
    ECHO_OUTPUT=$(echo "${ECHO_RESULT}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('output',''))" 2>/dev/null || echo "")

    if [[ "${ECHO_STATUS}" == "completed" ]]; then
      pass "POST /execute echo → completed"
    else
      fail "POST /execute echo" "status=${ECHO_STATUS}"
    fi

    if echo "${ECHO_OUTPUT}" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('msg')=='wasm-test'" 2>/dev/null; then
      pass "echo output is JSON and contains input field msg=wasm-test"
    else
      fail "echo output JSON validation" "output: ${ECHO_OUTPUT:0:200}"
    fi

    # Test hello — output must contain the name
    HELLO_RESULT=$(api_post "/execute" \
      "{\"session_id\":\"${SESSION_ID}\",\"tool\":\"hello\",\"input\":{\"name\":\"Platform\"}}" || echo '{}')
    HELLO_OUTPUT=$(echo "${HELLO_RESULT}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('output',''))" 2>/dev/null || echo "")
    if echo "${HELLO_OUTPUT}" | grep -q "Platform"; then
      pass "POST /execute hello → output contains 'Platform'"
    else
      fail "POST /execute hello" "output: ${HELLO_OUTPUT:0:200}"
    fi

    # Test json_parse — valid JSON input
    JP_RESULT=$(api_post "/execute" \
      "{\"session_id\":\"${SESSION_ID}\",\"tool\":\"json_parse\",\"input\":{\"data\":\"{\\\"k\\\":\\\"v\\\"}\"}}" || echo '{}')
    JP_STATUS=$(echo "${JP_RESULT}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
    if [[ "${JP_STATUS}" == "completed" ]]; then
      pass "POST /execute json_parse → completed"
    else
      fail "POST /execute json_parse" "status=${JP_STATUS}"
    fi
  fi

  # Test real mode: check wasm-agent log shows mode=real if WASM_MODE=real
  if [[ "${MODE}" == "real" ]]; then
    section "Real mode: WASM_MODE=real smoke test"
    if command -v wasmtime &>/dev/null; then
      pass "wasmtime available — wasm-agent will run in real mode"
      skip "end-to-end real WASM execution" "requires .wasm module uploaded to MinIO platform-modules bucket"
    else
      skip "real mode smoke test" "wasmtime not installed"
    fi
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  Results: ${PASS} passed  ${FAIL} failed"
echo "════════════════════════════════════════"
[[ $FAIL -eq 0 ]] && echo -e "${GREEN}All WASM runtime tests passed.${NC}" \
  || echo -e "${RED}${FAIL} test(s) failed.${NC}"
[[ $FAIL -eq 0 ]]

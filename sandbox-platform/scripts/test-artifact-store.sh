#!/usr/bin/env bash
# test-artifact-store.sh
# Tests the artifact store (upload, download, URL generation).
#
# Modes:
#   --unit    go test only, no running services required  [default]
#   --sim     go test + live API upload/download (make dev must be running)
#
# Usage:
#   bash scripts/test-artifact-store.sh [--unit | --sim] [--api-url URL]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

MODE="unit"
API_URL="${PLATFORM_API_URL:-http://localhost:8080}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --unit)    MODE="unit"; shift ;;
    --sim)     MODE="sim";  shift ;;
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

echo "╔══════════════════════════════════════════════════╗"
echo "║          Artifact Store Test [${MODE}]            "
echo "╚══════════════════════════════════════════════════╝"
echo ""

cd "${PLATFORM_DIR}"

# ── Go tests ──────────────────────────────────────────────────────────────────
section "Go tests: internal/artifacts"

if command -v go &>/dev/null; then
  if go test ./internal/artifacts/... -count=1 2>&1 | tee /tmp/art-go-test.log | grep -E "^(ok|FAIL|---)" ; then
    if grep -q "^FAIL" /tmp/art-go-test.log; then
      fail "go test ./internal/artifacts/..." "see output above"
    else
      pass "go test ./internal/artifacts/... (all tests green)"
    fi
  else
    fail "go test ./internal/artifacts/..." "$(tail -5 /tmp/art-go-test.log)"
  fi

  if go vet ./internal/artifacts/... 2>/dev/null; then
    pass "go vet ./internal/artifacts/..."
  else
    fail "go vet ./internal/artifacts/..." "$(go vet ./internal/artifacts/... 2>&1 | head -3)"
  fi
else
  skip "go test" "go not installed"
fi

# ── API integration tests (sim mode) ──────────────────────────────────────────
if [[ "${MODE}" == "sim" ]]; then
  section "API: health check"

  HEALTH=$(curl -sf "${API_URL}/health" 2>/dev/null || echo '{"status":"down"}')
  STATUS=$(echo "${HEALTH}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")

  if [[ "${STATUS}" == "healthy" ]]; then
    pass "GET /health → healthy"
  else
    fail "GET /health" "got: ${HEALTH}"
    echo "  ⚠ Start the API: cd sandbox-platform && make dev"
    echo ""
    echo "  Results: ${PASS} passed  ${FAIL} failed"
    exit 1
  fi

  section "API: artifact upload + download"

  # Create a wasm session to get session_id
  SESSION=$(api_post "/sessions" '{"runtime":"wasm"}' || echo '{}')
  SESSION_ID=$(echo "${SESSION}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || echo "")

  if [[ -z "${SESSION_ID}" ]]; then
    fail "POST /sessions" "no session_id in: ${SESSION}"
    echo ""
    echo "  Results: ${PASS} passed  ${FAIL} failed"
    exit 1
  fi
  pass "POST /sessions → session: ${SESSION_ID:0:8}..."

  # Upload a text artifact
  TMP_ARTIFACT=$(mktemp /tmp/test-artifact-XXXXXX.txt)
  echo "artifact content: platform test $(date +%s)" > "${TMP_ARTIFACT}"
  EXPECTED_CONTENT=$(cat "${TMP_ARTIFACT}")

  UPLOAD=$(curl -sf -X POST \
    -F "session_id=${SESSION_ID}" \
    -F "name=test-upload.txt" \
    -F "file=@${TMP_ARTIFACT}" \
    "${API_URL}/artifacts" 2>/dev/null || echo '{}')
  rm -f "${TMP_ARTIFACT}"

  ARTIFACT_ID=$(echo "${UPLOAD}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('artifact_id',''))" 2>/dev/null || echo "")
  ARTIFACT_KEY=$(echo "${UPLOAD}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('key',''))" 2>/dev/null || echo "")
  ARTIFACT_URL=$(echo "${UPLOAD}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('url',''))" 2>/dev/null || echo "")
  ARTIFACT_SIZE=$(echo "${UPLOAD}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('size',0))" 2>/dev/null || echo "0")

  if [[ -n "${ARTIFACT_ID}" ]]; then
    pass "POST /artifacts → artifact_id: ${ARTIFACT_ID:0:8}..."
  else
    fail "POST /artifacts" "response: ${UPLOAD}"
    echo ""
    echo "  Results: ${PASS} passed  ${FAIL} failed"
    exit 1
  fi

  # Validate response fields
  if [[ -n "${ARTIFACT_KEY}" ]]; then
    pass "POST /artifacts → key present: ${ARTIFACT_KEY}"
  else
    fail "POST /artifacts" "missing key in response"
  fi

  if [[ -n "${ARTIFACT_URL}" ]]; then
    pass "POST /artifacts → URL present: ${ARTIFACT_URL}"
  else
    fail "POST /artifacts" "missing url in response"
  fi

  if [[ "${ARTIFACT_SIZE}" -gt 0 ]]; then
    pass "POST /artifacts → size=${ARTIFACT_SIZE} bytes"
  else
    fail "POST /artifacts" "size is 0"
  fi

  # Download and verify content
  if [[ -n "${ARTIFACT_KEY}" ]]; then
    DL_TMP=$(mktemp /tmp/art-dl-XXXXXX)
    if curl -sf "${API_URL}/artifacts/${ARTIFACT_KEY}" -o "${DL_TMP}" 2>/dev/null; then
      DL_CONTENT=$(cat "${DL_TMP}")
      if [[ "${DL_CONTENT}" == "${EXPECTED_CONTENT}" ]]; then
        pass "GET /artifacts/{key} → content matches uploaded data"
      else
        fail "GET /artifacts/{key} content mismatch" \
          "expected: ${EXPECTED_CONTENT}  got: ${DL_CONTENT}"
      fi
    else
      fail "GET /artifacts/${ARTIFACT_KEY}" "download request failed"
    fi
    rm -f "${DL_TMP}"
  fi

  # Upload a binary artifact
  BINARY_TMP=$(mktemp /tmp/test-bin-XXXXXX.bin)
  dd if=/dev/urandom of="${BINARY_TMP}" bs=1024 count=2 2>/dev/null
  BINARY_SIZE=$(wc -c < "${BINARY_TMP}")

  BIN_UPLOAD=$(curl -sf -X POST \
    -F "session_id=${SESSION_ID}" \
    -F "name=test.bin" \
    -F "file=@${BINARY_TMP}" \
    "${API_URL}/artifacts" 2>/dev/null || echo '{}')
  rm -f "${BINARY_TMP}"

  BIN_ID=$(echo "${BIN_UPLOAD}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('artifact_id',''))" 2>/dev/null || echo "")
  BIN_KEY=$(echo "${BIN_UPLOAD}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('key',''))" 2>/dev/null || echo "")

  if [[ -n "${BIN_ID}" && -n "${BIN_KEY}" ]]; then
    pass "POST /artifacts binary upload → ${BIN_ID:0:8}..."

    # Download binary and check size matches
    BIN_DL=$(mktemp /tmp/art-bin-dl-XXXXXX)
    if curl -sf "${API_URL}/artifacts/${BIN_KEY}" -o "${BIN_DL}" 2>/dev/null; then
      DL_SIZE=$(wc -c < "${BIN_DL}")
      if [[ "${DL_SIZE}" -eq "${BINARY_SIZE}" ]]; then
        pass "Binary download size matches (${DL_SIZE} bytes)"
      else
        fail "Binary download size" "uploaded=${BINARY_SIZE}, downloaded=${DL_SIZE}"
      fi
    else
      fail "GET /artifacts/${BIN_KEY} binary" "download failed"
    fi
    rm -f "${BIN_DL}"
  else
    fail "POST /artifacts binary upload" "response: ${BIN_UPLOAD}"
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  Results: ${PASS} passed  ${FAIL} failed"
echo "════════════════════════════════════════"
[[ $FAIL -eq 0 ]] && echo -e "${GREEN}All artifact store tests passed.${NC}" \
  || echo -e "${RED}${FAIL} test(s) failed.${NC}"
[[ $FAIL -eq 0 ]]

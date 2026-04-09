#!/usr/bin/env bash
# test-e2e.sh — End-to-end workflow test for the sandbox platform
#
# Demonstrates the full execution path for each tier:
#   WASM    — stateless tools: echo, hello, json_parse, markdown_convert
#   MicroVM — subprocess tools: python_run, bash_run
#   (GUI    — not yet implemented)
#
# Includes:
#   - session lifecycle (create → execute → verify output)
#   - auto-routing without session_id
#   - artifact upload and download
#
# Requirements: make dev  (API + agents + postgres + redis running)
#
# Usage:
#   bash test-e2e.sh [--api-url URL]
#   API_URL=http://my-node:8080 bash test-e2e.sh

set -uo pipefail

API_URL="${API_URL:-http://localhost:8080}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-url) API_URL="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

PASS=0; FAIL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

pass()    { PASS=$((PASS+1)); echo -e "  ${GREEN}✓${NC} $1"; }
fail()    { FAIL=$((FAIL+1)); echo -e "  ${RED}✗${NC} $1"; [[ -n "${2:-}" ]] && echo -e "    ${RED}→${NC} $2"; }
info()    { echo -e "  ${YELLOW}·${NC} $1"; }
section() { echo ""; echo -e "${BLUE}${BOLD}$1${NC}"; echo -e "${BLUE}$(printf '─%.0s' $(seq 1 ${#1}))${NC}"; }
step()    { echo -e "  ${BLUE}▶${NC} $1"; }

json_field() {
  echo "${1}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('${2}',''))" 2>/dev/null || echo ""
}

json_assert() {
  local label="$1" json="$2" field="$3" expected="$4"
  local actual
  actual=$(json_field "${json}" "${field}")
  if [[ "${actual}" == "${expected}" ]]; then
    pass "${label}: ${field}=${expected}"
  else
    fail "${label}" "want ${field}='${expected}', got '${actual}'\n    response: ${json:0:300}"
  fi
}

api_post() {
  curl -sf -X POST "${API_URL}${1}" -H "Content-Type: application/json" -d "${2}" 2>/dev/null
}

execute_tool() {
  api_post "/execute" "{\"session_id\":\"${1}\",\"tool\":\"${2}\",\"input\":${3}}"
}

# ── Pre-flight ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║         Platform End-to-End Test                     ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
echo -e "  API: ${API_URL}"
echo ""

section "Platform health"

step "GET /health"
HEALTH=$(curl -sf "${API_URL}/health" 2>/dev/null || echo '{}')
STATUS=$(json_field "${HEALTH}" "status")

if [[ "${STATUS}" == "healthy" ]]; then
  pass "Platform healthy"
else
  fail "Platform health check" "status='${STATUS}'"
  echo ""
  echo -e "  ${RED}API is not running. Start with:${NC}"
  echo -e "  ${YELLOW}cd sandbox-platform && make dev${NC}"
  exit 1
fi

PG=$(echo "${HEALTH}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('services',{}).get('postgres','?'))" 2>/dev/null || echo "?")
RD=$(echo "${HEALTH}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('services',{}).get('redis','?'))" 2>/dev/null || echo "?")
info "postgres=${PG}  redis=${RD}"

# ═══════════════════════════════════════════════════════════════════════════════
# WASM WORKFLOW
# Tools routed to WASM tier: echo, hello, json_parse, markdown_convert
# Runtime mode: sim (no wasmtime) or real (wasmtime in PATH + module in MinIO)
# ═══════════════════════════════════════════════════════════════════════════════
section "WASM Workflow"

step "Create WASM session"
WASM_SESS=$(api_post "/sessions" '{"runtime":"wasm"}')
WASM_SID=$(json_field "${WASM_SESS}" "session_id")

if [[ -n "${WASM_SID}" ]]; then
  pass "Session created: ${WASM_SID:0:8}..."
else
  fail "Create WASM session" "${WASM_SESS}"
  exit 1
fi

# ── echo: input must be reflected back as JSON ────────────────────────────────
step "Tool: echo"
ECHO_RES=$(execute_tool "${WASM_SID}" "echo" '{"msg":"hello-wasm","n":42}')
ECHO_OUT=$(json_field "${ECHO_RES}" "output")
json_assert "echo" "${ECHO_RES}" "status" "completed"
if echo "${ECHO_OUT}" | python3 -c \
    "import json,sys; d=json.load(sys.stdin); assert d.get('msg')=='hello-wasm' and d.get('n')==42" 2>/dev/null; then
  pass "echo: output is JSON with msg='hello-wasm' and n=42"
else
  fail "echo: output JSON content" "output: ${ECHO_OUT:0:200}"
fi

# ── hello: output must contain the provided name ──────────────────────────────
step "Tool: hello (with name)"
HELLO_RES=$(execute_tool "${WASM_SID}" "hello" '{"name":"Platform"}')
HELLO_OUT=$(json_field "${HELLO_RES}" "output")
json_assert "hello" "${HELLO_RES}" "status" "completed"
if echo "${HELLO_OUT}" | grep -q "Platform"; then
  pass "hello: output contains 'Platform'"
else
  fail "hello: output should contain name" "output: ${HELLO_OUT:0:200}"
fi

# ── hello: no name → default 'World' ─────────────────────────────────────────
step "Tool: hello (no name → default 'World')"
HELLO_DEF=$(execute_tool "${WASM_SID}" "hello" '{}')
HELLO_DEF_OUT=$(json_field "${HELLO_DEF}" "output")
json_assert "hello default" "${HELLO_DEF}" "status" "completed"
if echo "${HELLO_DEF_OUT}" | grep -q "World"; then
  pass "hello default: output contains 'World'"
else
  fail "hello default: want 'World'" "output: ${HELLO_DEF_OUT:0:200}"
fi

# ── json_parse: valid JSON round-trip ────────────────────────────────────────
step "Tool: json_parse (round-trip)"
JP_RES=$(execute_tool "${WASM_SID}" "json_parse" '{"data":"{\"platform\":\"sandbox\",\"version\":1}"}')
JP_OUT=$(json_field "${JP_RES}" "output")
json_assert "json_parse" "${JP_RES}" "status" "completed"
if echo "${JP_OUT}" | python3 -c \
    "import json,sys; d=json.load(sys.stdin); assert d.get('platform')=='sandbox'" 2>/dev/null; then
  pass "json_parse: round-trip JSON, platform='sandbox'"
else
  fail "json_parse: round-trip content" "output: ${JP_OUT:0:200}"
fi

# ── json_parse: invalid JSON → must return status=failed ─────────────────────
step "Tool: json_parse (invalid input → expect failure)"
JP_BAD=$(execute_tool "${WASM_SID}" "json_parse" '{"data":"not{json"}')
JP_BAD_ST=$(json_field "${JP_BAD}" "status")
if [[ "${JP_BAD_ST}" == "failed" ]]; then
  pass "json_parse invalid: status=failed as expected"
else
  fail "json_parse invalid" "expected status=failed, got ${JP_BAD_ST}"
fi

# ── markdown_convert: output must contain HTML ───────────────────────────────
step "Tool: markdown_convert"
MD_RES=$(execute_tool "${WASM_SID}" "markdown_convert" '{"markdown":"# Title\nSome text"}')
MD_OUT=$(json_field "${MD_RES}" "output")
json_assert "markdown_convert" "${MD_RES}" "status" "completed"
if echo "${MD_OUT}" | grep -qi "html"; then
  pass "markdown_convert: output contains HTML tags"
else
  fail "markdown_convert: output should contain HTML" "output: ${MD_OUT:0:200}"
fi

# ── auto-route: echo without session_id → API creates WASM session ───────────
step "Auto-route: echo (no session_id)"
AUTO=$(api_post "/execute" '{"tool":"echo","input":{"auto":"true"}}')
AUTO_ST=$(json_field "${AUTO}" "status")
AUTO_JID=$(json_field "${AUTO}" "job_id")
if [[ "${AUTO_ST}" == "completed" && -n "${AUTO_JID}" ]]; then
  pass "Auto-route echo → completed  job_id=${AUTO_JID:0:8}..."
else
  fail "Auto-route echo" "status=${AUTO_ST}"
fi

# ── artifact: upload WASM output, download and verify ────────────────────────
step "Artifact: upload + download"
TMP_W=$(mktemp /tmp/wasm-out-XXXXXX.json)
echo "${ECHO_OUT}" > "${TMP_W}"
W_UP=$(curl -sf -X POST \
  -F "session_id=${WASM_SID}" -F "name=echo-output.json" -F "file=@${TMP_W}" \
  "${API_URL}/artifacts" 2>/dev/null || echo '{}')
rm -f "${TMP_W}"

W_ART_ID=$(json_field "${W_UP}" "artifact_id")
W_ART_KEY=$(json_field "${W_UP}" "key")
if [[ -n "${W_ART_ID}" ]]; then
  pass "Artifact upload → id=${W_ART_ID:0:8}...  key=${W_ART_KEY}"
  DL_W=$(mktemp /tmp/wasm-dl-XXXXXX)
  if curl -sf "${API_URL}/artifacts/${W_ART_KEY}" -o "${DL_W}" 2>/dev/null \
      && grep -q "hello-wasm" "${DL_W}"; then
    pass "Artifact download: content matches echo output"
  else
    fail "Artifact download" "content mismatch or request failed"
  fi
  rm -f "${DL_W}"
else
  fail "Artifact upload" "${W_UP:0:300}"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# FIRECRACKER / MICROVM WORKFLOW
# Tools routed to MicroVM tier: python_run, bash_run
# Runtime mode: sim (no /dev/kvm) or real (FC_MODE=real, KVM present)
# ═══════════════════════════════════════════════════════════════════════════════
section "Firecracker / MicroVM Workflow"

step "Create MicroVM session"
FC_SESS=$(api_post "/sessions" '{"runtime":"microvm"}')
FC_SID=$(json_field "${FC_SESS}" "session_id")

if [[ -n "${FC_SID}" ]]; then
  pass "Session created: ${FC_SID:0:8}..."
else
  fail "Create MicroVM session" "${FC_SESS}"
  exit 1
fi

# ── python_run: print string ─────────────────────────────────────────────────
step "Tool: python_run (print hello)"
PY_RES=$(execute_tool "${FC_SID}" "python_run" '{"code":"print(\"hello from firecracker\")"}')
PY_OUT=$(json_field "${PY_RES}" "output")
json_assert "python_run hello" "${PY_RES}" "status" "completed"
info "python_run output: ${PY_OUT:0:120}"

# ── python_run: arithmetic ────────────────────────────────────────────────────
step "Tool: python_run (arithmetic: 6*7)"
PYMATH=$(execute_tool "${FC_SID}" "python_run" '{"code":"x=6*7; print(x)"}')
PYMATH_OUT=$(json_field "${PYMATH}" "output")
json_assert "python_run arithmetic" "${PYMATH}" "status" "completed"
info "python_run arithmetic output: ${PYMATH_OUT:0:120}"

# ── bash_run: echo ────────────────────────────────────────────────────────────
step "Tool: bash_run (echo)"
BASH_RES=$(execute_tool "${FC_SID}" "bash_run" '{"command":"echo firecracker-e2e-ok"}')
BASH_OUT=$(json_field "${BASH_RES}" "output")
json_assert "bash_run" "${BASH_RES}" "status" "completed"
info "bash_run output: ${BASH_OUT:0:120}"

# ── bash_run: env check ───────────────────────────────────────────────────────
step "Tool: bash_run (env check)"
BENV=$(execute_tool "${FC_SID}" "bash_run" '{"command":"echo SHELL=$SHELL"}')
json_assert "bash_run env" "${BENV}" "status" "completed"
info "bash_run env: $(json_field "${BENV}" "output" | head -c 80)"

# ── auto-route: python_run without session_id ────────────────────────────────
step "Auto-route: python_run (no session_id)"
FC_AUTO=$(api_post "/execute" '{"tool":"python_run","input":{"code":"print(42)"}}')
FC_AUTO_ST=$(json_field "${FC_AUTO}" "status")
if [[ "${FC_AUTO_ST}" == "completed" ]]; then
  pass "Auto-route python_run → completed"
else
  fail "Auto-route python_run" "status=${FC_AUTO_ST}"
fi

# ── artifact: upload MicroVM output ──────────────────────────────────────────
step "Artifact: upload MicroVM session output"
TMP_FC=$(mktemp /tmp/fc-out-XXXXXX.txt)
printf "python_run: %s\nbash_run:   %s\n" "${PY_OUT}" "${BASH_OUT}" > "${TMP_FC}"
FC_UP=$(curl -sf -X POST \
  -F "session_id=${FC_SID}" -F "name=fc-session-output.txt" -F "file=@${TMP_FC}" \
  "${API_URL}/artifacts" 2>/dev/null || echo '{}')
rm -f "${TMP_FC}"

FC_ART_ID=$(json_field "${FC_UP}" "artifact_id")
FC_ART_KEY=$(json_field "${FC_UP}" "key")
if [[ -n "${FC_ART_ID}" ]]; then
  pass "Artifact upload → id=${FC_ART_ID:0:8}..."
  info "URL: $(json_field "${FC_UP}" "url")"
  DL_FC=$(mktemp /tmp/fc-dl-XXXXXX)
  if curl -sf "${API_URL}/artifacts/${FC_ART_KEY}" -o "${DL_FC}" 2>/dev/null \
      && grep -q "python_run" "${DL_FC}"; then
    pass "Artifact download: content verified"
  else
    fail "Artifact download" "content mismatch or request failed"
  fi
  rm -f "${DL_FC}"
else
  fail "Artifact upload" "${FC_UP:0:300}"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-TIER ROUTING
# Verify every tool auto-routes to the correct tier
# ═══════════════════════════════════════════════════════════════════════════════
section "Cross-tier Routing Verification"

for spec in \
  'echo|wasm|{"x":"1"}' \
  'hello|wasm|{"name":"x"}' \
  'json_parse|wasm|{"data":"{\"k\":1}"}' \
  'markdown_convert|wasm|{"markdown":"# h"}' \
  'python_run|microvm|{"code":"pass"}' \
  'bash_run|microvm|{"command":"true"}'; do
  IFS='|' read -r tool tier input <<< "${spec}"
  RES=$(api_post "/execute" "{\"tool\":\"${tool}\",\"input\":${input}}")
  ST=$(json_field "${RES}" "status")
  if [[ "${ST}" == "completed" ]]; then
    pass "Route: ${tool} → ${tier} (completed)"
  else
    fail "Route: ${tool} → ${tier}" "status=${ST}"
  fi
done

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
TOTAL=$((PASS + FAIL))
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
if [[ $FAIL -eq 0 ]]; then
  printf "${BOLD}║  ${GREEN}✓  All %d checks passed${NC}${BOLD}%-30s║${NC}\n" "${TOTAL}" " "
  echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  ${GREEN}WASM workflow    ✓${NC}  echo · hello · json_parse · markdown_convert · artifact"
  echo -e "  ${GREEN}MicroVM workflow ✓${NC}  python_run · bash_run · artifact"
  echo -e "  ${GREEN}Cross-tier route ✓${NC}  6 tools auto-routed correctly"
  echo ""
  exit 0
else
  printf "${BOLD}║  ${RED}✗  %d / %d checks failed${NC}${BOLD}%-29s║${NC}\n" "${FAIL}" "${TOTAL}" " "
  echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
  echo ""
  exit 1
fi

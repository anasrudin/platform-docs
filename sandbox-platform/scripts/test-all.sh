#!/usr/bin/env bash
# test-all.sh
# Runs all test suites in the correct order.
#
# Each suite can run standalone. This script is the single entry point
# for verifying the complete platform.
#
# Modes:
#   --unit    Go tests only, no running services  [default]
#   --sim     Go tests + live API integration
#   --real    Go tests + live API + real KVM/wasmtime
#
# Usage:
#   bash scripts/test-all.sh [--unit | --sim | --real] [--api-url URL]
#   bash scripts/test-all.sh --unit          # fast: no services needed
#   bash scripts/test-all.sh --sim           # full: make dev must be running

set -uo pipefail   # not -e: we want all suites to run even if one fails
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODE="${1:---unit}"
API_URL="${PLATFORM_API_URL:-http://localhost:8080}"

# Forward remaining args
shift || true
EXTRA_ARGS=("$@")

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

SUITES_PASS=0
SUITES_FAIL=0

run_suite() {
  local name="$1" script="$2"
  shift 2
  echo ""
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BLUE}  Suite: ${name}${NC}"
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  if bash "${SCRIPT_DIR}/${script}" "$@" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"; then
    SUITES_PASS=$((SUITES_PASS+1))
    echo -e "${GREEN}  ✓ ${name}${NC}"
  else
    SUITES_FAIL=$((SUITES_FAIL+1))
    echo -e "${RED}  ✗ ${name}${NC}"
  fi
}

echo "╔══════════════════════════════════════════════════╗"
echo "║            All Tests  [mode: ${MODE}]             "
echo "╚══════════════════════════════════════════════════╝"
echo "  SCRIPT_DIR: ${SCRIPT_DIR}"
echo "  API_URL:    ${API_URL}"

# ── Snapshot builder (always unit mode — no KVM/Docker needed) ────────────────
run_suite "snapshot-builder"    "test-snapshot-builder.sh"

# ── Go runtime unit tests ─────────────────────────────────────────────────────
run_suite "fc-runtime"          "test-fc-runtime.sh"     "${MODE}" --api-url "${API_URL}"
run_suite "wasm-runtime"        "test-wasm-runtime.sh"   "${MODE}" --api-url "${API_URL}"
run_suite "artifact-store"      "test-artifact-store.sh" \
  "$(  [[ "${MODE}" == "--unit" ]] && echo "--unit" || echo "--sim"  )" \
  --api-url "${API_URL}"

# ── Infrastructure cluster (only when sim/real and running on a cluster) ──────
if [[ "${MODE}" != "--unit" ]]; then
  echo ""
  echo -e "${YELLOW}  (infra-cluster requires a production node — run separately if needed)${NC}"
  echo -e "${YELLOW}  → bash scripts/test-infra-cluster.sh [NODE1_IP]${NC}"
fi

# ── Firecracker setup (only in real mode) ─────────────────────────────────────
if [[ "${MODE}" == "--real" ]]; then
  run_suite "firecracker-setup" "test-firecracker-setup.sh"
fi

# ── Final summary ─────────────────────────────────────────────────────────────
TOTAL=$((SUITES_PASS + SUITES_FAIL))
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║               Final Results                      ║"
echo "╠══════════════════════════════════════════════════╣"
printf "║  %-20s  %2d / %2d suites passed         ║\n" "${MODE}" "${SUITES_PASS}" "${TOTAL}"
echo "╚══════════════════════════════════════════════════╝"

if [[ $SUITES_FAIL -eq 0 ]]; then
  echo -e "${GREEN}All suites passed.${NC}"
  exit 0
else
  echo -e "${RED}${SUITES_FAIL} suite(s) failed.${NC}"
  exit 1
fi

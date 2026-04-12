#!/usr/bin/env bash
# tools/runbook/gcp.sh — Demo runbook for GCP Nomad (FC_MODE=real, KVM enabled)
#
# Thin wrapper over gcp-jumphost-nomad/:
#   setup    → gen-topology + deploy-full-stack
#   test     → smoke-test.sh
#   teardown → cleanup.sh
#   status   → check health endpoints across all layers
#
# Usage:
#   ./gcp.sh <setup|test|teardown|status> [options]
#
# Options:
#   --project PROJECT_ID     GCP project ID
#   --zone ZONE              GCP zone (default: asia-southeast1-a)
#   --nomad NOMAD_VM_NAME    Nomad VM name in GCP (default: nomad)
#   --api-port PORT          platform-api port (default: 8080)
#   --snapshot SNAP_NAME     Firecracker snapshot name (default: python-v1)
#   --skip-sync              Skip rsync of services/ and sandbox-worker/
#   --skip-firewall          Skip firewall rule update
#   --skip-nomad             Skip Nomad job redeploy
#   --fc-mode MODE           FC_MODE: sim (default) or real
#   --my-ip IP               Your public IP (default: auto-detect)
#   --dry-run                Print commands without executing
set -euo pipefail

RUNBOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GCP_DIR="${RUNBOOK_DIR}/gcp-jumphost-nomad"
GCLOUD_DIR="${GCP_DIR}/gcloud"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${BLUE}[gcp-runbook]${NC} $*"; }
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  !${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*" >&2; }
step() { echo -e "\n${BOLD}── $* ──${NC}"; }

run() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    printf '[dry-run]'; printf ' %q' "$@"; printf '\n'
  else
    "$@"
  fi
}

# ── Defaults ──────────────────────────────────────────────────────────────────
PROJECT_ID="${PROJECT_ID:-e2b-infra-489707}"
ZONE="${ZONE:-asia-southeast1-a}"
NOMAD_NAME="${NOMAD_NAME:-nomad}"
API_PORT="${API_PORT:-8080}"
SNAPSHOT_NAME="${SNAPSHOT_NAME:-python-v1}"
FC_MODE="${FC_MODE:-sim}"   # sim = safe default (no snapshot required); real = actual Firecracker VMs
DRY_RUN=false

DEPLOY_EXTRA_ARGS=()

# ── Argument parsing ──────────────────────────────────────────────────────────
SUBCOMMAND="${1:-}"
shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)        PROJECT_ID="$2";    shift 2 ;;
    --zone)           ZONE="$2";          shift 2 ;;
    --nomad)          NOMAD_NAME="$2";    shift 2 ;;
    --api-port)       API_PORT="$2";      shift 2 ;;
    --snapshot)       SNAPSHOT_NAME="$2"; shift 2 ;;
    --skip-sync)      DEPLOY_EXTRA_ARGS+=("--skip-sync");     shift ;;
    --skip-firewall)  DEPLOY_EXTRA_ARGS+=("--skip-firewall"); shift ;;
    --skip-nomad)     DEPLOY_EXTRA_ARGS+=("--skip-nomad");    shift ;;
    --fc-mode)        FC_MODE="$2"; shift 2 ;;
    --fc-mode=*)      FC_MODE="${1#--fc-mode=}"; shift ;;
    --my-ip)          DEPLOY_EXTRA_ARGS+=("--my-ip=$2");      shift 2 ;;
    --my-ip=*)        DEPLOY_EXTRA_ARGS+=("$1");              shift ;;
    --dry-run)        DRY_RUN=true;       shift ;;
    *) fail "Unknown option: $1"; echo "Run '$0 --help' for usage." >&2; exit 1 ;;
  esac
done

# ── Load topology if it already exists ───────────────────────────────────────
TOPOLOGY_FILE="${GCP_DIR}/config/topology.env"
if [[ -f "${TOPOLOGY_FILE}" ]]; then
  # shellcheck source=/dev/null
  source "${TOPOLOGY_FILE}"
  log "Topology loaded: ${TOPOLOGY_FILE}"
fi

CONTROLLER_HOST="${CONTROLLER_HOST:-}"
API_URL="http://${CONTROLLER_HOST:-localhost}:${API_PORT}"

# ── Prereqs ───────────────────────────────────────────────────────────────────
check_prereqs() {
  local missing=()
  for cmd in gcloud curl jq python3; do
    command -v "$cmd" &>/dev/null || missing+=("$cmd")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    fail "Missing required tools: ${missing[*]}"
    exit 1
  fi
  ok "Prerequisites: gcloud curl jq python3"

  if ! gcloud auth list --filter="status=ACTIVE" --format="value(account)" 2>/dev/null | grep -q .; then
    fail "gcloud not authenticated. Run: gcloud auth login"
    exit 1
  fi
  ok "gcloud authenticated"
}

# ── Poll helper ───────────────────────────────────────────────────────────────
poll_healthy() {
  local label="$1" check_cmd="$2" max_seconds="${3:-60}"
  if [[ "${DRY_RUN}" == "true" ]]; then
    log "[dry-run] would poll: $label"
    return 0
  fi
  log "Waiting for $label (max ${max_seconds}s)..."
  local i=0 interval=3
  while (( i * interval < max_seconds )); do
    if eval "$check_cmd" &>/dev/null; then
      echo ""
      ok "$label is ready"
      return 0
    fi
    echo -n "."
    sleep "$interval"
    (( i++ )) || true
  done
  echo ""
  fail "$label not ready after ${max_seconds}s"
  return 1
}

# ── setup ─────────────────────────────────────────────────────────────────────
cmd_setup() {
  step "Setup GCP demo (real Firecracker + KVM)"
  check_prereqs

  # Step 1: Generate topology.env from Terraform output (if not present)
  if [[ ! -f "${TOPOLOGY_FILE}" ]]; then
    step "Generating topology.env"
    if [[ "${DRY_RUN}" == "true" ]]; then
      log "[dry-run] would run: gen-topology.sh --dry-run"
    else
      run bash "${GCLOUD_DIR}/gen-topology.sh" || {
        warn "gen-topology.sh failed — Terraform may not have been applied yet."
        warn "Manual fallback:"
        warn "  cp ${GCP_DIR}/config/topology.env.example ${TOPOLOGY_FILE}"
        warn "  # Set CONTROLLER_HOST to your GCP VM's IP"
        exit 1
      }
      # Reload after generating
      # shellcheck source=/dev/null
      source "${TOPOLOGY_FILE}"
      CONTROLLER_HOST="${CONTROLLER_HOST:-}"
      API_URL="http://${CONTROLLER_HOST}:${API_PORT}"
    fi
  else
    ok "topology.env already exists: ${TOPOLOGY_FILE}"
  fi

  # Step 2: Deploy full stack to GCP
  step "Deploying full stack to GCP (FC_MODE=${FC_MODE})"
  log "  Project:  ${PROJECT_ID}"
  log "  Zone:     ${ZONE}"
  log "  VM:       ${NOMAD_NAME}"
  log "  API port: ${API_PORT}"
  log "  FC_MODE:  ${FC_MODE}"
  log ""

  run env \
    PROJECT_ID="${PROJECT_ID}" \
    ZONE="${ZONE}" \
    NOMAD_NAME="${NOMAD_NAME}" \
    SNAPSHOT_NAME="${SNAPSHOT_NAME}" \
    API_PORT="${API_PORT}" \
    FC_MODE="${FC_MODE}" \
    bash "${GCLOUD_DIR}/deploy-full-stack.sh" "--fc-mode=${FC_MODE}" "${DEPLOY_EXTRA_ARGS[@]+"${DEPLOY_EXTRA_ARGS[@]}"}"

  # Step 3: Wait for API to become healthy
  if [[ -n "${CONTROLLER_HOST}" ]]; then
    poll_healthy "platform-api" \
      "curl -fsS '${API_URL}/health' >/dev/null" \
      90
  fi

  echo ""
  ok "Setup complete. Run: $0 test"
  _print_urls
}

# ── test ──────────────────────────────────────────────────────────────────────
cmd_test() {
  step "End-to-end smoke test (GCP real mode)"

  if [[ -z "${CONTROLLER_HOST:-}" ]]; then
    fail "CONTROLLER_HOST is unknown. Run '$0 setup' first."
    exit 1
  fi

  run bash "${GCP_DIR}/smoke-test.sh" "${API_URL}"
}

# ── teardown ──────────────────────────────────────────────────────────────────
cmd_teardown() {
  step "Teardown GCP demo resources"

  warn "This will stop the Nomad job and kill any orphaned Firecracker processes on the VM."
  warn "Data in MinIO/Postgres/Redis is NOT deleted unless --purge is used."
  echo ""

  run env \
    PROJECT_ID="${PROJECT_ID}" \
    ZONE="${ZONE}" \
    NOMAD_NAME="${NOMAD_NAME}" \
    bash "${GCLOUD_DIR}/cleanup.sh"

  ok "Teardown complete."
}

# ── status ────────────────────────────────────────────────────────────────────
cmd_status() {
  echo ""
  printf "${BOLD}%-28s %s${NC}\n" "Endpoint" "Status"
  printf "%-28s %s\n" "───────────────────────────" "──────────────────────────"

  local C="${CONTROLLER_HOST:-<not set>}"
  local D="${DATA_HOST:-${C}}"

  _check_url() {
    local label="$1" url="$2"
    if [[ "${C}" == "<not set>" ]]; then
      printf "%-28s %s\n" "${label}" "unknown (topology.env not loaded)"
      return
    fi
    if curl -fsS --max-time 3 "${url}" >/dev/null 2>&1; then
      printf "%-28s ${GREEN}up${NC}   %s\n" "${label}" "${url}"
    else
      printf "%-28s ${RED}down${NC} %s\n" "${label}" "${url}"
    fi
  }

  _check_url "platform-api /health"  "http://${C}:${API_PORT}/health"
  _check_url "Nomad UI"              "http://${C}:4646/v1/status/leader"
  _check_url "Consul UI"             "http://${C}:8500/v1/status/leader"
  _check_url "Jaeger UI"             "http://${D}:16686/"
  _check_url "MinIO console"         "http://${D}:9001/minio/health/live"

  echo ""
  if [[ -f "${TOPOLOGY_FILE}" ]]; then
    ok "topology.env: ${TOPOLOGY_FILE}"
    echo "  controller: ${CONTROLLER_HOST:-<not set>}"
    echo "  data:       ${DATA_HOST:-${CONTROLLER_HOST:-<not set>}}"
  else
    warn "topology.env not found — run '$0 setup' or gen-topology.sh"
  fi
  echo ""
}

# ── helper: print dashboard URLs ─────────────────────────────────────────────
_print_urls() {
  local C="${CONTROLLER_HOST:-<controller-ip>}"
  local D="${DATA_HOST:-${C}}"
  echo ""
  echo "  Dashboards:"
  printf "    %-22s http://%s:4646\n"   "Nomad:"   "${C}"
  printf "    %-22s http://%s:8500/ui\n" "Consul:"  "${C}"
  printf "    %-22s http://%s:${API_PORT}/health\n" "platform-api:"  "${C}"
  printf "    %-22s http://%s:16686\n"  "Jaeger:"  "${D}"
  printf "    %-22s http://%s:9001\n"   "MinIO:"   "${D}"
  echo ""
  echo "  Smoke test:"
  echo "    ${GCP_DIR}/smoke-test.sh http://${C}:${API_PORT}"
  echo ""
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
case "${SUBCOMMAND}" in
  setup)    cmd_setup    ;;
  test)     cmd_test     ;;
  teardown) cmd_teardown ;;
  status)   cmd_status   ;;
  ""|--help|-h)
    echo "Usage: $0 <setup|test|teardown|status> [options]"
    echo ""
    echo "Subcommands:"
    echo "  setup      Deploy full stack to GCP (FC_MODE=real + KVM)"
    echo "  test       Run end-to-end smoke test"
    echo "  teardown   Stop Nomad job + kill FC orphans on the GCP VM"
    echo "  status     Check health of all endpoints"
    echo ""
    echo "Options:"
    echo "  --project PROJECT_ID     GCP project ID (default: from topology.env / e2b-infra-489707)"
    echo "  --zone ZONE              GCP zone       (default: asia-southeast1-a)"
    echo "  --nomad NOMAD_VM_NAME    Nomad VM name  (default: nomad)"
    echo "  --api-port PORT          platform-api port (default: 8080)"
    echo "  --snapshot SNAP_NAME     Snapshot name  (default: python-v1)"
    echo "  --fc-mode MODE           FC_MODE: sim (default) or real"
    echo "                             sim  = no KVM/snapshot required, safe for demo"
    echo "                             real = actual Firecracker VMs, needs snapshot in MinIO"
    echo "  --skip-sync              Skip rsync of services/ and sandbox-worker/"
    echo "  --skip-firewall          Skip firewall rule update"
    echo "  --skip-nomad             Skip Nomad job redeploy"
    echo "  --my-ip IP               Your public IP (default: auto-detect)"
    echo "  --dry-run                Print commands without executing"
    echo ""
    echo "Quick start:"
    echo "  cd tools/runbook"
    echo "  ./gcp.sh setup"
    echo "  ./gcp.sh test"
    echo "  ./gcp.sh teardown"
    exit 0
    ;;
  *)
    fail "Unknown subcommand: ${SUBCOMMAND}"
    echo "Run '$0 --help' for usage." >&2
    exit 1
    ;;
esac

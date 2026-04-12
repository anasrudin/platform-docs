#!/usr/bin/env bash
# destroy-from-jumphost.sh — SSH into jumphost and run terraform destroy there.
#
# Usage:
#   cd tools/runbook/gcp-jumphost-nomad
#   ./destroy-from-jumphost.sh               # prompts for confirmation
#   ./destroy-from-jumphost.sh -auto-approve # fully unattended

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_VARS_FILE="${SCRIPT_DIR}/terraform/terraform.tfvars"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${BLUE}[destroy-from-jumphost]${NC} $*"; }
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  !${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*" >&2; exit 1; }

if ! command -v gcloud >/dev/null 2>&1; then
  fail "gcloud not found."
fi

if [[ ! -f "${TF_VARS_FILE}" ]]; then
  fail "terraform.tfvars not found at ${TF_VARS_FILE}"
fi

_tfvar() {
  local key="$1" default="${2:-}"
  local line
  line="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "${TF_VARS_FILE}" | head -1)"
  if [[ -z "${line}" ]]; then echo "${default}"; return; fi
  if echo "${line}" | grep -q '"'; then
    echo "${line}" | sed 's/.*"\([^"]*\)".*/\1/'
  else
    echo "${line}" | sed 's/^[^=]*=//' | sed 's/#.*//' | tr -d ' '
  fi
}

PROJECT_ID="${PROJECT_ID:-$(_tfvar project_id '')}"
ZONE="${ZONE:-$(_tfvar zone 'asia-southeast1-a')}"
JUMPHOST_NAME="${JUMPHOST_NAME:-$(_tfvar jumphost_name 'jumphost')}"

if [[ -z "${PROJECT_ID}" ]]; then
  fail "project_id not found in terraform.tfvars."
fi

REMOTE_RUNBOOK="~/gcp-jumphost-nomad"

echo -e "${BOLD}=== Destroy from jumphost ===${NC}"
echo ""
log "project:  ${PROJECT_ID}"
log "zone:     ${ZONE}"
log "jumphost: ${JUMPHOST_NAME}"
echo ""

warn "This will stop all platform services and DELETE all GCP resources."
echo ""

REMOTE_CMD="
set -euo pipefail
cd ${REMOTE_RUNBOOK}
chmod +x destroy.sh 2>/dev/null || true
./destroy.sh $*
"

gcloud compute ssh \
  "${JUMPHOST_NAME}" \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  --quiet \
  --command="${REMOTE_CMD}"

# Clean up local topology.env
TOPOLOGY_FILE="${SCRIPT_DIR}/config/topology.env"
if [[ -f "${TOPOLOGY_FILE}" ]]; then
  rm -f "${TOPOLOGY_FILE}"
  ok "Removed local ${TOPOLOGY_FILE}"
fi

echo ""
ok "All GCP resources destroyed."
echo ""
echo "  To redeploy:"
echo "    ${SCRIPT_DIR}/deploy-from-jumphost.sh"
echo ""

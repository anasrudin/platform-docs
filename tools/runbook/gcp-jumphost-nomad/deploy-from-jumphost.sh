#!/usr/bin/env bash
# deploy-from-jumphost.sh — Sync code to jumphost, run terraform apply there,
#                           then pull topology.env back locally.
#
# Why run Terraform on the jumphost?
#   The Terraform null_resource provisioner SSHes from wherever Terraform runs.
#   Running on the jumphost avoids NAT/firewall issues between the laptop and
#   the Nomad VM's private IP.
#
# What this script does:
#   1. Parse project/zone/user from terraform.tfvars (no extra env vars needed)
#   2. Sync this runbook dir to the jumphost
#   3. Sync sandbox-worker/ and services/ to the jumphost (needed by deploy-full-stack.sh)
#   4. Ensure Terraform is installed on the jumphost
#   5. SSH in and run ./deploy.sh [-auto-approve]
#   6. Pull config/topology.env back from jumphost to local
#   7. Print dashboard URLs
#
# Usage:
#   cd tools/runbook/gcp-jumphost-nomad
#   ./deploy-from-jumphost.sh                   # prompts for confirmation
#   ./deploy-from-jumphost.sh -auto-approve      # fully unattended
#   ./deploy-from-jumphost.sh -var fc_mode=real  # pass extra terraform flags
#
# Prerequisites:
#   - terraform/terraform.tfvars must exist and contain project_id, ssh_user, zone
#   - gcloud must be authenticated (gcloud auth login)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
TF_VARS_FILE="${SCRIPT_DIR}/terraform/terraform.tfvars"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${BLUE}[deploy-from-jumphost]${NC} $*"; }
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  !${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*" >&2; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────────────
if ! command -v gcloud >/dev/null 2>&1; then
  fail "gcloud not found. Install: https://cloud.google.com/sdk/docs/install"
fi

if ! gcloud auth list --filter="status=ACTIVE" --format="value(account)" 2>/dev/null | grep -q .; then
  fail "gcloud not authenticated. Run: gcloud auth login"
fi

if [[ ! -f "${TF_VARS_FILE}" ]]; then
  fail "terraform.tfvars not found at ${TF_VARS_FILE}
  Run:
    cp terraform/terraform.tfvars.example terraform/terraform.tfvars
    # Fill in: project_id, admin_cidr, ssh_user"
fi

# ── Parse terraform.tfvars ────────────────────────────────────────────────────
_tfvar() {
  local key="$1" default="${2:-}"
  # Extract value between quotes; fall back to unquoted value
  local line
  line="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "${TF_VARS_FILE}" | head -1)"
  if [[ -z "${line}" ]]; then echo "${default}"; return; fi
  # Quoted value: key = "value"
  if echo "${line}" | grep -q '"'; then
    echo "${line}" | sed 's/.*"\([^"]*\)".*/\1/'
  else
    # Unquoted: key = value  (strip key=, spaces, inline comments)
    echo "${line}" | sed 's/^[^=]*=//' | sed 's/#.*//' | tr -d ' '
  fi
}

PROJECT_ID="${PROJECT_ID:-$(_tfvar project_id '')}"
ZONE="${ZONE:-$(_tfvar zone 'asia-southeast1-a')}"
SSH_USER="${SSH_USER:-$(_tfvar ssh_user "$USER")}"
JUMPHOST_NAME="${JUMPHOST_NAME:-$(_tfvar jumphost_name 'jumphost')}"

if [[ -z "${PROJECT_ID}" ]]; then
  fail "project_id not found in terraform.tfvars. Set PROJECT_ID env var or fill in terraform.tfvars."
fi

REMOTE_RUNBOOK="~/gcp-jumphost-nomad"
REMOTE_ROOT="~/platform-docs"

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${BOLD}=== Deploy from jumphost ===${NC}"
echo ""
log "project:   ${PROJECT_ID}"
log "zone:      ${ZONE}"
log "jumphost:  ${JUMPHOST_NAME}"
log "ssh_user:  ${SSH_USER}"
log "tf flags:  $*"
echo ""

# ── tar helper: pack a directory into a tmp tarball (exclude noise) ──────────
_pack() {
  local src="$1"    # absolute path to source dir
  local name="$2"   # archive base name (no extension)
  local tmp="/tmp/${name}.tar.gz"
  tar -czf "${tmp}" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.git' \
    --exclude='.pytest_cache' \
    --exclude='*.egg-info' \
    --exclude='.venv' \
    --exclude='node_modules' \
    -C "$(dirname "${src}")" "$(basename "${src}")"
  echo "${tmp}"
}

_upload_and_extract() {
  local archive="$1"   # local path to .tar.gz
  local remote_parent="$2"  # remote destination parent dir (e.g. ~/platform-docs)
  local name
  name="$(basename "${archive}" .tar.gz)"
  gcloud compute scp \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    "${archive}" \
    "${JUMPHOST_NAME}:/tmp/${name}.tar.gz" \
    --quiet
  gcloud compute ssh "${JUMPHOST_NAME}" \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    --quiet \
    --command="mkdir -p ${remote_parent} && tar -xzf /tmp/${name}.tar.gz -C ${remote_parent} && rm /tmp/${name}.tar.gz"
  rm -f "${archive}"
}

# ── Step 1: Sync runbook dir to jumphost ─────────────────────────────────────
log "Step 1/5 — Syncing runbook to jumphost (${JUMPHOST_NAME}:${REMOTE_RUNBOOK})..."

gcloud compute ssh \
  "${JUMPHOST_NAME}" \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  --quiet \
  --command="mkdir -p $(dirname "${REMOTE_RUNBOOK}") ${REMOTE_ROOT}"

log "  Packing runbook..."
runbook_archive="$(_pack "${SCRIPT_DIR}" "gcp-jumphost-nomad")"
log "  Uploading $(du -sh "${runbook_archive}" | cut -f1) → jumphost..."
_upload_and_extract "${runbook_archive}" "$(dirname "${REMOTE_RUNBOOK}")"

ok "Runbook synced"
echo ""

# ── Step 2: Sync application code (needed by deploy-full-stack.sh) ───────────
log "Step 2/5 — Syncing services/ and sandbox-worker/ to jumphost..."

log "  Packing services/..."
svc_archive="$(_pack "${ROOT_DIR}/services" "platform-services")"
log "  Uploading $(du -sh "${svc_archive}" | cut -f1) → jumphost..."
_upload_and_extract "${svc_archive}" "${REMOTE_ROOT}"

log "  Packing sandbox-worker/..."
wk_archive="$(_pack "${ROOT_DIR}/sandbox-worker" "platform-sandbox-worker")"
log "  Uploading $(du -sh "${wk_archive}" | cut -f1) → jumphost..."
_upload_and_extract "${wk_archive}" "${REMOTE_ROOT}"

ok "Application code synced"
echo ""

# ── Step 3: Ensure Terraform is installed on jumphost ────────────────────────
log "Step 3/5 — Ensuring Terraform is installed on jumphost..."

gcloud compute ssh \
  "${JUMPHOST_NAME}" \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  --quiet \
  --command='
set -euo pipefail
if command -v terraform >/dev/null 2>&1; then
  echo "  terraform $(terraform version -json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get(\"terraform_version\",\"?\"))" 2>/dev/null || terraform version | head -1) already installed"
  exit 0
fi
echo "  Installing Terraform..."
sudo apt-get update -qq
sudo apt-get install -y gnupg software-properties-common curl -qq
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt-get update -qq
sudo apt-get install -y terraform -qq
terraform version
echo "  Terraform installed."
'

ok "Terraform ready on jumphost"
echo ""

# ── Step 4: Run deploy.sh on jumphost ────────────────────────────────────────
log "Step 4/5 — Running deploy.sh on jumphost (this provisions GCP infra + deploys platform stack)..."
echo ""
warn "This will CREATE or UPDATE GCP resources and deploy the full platform stack."
echo ""

gcloud compute ssh \
  "${JUMPHOST_NAME}" \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  --quiet \
  --command="$(cat <<REMOTE
set -euo pipefail
RB="\$HOME/gcp-jumphost-nomad"
RR="\$HOME/platform-docs"
cd "\$RB"
chmod +x deploy.sh gcloud/deploy-full-stack.sh gcloud/gen-topology.sh gcloud/import-existing-state.sh smoke-test.sh 2>/dev/null || true

# Init first (required before import)
terraform -chdir="\$RB/terraform" init -upgrade -input=false

# Import existing GCP resources so apply doesn't fail with 409
PROJECT_ID=${PROJECT_ID} ZONE=${ZONE} SSH_USER=${SSH_USER} \
  bash "\$RB/gcloud/import-existing-state.sh"

# Apply — creates only what's missing
PLATFORM_ROOT="\$RR" ./deploy.sh $*
REMOTE
)"

ok "deploy.sh complete"
echo ""

# ── Step 5: Pull topology.env back to local ───────────────────────────────────
log "Step 5/5 — Pulling config/topology.env from jumphost..."

mkdir -p "${SCRIPT_DIR}/config"
gcloud compute scp \
  --project="${PROJECT_ID}" \
  --zone="${ZONE}" \
  "${JUMPHOST_NAME}:${REMOTE_RUNBOOK}/config/topology.env" \
  "${SCRIPT_DIR}/config/topology.env" \
  --quiet 2>/dev/null || {
    warn "topology.env not found on jumphost — generating locally from terraform output..."
    # Fall back: read terraform output from jumphost and build topology.env locally
    TF_OUTPUT_JSON="$(gcloud compute ssh \
      "${JUMPHOST_NAME}" \
      --project="${PROJECT_ID}" \
      --zone="${ZONE}" \
      --quiet \
      --command="terraform -chdir=${REMOTE_RUNBOOK}/terraform output -json 2>/dev/null || echo '{}'")"

    CONTROLLER_IP="$(echo "${TF_OUTPUT_JSON}" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d.get('controller_ip',{}).get('value','') or d.get('jumphost_public_ip',{}).get('value',''))
" 2>/dev/null || echo '')"

    if [[ -n "${CONTROLLER_IP}" ]]; then
      mkdir -p "${SCRIPT_DIR}/config"
      cat >"${SCRIPT_DIR}/config/topology.env" <<EOF
#!/usr/bin/env bash
# topology.env — generated by deploy-from-jumphost.sh on $(date -u '+%Y-%m-%dT%H:%M:%SZ')
CONTROLLER_HOST="${CONTROLLER_IP}"
WORKER_HOST="${CONTROLLER_IP}"
DATA_HOST="${CONTROLLER_IP}"
PROJECT_ID="${PROJECT_ID}"
ZONE="${ZONE}"
SSH_USER="${SSH_USER}"
EOF
      ok "topology.env written (minimal fallback)"
    else
      warn "Could not determine CONTROLLER_IP — topology.env not written."
    fi
  }

# ── Done ──────────────────────────────────────────────────────────────────────
if [[ -f "${SCRIPT_DIR}/config/topology.env" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/config/topology.env"
  C="${CONTROLLER_HOST:-?}"

  ok "topology.env available at: ${SCRIPT_DIR}/config/topology.env"
  echo ""
  echo -e "${BOLD}=== Deploy complete ===${NC}"
  echo ""
  echo "  Dashboards:"
  printf "    %-22s http://%s:8080/health\n" "platform-api:" "${C}"
  printf "    %-22s http://%s:4646\n"        "Nomad:"        "${C}"
  printf "    %-22s http://%s:8500/ui\n"     "Consul:"       "${C}"
  printf "    %-22s http://%s:16686\n"       "Jaeger:"       "${C}"
  printf "    %-22s http://%s:9001\n"        "MinIO:"        "${C}"
  echo ""
  echo "  Run smoke test:"
  echo "    ./smoke-test.sh http://${C}:8080"
  echo ""
  echo "  When done, tear everything down:"
  echo "    ./destroy-from-jumphost.sh"
  echo ""
else
  echo ""
  echo -e "${BOLD}=== Deploy complete ===${NC}"
  echo "  Check dashboards: SSH to jumphost and check terraform output or topology.env."
fi

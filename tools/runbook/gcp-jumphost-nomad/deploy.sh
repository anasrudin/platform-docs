#!/usr/bin/env bash
# deploy.sh — One-shot deploy: provision GCP infra + deploy platform stack.
#
# What it does:
#   1. terraform init        — download providers (skipped if already done)
#   2. terraform apply       — provision VMs, network, firewall rules
#   3. null_resource         — auto-runs deploy-full-stack.sh via Terraform provisioner:
#                              sync code → install venv → start Docker services → Nomad job
#   4. gen-topology.sh       — writes config/topology.env from Terraform outputs
#
# Usage:
#   cd tools/runbook/gcp-jumphost-nomad
#   cp terraform/terraform.tfvars.example terraform/terraform.tfvars
#   # fill in project_id, admin_cidr, ssh_user
#   ./deploy.sh
#
# Options passed through to terraform apply:
#   ./deploy.sh -auto-approve          # skip interactive confirmation
#   ./deploy.sh -var fc_mode=real      # deploy with real Firecracker
#   ./deploy.sh -target=...            # partial apply

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="${SCRIPT_DIR}/terraform"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${BLUE}[deploy]${NC} $*"; }
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  !${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*" >&2; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────────────
if ! command -v terraform >/dev/null 2>&1; then
  fail "terraform not found. Install: https://developer.hashicorp.com/terraform/install"
fi

if ! command -v gcloud >/dev/null 2>&1; then
  fail "gcloud not found. Install: https://cloud.google.com/sdk/docs/install"
fi

if ! gcloud auth list --filter="status=ACTIVE" --format="value(account)" 2>/dev/null | grep -q .; then
  fail "gcloud not authenticated. Run: gcloud auth login && gcloud auth application-default login"
fi

if [[ ! -f "${TF_DIR}/terraform.tfvars" ]]; then
  fail "terraform.tfvars not found.
  Run:
    cp ${TF_DIR}/terraform.tfvars.example ${TF_DIR}/terraform.tfvars
    # Edit: project_id, admin_cidr, ssh_user"
fi

# ── Step 1: terraform init ────────────────────────────────────────────────────
log "Step 1/3 — terraform init"
terraform -chdir="${TF_DIR}" init -upgrade
ok "Providers ready"
echo ""

# ── Step 2: terraform apply ───────────────────────────────────────────────────
log "Step 2/3 — terraform apply (provision VMs + deploy platform stack)"
log "  This will:"
log "    • Create jumphost + Nomad VM on GCP"
log "    • Wait for VM bootstrap (Nomad + Docker, ~2 min)"
log "    • Sync sandbox-worker/ and services/ to VM"
log "    • Install Python venv + app"
log "    • Start MinIO, Postgres, Redis, Consul, Jaeger via docker compose"
log "    • Deploy platform-api Nomad job"
echo ""

terraform -chdir="${TF_DIR}" apply "$@"

echo ""
ok "terraform apply complete"
echo ""

# ── Step 3: Write topology.env ────────────────────────────────────────────────
log "Step 3/3 — generating config/topology.env from Terraform outputs"
TF_DIR="${TF_DIR}" bash "${SCRIPT_DIR}/gcloud/gen-topology.sh"
ok "topology.env written"
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
CONTROLLER_IP="$(terraform -chdir="${TF_DIR}" output -raw controller_ip 2>/dev/null || echo '<unknown>')"
API_PORT="$(terraform -chdir="${TF_DIR}" output -json dashboard_urls 2>/dev/null \
  | python3 -c "import json,sys; u=json.load(sys.stdin); print(u['platform_api'])" 2>/dev/null || echo "http://${CONTROLLER_IP}:8080/health")"

echo -e "${BOLD}=== Deploy complete ===${NC}"
echo ""
echo "  Dashboards:"
printf "    %-22s http://%s:8080/health\n" "platform-api:"  "${CONTROLLER_IP}"
printf "    %-22s http://%s:4646\n"        "Nomad:"         "${CONTROLLER_IP}"
printf "    %-22s http://%s:8500/ui\n"     "Consul:"        "${CONTROLLER_IP}"
printf "    %-22s http://%s:16686\n"       "Jaeger:"        "${CONTROLLER_IP}"
printf "    %-22s http://%s:9001\n"        "MinIO:"         "${CONTROLLER_IP}"
echo ""
echo "  Run smoke test:"
echo "    ${SCRIPT_DIR}/smoke-test.sh http://${CONTROLLER_IP}:8080"
echo ""
echo "  When done, tear everything down:"
echo "    ${SCRIPT_DIR}/destroy.sh"
echo ""

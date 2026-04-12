#!/usr/bin/env bash
# destroy.sh — Tear down everything: stop platform stack + destroy GCP infra.
#
# What it does (in order):
#   1. null_resource destroy provisioner — stop Nomad job, kill Firecracker
#      processes, stop docker compose (runs BEFORE VMs are deleted)
#   2. terraform destroy — delete all GCP resources (VMs, network, firewall)
#
# Usage:
#   cd tools/runbook/gcp-jumphost-nomad
#   ./destroy.sh
#
# Options passed through to terraform destroy:
#   ./destroy.sh -auto-approve          # skip interactive confirmation
#   ./destroy.sh -target=...            # partial destroy

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="${SCRIPT_DIR}/terraform"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${BLUE}[destroy]${NC} $*"; }
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  !${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*" >&2; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────────────
if ! command -v terraform >/dev/null 2>&1; then
  fail "terraform not found."
fi

if [[ ! -f "${TF_DIR}/terraform.tfvars" ]]; then
  fail "terraform.tfvars not found at ${TF_DIR}/terraform.tfvars"
fi

if [[ ! -d "${TF_DIR}/.terraform" ]]; then
  warn "Terraform not initialized. Running init first..."
  terraform -chdir="${TF_DIR}" init -upgrade
fi

# ── Confirm ───────────────────────────────────────────────────────────────────
echo -e "${BOLD}=== Destroy platform stack + GCP infra ===${NC}"
echo ""
warn "This will:"
warn "  • Stop the platform-api Nomad job on the GCP VM"
warn "  • Kill any running Firecracker processes"
warn "  • Stop all Docker containers (MinIO, Postgres, Redis, Consul, Jaeger)"
warn "  • DELETE all GCP resources: VMs, network, firewall rules, service account"
echo ""

# terraform destroy prompts for confirmation unless -auto-approve is passed
terraform -chdir="${TF_DIR}" destroy "$@"

echo ""
ok "All GCP resources destroyed."
echo ""

# ── Clean up local topology.env ───────────────────────────────────────────────
TOPOLOGY_FILE="${SCRIPT_DIR}/config/topology.env"
if [[ -f "${TOPOLOGY_FILE}" ]]; then
  rm -f "${TOPOLOGY_FILE}"
  ok "Removed ${TOPOLOGY_FILE}"
fi

echo -e "${BOLD}=== Done. ===${NC}"
echo ""
echo "  To redeploy:"
echo "    ${SCRIPT_DIR}/deploy.sh"
echo ""

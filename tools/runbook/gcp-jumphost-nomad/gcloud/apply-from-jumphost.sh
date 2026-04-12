#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNBOOK_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID first}"
REGION="${REGION:-asia-southeast1}"
ZONE="${ZONE:-asia-southeast1-a}"
ADMIN_CIDR="${ADMIN_CIDR:-0.0.0.0/0}"
SSH_USER="${SSH_USER:-$USER}"
JUMPHOST_NAME="${JUMPHOST_NAME:-jumphost}"
REMOTE_DIR="${REMOTE_DIR:-gcp-jumphost-nomad}"

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require gcloud
ACCESS_TOKEN="$(gcloud auth print-access-token)"

echo "syncing runbook to jumphost"
gcloud compute scp \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --recurse \
  "$RUNBOOK_DIR/." \
  "${JUMPHOST_NAME}:~/${REMOTE_DIR}" \
  --quiet

gcloud compute scp \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  "${SCRIPT_DIR}/jumphost-terraform-bootstrap.sh" \
  "${JUMPHOST_NAME}:~/jumphost-terraform-bootstrap.sh" \
  --quiet

gcloud compute ssh \
  "$JUMPHOST_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --quiet \
  --command="bash ~/jumphost-terraform-bootstrap.sh ~/${REMOTE_DIR}"

gcloud compute ssh \
  "$JUMPHOST_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --quiet \
  --command="cat > ~/${REMOTE_DIR}/terraform/terraform.auto.tfvars <<EOF
project_id = \"$PROJECT_ID\"
region     = \"$REGION\"
zone       = \"$ZONE\"
admin_cidr = \"$ADMIN_CIDR\"
ssh_user   = \"$SSH_USER\"
EOF
TF_VAR_access_token='$ACCESS_TOKEN' PROJECT_ID='$PROJECT_ID' REGION='$REGION' ZONE='$ZONE' ADMIN_CIDR='$ADMIN_CIDR' SSH_USER='$SSH_USER' REMOTE_DIR='$REMOTE_DIR' bash ~/${REMOTE_DIR}/gcloud/import-existing-state.sh"

gcloud compute ssh \
  "$JUMPHOST_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --quiet \
  --command="TF_VAR_access_token='$ACCESS_TOKEN' terraform -chdir=\$HOME/${REMOTE_DIR}/terraform apply -auto-approve"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNBOOK_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID first}"
ZONE="${ZONE:-asia-southeast1-a}"
JUMPHOST_NAME="${JUMPHOST_NAME:-jumphost}"
REMOTE_DIR="${REMOTE_DIR:-gcp-jumphost-nomad}"

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require gcloud

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

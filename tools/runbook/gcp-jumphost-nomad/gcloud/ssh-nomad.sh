#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-}"
ZONE="${ZONE:-asia-southeast1-a}"
JUMPHOST_NAME="${JUMPHOST_NAME:-jumphost}"
NOMAD_NAME="${NOMAD_NAME:-nomad}"
NOMAD_SSH_USER="${NOMAD_SSH_USER:-${SSH_USER:-$USER}}"

project_args=()
if [[ -n "$PROJECT_ID" ]]; then
  project_args+=(--project="$PROJECT_ID")
fi

NOMAD_PRIVATE_IP="$(gcloud compute instances describe "$NOMAD_NAME" \
  "${project_args[@]}" \
  --zone="$ZONE" \
  --format='get(networkInterfaces[0].networkIP)')"

exec gcloud compute ssh "$JUMPHOST_NAME" \
  "${project_args[@]}" \
  --zone="$ZONE" \
  --ssh-flag="-A" \
  --ssh-flag="-tt" \
  --command="bash -lc 'ssh -A -o StrictHostKeyChecking=accept-new ${NOMAD_SSH_USER}@${NOMAD_PRIVATE_IP}'"

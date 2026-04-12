#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-}"
ZONE="${ZONE:-asia-southeast1-a}"
JUMPHOST_NAME="${JUMPHOST_NAME:-jumphost}"

project_args=()
if [[ -n "$PROJECT_ID" ]]; then
  project_args+=(--project="$PROJECT_ID")
fi

exec gcloud compute ssh "$JUMPHOST_NAME" \
  "${project_args[@]}" \
  --zone="$ZONE"

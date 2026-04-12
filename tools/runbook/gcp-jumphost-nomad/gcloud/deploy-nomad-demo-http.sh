#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNBOOK_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID first}"
REGION="${REGION:-asia-southeast1}"
ZONE="${ZONE:-asia-southeast1-a}"
JUMPHOST_NAME="${JUMPHOST_NAME:-jumphost}"
NOMAD_NAME="${NOMAD_NAME:-nomad}"
REMOTE_DIR="${REMOTE_DIR:-gcp-jumphost-nomad}"
JOB_PATH="${JOB_PATH:-nomad/demo-http.nomad}"

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require gcloud

NOMAD_PRIVATE_IP="$(gcloud compute instances describe "$NOMAD_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --format='get(networkInterfaces[0].networkIP)')"

gcloud compute ssh \
  "$JUMPHOST_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --quiet \
  --command="mkdir -p ~/${REMOTE_DIR}/nomad"

gcloud compute scp \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  "${RUNBOOK_DIR}/${JOB_PATH}" \
  "${JUMPHOST_NAME}:~/${REMOTE_DIR}/${JOB_PATH}" \
  --quiet

gcloud compute ssh \
  "$JUMPHOST_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --quiet \
  --command="NOMAD_ADDR='http://${NOMAD_PRIVATE_IP}:4646' nomad job run ~/${REMOTE_DIR}/${JOB_PATH}"

cat <<EOF

job submitted

nomad addr   : http://${NOMAD_PRIVATE_IP}:4646
service port  : 8081

to hit from your laptop, keep a tunnel open in a separate terminal:
  gcloud compute ssh ${JUMPHOST_NAME} --project=${PROJECT_ID} --zone=${ZONE} -- -N -L 8081:${NOMAD_PRIVATE_IP}:8081

then browse:
  http://127.0.0.1:8081/
EOF

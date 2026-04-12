#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID first}"
REGION="${REGION:-asia-southeast1}"
ZONE="${ZONE:-asia-southeast1-a}"
NETWORK_NAME="${NETWORK_NAME:-jump-nomad-vpc}"
SUBNET_NAME="${SUBNET_NAME:-jump-nomad-subnet}"
JUMPHOST_NAME="${JUMPHOST_NAME:-jumphost}"
NOMAD_NAME="${NOMAD_NAME:-nomad}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-jumphost-operator}"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

instance_exists() {
  local name="$1"
  gcloud compute instances describe "$name" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    >/dev/null 2>&1
}

firewall_exists() {
  local name="$1"
  gcloud compute firewall-rules describe "$name" \
    --project="$PROJECT_ID" \
    >/dev/null 2>&1
}

subnet_exists() {
  gcloud compute networks subnets describe "$SUBNET_NAME" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    >/dev/null 2>&1
}

network_exists() {
  gcloud compute networks describe "$NETWORK_NAME" \
    --project="$PROJECT_ID" \
    >/dev/null 2>&1
}

service_account_exists() {
  gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" \
    --project="$PROJECT_ID" \
    >/dev/null 2>&1
}

if instance_exists "$JUMPHOST_NAME"; then
  gcloud compute instances delete "$JUMPHOST_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --quiet
fi

if instance_exists "$NOMAD_NAME"; then
  gcloud compute instances delete "$NOMAD_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --quiet
fi

for rule in \
  "${NETWORK_NAME}-allow-ssh-jumphost" \
  "${NETWORK_NAME}-allow-ssh-nomad" \
  "${NETWORK_NAME}-allow-nomad-ui" \
  "${NETWORK_NAME}-allow-nomad-demo-http"
do
  if firewall_exists "$rule"; then
    gcloud compute firewall-rules delete "$rule" \
      --project="$PROJECT_ID" \
      --quiet
  fi
done

if subnet_exists; then
  gcloud compute networks subnets delete "$SUBNET_NAME" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --quiet
fi

if network_exists; then
  gcloud compute networks delete "$NETWORK_NAME" \
    --project="$PROJECT_ID" \
    --quiet
fi

if service_account_exists; then
  gcloud iam service-accounts delete "$SERVICE_ACCOUNT_EMAIL" \
    --project="$PROJECT_ID" \
    --quiet
fi

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID first}"
REGION="${REGION:-asia-southeast1}"
ZONE="${ZONE:-asia-southeast1-a}"
NETWORK_NAME="${NETWORK_NAME:-jump-nomad-vpc}"
SUBNET_NAME="${SUBNET_NAME:-jump-nomad-subnet}"
SUBNET_CIDR="${SUBNET_CIDR:-10.42.0.0/24}"
ADMIN_CIDR="${ADMIN_CIDR:-0.0.0.0/0}"
JUMPHOST_NAME="${JUMPHOST_NAME:-jumphost}"
NOMAD_NAME="${NOMAD_NAME:-nomad}"
JUMPHOST_MACHINE_TYPE="${JUMPHOST_MACHINE_TYPE:-e2-medium}"
NOMAD_MACHINE_TYPE="${NOMAD_MACHINE_TYPE:-n2-standard-4}"
BOOT_DISK_SIZE_GB="${BOOT_DISK_SIZE_GB:-30}"
IMAGE_FAMILY="${IMAGE_FAMILY:-debian-12}"
IMAGE_PROJECT="${IMAGE_PROJECT:-debian-cloud}"
SSH_USER="${SSH_USER:-$USER}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-jumphost-operator}"
SERVICE_ACCOUNT_DISPLAY_NAME="${SERVICE_ACCOUNT_DISPLAY_NAME:-Jumphost Operator}"
SERVICE_ACCOUNT_ROLES="${SERVICE_ACCOUNT_ROLES:-roles/logging.logWriter,roles/monitoring.metricWriter,roles/compute.viewer}"

JUMPHOST_STARTUP="${ROOT_DIR}/startup/jumphost-startup.sh"
NOMAD_STARTUP="${ROOT_DIR}/startup/nomad-startup.sh"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

resource_exists() {
  local describe_cmd=("$@")
  "${describe_cmd[@]}" >/dev/null 2>&1
}

create_firewall_if_missing() {
  local name="$1"
  shift

  if resource_exists gcloud compute firewall-rules describe "$name" --project="$PROJECT_ID"; then
    echo "firewall rule already exists: $name"
    return
  fi

  gcloud compute firewall-rules create "$name" \
    --project="$PROJECT_ID" \
    "$@"
}

require gcloud

gcloud config set project "$PROJECT_ID" >/dev/null

echo "enabling required APIs"
gcloud services enable \
  compute.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_ID"

if ! resource_exists gcloud compute networks describe "$NETWORK_NAME" --project="$PROJECT_ID"; then
  echo "creating network: $NETWORK_NAME"
  gcloud compute networks create "$NETWORK_NAME" \
    --project="$PROJECT_ID" \
    --subnet-mode=custom
else
  echo "network already exists: $NETWORK_NAME"
fi

if ! resource_exists gcloud compute networks subnets describe "$SUBNET_NAME" --project="$PROJECT_ID" --region="$REGION"; then
  echo "creating subnet: $SUBNET_NAME"
  gcloud compute networks subnets create "$SUBNET_NAME" \
    --project="$PROJECT_ID" \
    --network="$NETWORK_NAME" \
    --region="$REGION" \
    --range="$SUBNET_CIDR"
else
  echo "subnet already exists: $SUBNET_NAME"
fi

create_firewall_if_missing \
  "${NETWORK_NAME}-allow-ssh-jumphost" \
  --network="$NETWORK_NAME" \
  --direction=INGRESS \
  --allow=tcp:22 \
  --source-ranges="$ADMIN_CIDR" \
  --target-tags=jumphost \
  --description="Allow SSH from admin CIDR to jumphost"

create_firewall_if_missing \
  "${NETWORK_NAME}-allow-ssh-nomad" \
  --network="$NETWORK_NAME" \
  --direction=INGRESS \
  --allow=tcp:22 \
  --source-tags=jumphost \
  --target-tags=nomad \
  --description="Allow SSH from jumphost to nomad"

create_firewall_if_missing \
  "${NETWORK_NAME}-allow-nomad-ui" \
  --network="$NETWORK_NAME" \
  --direction=INGRESS \
  --allow=tcp:4646 \
  --source-tags=jumphost \
  --target-tags=nomad \
  --description="Allow Nomad UI from jumphost to nomad"

create_firewall_if_missing \
  "${NETWORK_NAME}-allow-nomad-demo-http" \
  --network="$NETWORK_NAME" \
  --direction=INGRESS \
  --allow=tcp:8081 \
  --source-tags=jumphost \
  --target-tags=nomad \
  --description="Allow demo HTTP job from jumphost to nomad"

create_firewall_if_missing \
  "${NETWORK_NAME}-allow-platform-api-public" \
  --network="$NETWORK_NAME" \
  --direction=INGRESS \
  --allow=tcp:8080 \
  --source-ranges="$ADMIN_CIDR" \
  --target-tags=nomad \
  --description="Allow platform-api from admin CIDR to nomad"

if ! resource_exists gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" --project="$PROJECT_ID"; then
  echo "creating service account: $SERVICE_ACCOUNT_EMAIL"
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
    --project="$PROJECT_ID" \
    --display-name="$SERVICE_ACCOUNT_DISPLAY_NAME"
else
  echo "service account already exists: $SERVICE_ACCOUNT_EMAIL"
fi

IFS=',' read -r -a roles <<< "$SERVICE_ACCOUNT_ROLES"
for role in "${roles[@]}"; do
  [[ -n "$role" ]] || continue

  echo "ensuring IAM binding: $role"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="$role" \
    >/dev/null
done

if ! resource_exists gcloud compute instances describe "$NOMAD_NAME" --project="$PROJECT_ID" --zone="$ZONE"; then
  echo "creating nomad instance: $NOMAD_NAME"
  gcloud compute instances create "$NOMAD_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --machine-type="$NOMAD_MACHINE_TYPE" \
    --enable-nested-virtualization \
    --min-cpu-platform="Intel Cascade Lake" \
    --subnet="$SUBNET_NAME" \
    --no-address \
    --tags=nomad \
    --image-family="$IMAGE_FAMILY" \
    --image-project="$IMAGE_PROJECT" \
    --boot-disk-size="${BOOT_DISK_SIZE_GB}GB" \
    --metadata-from-file=startup-script="$NOMAD_STARTUP"
else
  echo "instance already exists: $NOMAD_NAME"
fi

NOMAD_PRIVATE_IP="$(gcloud compute instances describe "$NOMAD_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --format='get(networkInterfaces[0].networkIP)')"

if ! resource_exists gcloud compute instances describe "$JUMPHOST_NAME" --project="$PROJECT_ID" --zone="$ZONE"; then
  echo "creating jumphost instance: $JUMPHOST_NAME"
  gcloud compute instances create "$JUMPHOST_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --machine-type="$JUMPHOST_MACHINE_TYPE" \
    --subnet="$SUBNET_NAME" \
    --tags=jumphost \
    --image-family="$IMAGE_FAMILY" \
    --image-project="$IMAGE_PROJECT" \
    --boot-disk-size="${BOOT_DISK_SIZE_GB}GB" \
    --service-account="$SERVICE_ACCOUNT_EMAIL" \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --metadata=nomad_private_ip="$NOMAD_PRIVATE_IP",nomad_ssh_user="$SSH_USER" \
    --metadata-from-file=startup-script="$JUMPHOST_STARTUP"
else
  echo "instance already exists: $JUMPHOST_NAME"
fi

JUMPHOST_EXTERNAL_IP="$(gcloud compute instances describe "$JUMPHOST_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')"

cat <<EOF

topology ready

project            : $PROJECT_ID
zone               : $ZONE
jumphost name      : $JUMPHOST_NAME
jumphost public ip : $JUMPHOST_EXTERNAL_IP
nomad name         : $NOMAD_NAME
nomad private ip   : $NOMAD_PRIVATE_IP
service account    : $SERVICE_ACCOUNT_EMAIL

next commands:
  PROJECT_ID=$PROJECT_ID ZONE=$ZONE JUMPHOST_NAME=$JUMPHOST_NAME ./gcloud/ssh-jumphost.sh
  PROJECT_ID=$PROJECT_ID ZONE=$ZONE JUMPHOST_NAME=$JUMPHOST_NAME NOMAD_NAME=$NOMAD_NAME SSH_USER=$SSH_USER ./gcloud/ssh-nomad.sh
EOF

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
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_EMAIL:-${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"
SSH_USER="${SSH_USER:-$USER}"
REMOTE_DIR="${REMOTE_DIR:-gcp-jumphost-nomad}"

APP_DIR="${HOME}/${REMOTE_DIR}"
TF_DIR="${APP_DIR}/terraform"

import_if_missing() {
  local address="$1"
  local id="$2"

  if terraform -chdir="$TF_DIR" state list 2>/dev/null | grep -Fxq "$address"; then
    echo "state already contains: $address"
    return
  fi

  echo "importing: $address"
  local import_output
  if import_output="$(terraform -chdir="$TF_DIR" import "$address" "$id" 2>&1)"; then
    printf '%s\n' "$import_output"
    return
  fi

  if grep -Fq "Resource already managed by Terraform" <<<"$import_output"; then
    echo "state already contains: $address"
    return
  fi

  printf '%s\n' "$import_output" >&2
  return 1
}

terraform -chdir="$TF_DIR" init -input=false

import_if_missing google_project_service.compute "${PROJECT_ID}/compute.googleapis.com"
import_if_missing google_project_service.iam "${PROJECT_ID}/iam.googleapis.com"
import_if_missing google_compute_network.main "projects/${PROJECT_ID}/global/networks/${NETWORK_NAME}"
import_if_missing google_compute_subnetwork.main "projects/${PROJECT_ID}/regions/${REGION}/subnetworks/${SUBNET_NAME}"
import_if_missing google_compute_firewall.ssh_jumphost "projects/${PROJECT_ID}/global/firewalls/${NETWORK_NAME}-allow-ssh-jumphost"
import_if_missing google_compute_firewall.ssh_nomad "projects/${PROJECT_ID}/global/firewalls/${NETWORK_NAME}-allow-ssh-nomad"
import_if_missing google_compute_firewall.nomad_ui "projects/${PROJECT_ID}/global/firewalls/${NETWORK_NAME}-allow-nomad-ui"
import_if_missing google_service_account.jumphost "projects/${PROJECT_ID}/serviceAccounts/${SERVICE_ACCOUNT_EMAIL}"
import_if_missing google_compute_instance.nomad "projects/${PROJECT_ID}/zones/${ZONE}/instances/${NOMAD_NAME}"
import_if_missing google_compute_instance.jumphost "projects/${PROJECT_ID}/zones/${ZONE}/instances/${JUMPHOST_NAME}"
import_if_missing 'google_project_iam_member.jumphost_roles["roles/logging.logWriter"]' "${PROJECT_ID} roles/logging.logWriter serviceAccount:${SERVICE_ACCOUNT_EMAIL}"
import_if_missing 'google_project_iam_member.jumphost_roles["roles/monitoring.metricWriter"]' "${PROJECT_ID} roles/monitoring.metricWriter serviceAccount:${SERVICE_ACCOUNT_EMAIL}"
import_if_missing 'google_project_iam_member.jumphost_roles["roles/compute.viewer"]' "${PROJECT_ID} roles/compute.viewer serviceAccount:${SERVICE_ACCOUNT_EMAIL}"

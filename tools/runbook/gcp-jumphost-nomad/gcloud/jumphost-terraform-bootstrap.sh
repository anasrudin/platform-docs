#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:?usage: jumphost-terraform-bootstrap.sh <app-dir>}"

CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME}")"

sudo rm -f /etc/apt/sources.list.d/hashicorp.list

if ! command -v terraform >/dev/null 2>&1 || ! command -v nomad >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y curl gnupg lsb-release ca-certificates

  sudo install -d -m 0755 /usr/share/keyrings
  curl -fsSL https://apt.releases.hashicorp.com/gpg \
    | gpg --dearmor --batch --yes \
    | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg >/dev/null

  echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com ${CODENAME} main" \
    | sudo tee /etc/apt/sources.list.d/hashicorp.list >/dev/null

  sudo apt-get update
  install_packages=()

  if ! command -v terraform >/dev/null 2>&1; then
    install_packages+=(terraform)
  fi

  if ! command -v nomad >/dev/null 2>&1; then
    install_packages+=(nomad)
  fi

  sudo apt-get install -y "${install_packages[@]}"
fi

terraform -chdir="$APP_DIR/terraform" init -input=false
terraform -chdir="$APP_DIR/terraform" validate

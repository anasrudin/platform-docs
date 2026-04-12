#!/usr/bin/env bash
set -euo pipefail

if command -v nomad >/dev/null 2>&1; then
  nomad version | head -n 1
  exit 0
fi

CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME}")"

sudo apt-get update
sudo apt-get install -y curl gnupg lsb-release ca-certificates

sudo install -d -m 0755 /usr/share/keyrings
curl -fsSL https://apt.releases.hashicorp.com/gpg \
  | gpg --dearmor --batch --yes \
  | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg >/dev/null

echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com ${CODENAME} main" \
  | sudo tee /etc/apt/sources.list.d/hashicorp.list >/dev/null

sudo apt-get update
sudo apt-get install -y nomad

nomad version | head -n 1

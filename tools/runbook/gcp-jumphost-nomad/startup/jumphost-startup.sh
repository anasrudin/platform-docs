#!/usr/bin/env bash
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

metadata() {
  local path="$1"
  curl -fsSL \
    -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/${path}"
}

install_hashicorp_cli() {
  local package="$1"

  if command -v "$package" >/dev/null 2>&1; then
    return
  fi

  local codename
  codename="$(. /etc/os-release && echo "${VERSION_CODENAME}")"

  rm -f /etc/apt/sources.list.d/hashicorp.list
  apt-get update
  apt-get install -y curl gnupg lsb-release ca-certificates

  install -d -m 0755 /usr/share/keyrings
  curl -fsSL https://apt.releases.hashicorp.com/gpg \
    | gpg --dearmor --batch --yes -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

  cat >/etc/apt/sources.list.d/hashicorp.list <<EOF
deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com ${codename} main
EOF

  apt-get update
  apt-get install -y "$package"
}

apt-get update
apt-get install -y curl jq unzip openssh-client
install_hashicorp_cli terraform
install_hashicorp_cli nomad

NOMAD_PRIVATE_IP="$(metadata instance/attributes/nomad_private_ip || true)"
NOMAD_SSH_USER="$(metadata instance/attributes/nomad_ssh_user || true)"

if [[ -n "${NOMAD_PRIVATE_IP}" && -n "${NOMAD_SSH_USER}" ]]; then
  cat >/usr/local/bin/ssh-nomad <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec ssh -o StrictHostKeyChecking=accept-new ${NOMAD_SSH_USER}@${NOMAD_PRIVATE_IP} "\$@"
EOF
  chmod +x /usr/local/bin/ssh-nomad
fi

cat >/usr/local/bin/jumphost-terraform <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${JUMPHOST_TERRAFORM_DIR:-$HOME/gcp-jumphost-nomad/terraform}"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Terraform app directory not found: $APP_DIR" >&2
  exit 1
fi

exec terraform -chdir="$APP_DIR" "$@"
EOF
chmod +x /usr/local/bin/jumphost-terraform

cat >/etc/motd <<EOF
Jumphost bootstrap complete.

Nomad private IP : ${NOMAD_PRIVATE_IP:-unknown}
Nomad SSH user   : ${NOMAD_SSH_USER:-unknown}

Helper:
  ssh-nomad
  jumphost-terraform
EOF

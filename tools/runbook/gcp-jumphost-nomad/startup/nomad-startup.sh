#!/usr/bin/env bash
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

metadata() {
  local path="$1"
  curl -fsSL \
    -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/${path}"
}

apt-get update
apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release

# ── Nomad ─────────────────────────────────────────────────────────────────────
install -d -m 0755 /usr/share/keyrings
curl -fsSL https://apt.releases.hashicorp.com/gpg \
  | gpg --dearmor --batch --yes -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
cat >/etc/apt/sources.list.d/hashicorp.list <<EOF
deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com ${CODENAME} main
EOF

apt-get update
apt-get install -y nomad

# ── Docker CE ─────────────────────────────────────────────────────────────────
curl -fsSL https://download.docker.com/linux/debian/gpg \
  | gpg --dearmor --batch --yes -o /usr/share/keyrings/docker-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
https://download.docker.com/linux/debian ${CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable docker
systemctl start docker

# ── Python 3 + venv ───────────────────────────────────────────────────────────
apt-get install -y python3 python3-venv python3-pip git

# ── Nomad single-node config ──────────────────────────────────────────────────
INTERNAL_IP="$(metadata instance/network-interfaces/0/ip)"

mkdir -p /etc/nomad.d /opt/nomad/data

cat >/etc/nomad.d/server.hcl <<EOF
name      = "nomad-single"
log_level = "INFO"
data_dir  = "/opt/nomad/data"
bind_addr = "0.0.0.0"

advertise {
  http = "${INTERNAL_IP}"
  rpc  = "${INTERNAL_IP}"
  serf = "${INTERNAL_IP}"
}

server {
  enabled          = true
  bootstrap_expect = 1
}

client {
  enabled = true

  meta {
    "node_class" = "single-node"
  }

  reserved {
    cpu    = 250
    memory = 256
    disk   = 1024
  }
}

plugin "raw_exec" {
  config {
    enabled = true
  }
}

ui {
  enabled = true
}
EOF

chmod 0640 /etc/nomad.d/server.hcl
systemctl enable nomad
systemctl restart nomad

# ── Mark bootstrap complete ───────────────────────────────────────────────────
touch /var/lib/nomad-bootstrap-complete

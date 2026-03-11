#!/bin/bash
# setup-all-nodes.sh
# Run on ALL 3 nodes (node1, node2, node3) to install base dependencies.
#
# Usage:
#   chmod +x setup-all-nodes.sh
#   sudo ./setup-all-nodes.sh

set -euo pipefail

echo "=== Platform Runtime — Base Node Setup ==="
echo "Installing: Nomad, curl, jq, ca-certificates"
echo ""

# ── System packages ──────────────────────────────────────────────────────────
apt-get update -y
apt-get install -y \
    curl \
    jq \
    ca-certificates \
    gnupg \
    lsb-release \
    wget \
    unzip

# ── HashiCorp repository ──────────────────────────────────────────────────────
echo "Adding HashiCorp apt repository..."
wget -O- https://apt.releases.hashicorp.com/gpg \
    | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
    | tee /etc/apt/sources.list.d/hashicorp.list

apt-get update -y
apt-get install -y nomad

# ── Nomad data directory ──────────────────────────────────────────────────────
mkdir -p /opt/nomad/data
chown nomad:nomad /opt/nomad/data 2>/dev/null || true

# ── Verify ────────────────────────────────────────────────────────────────────
echo ""
echo "✅ Base setup complete."
echo "   Nomad version: $(nomad --version)"
echo ""
echo "Next steps:"
echo "  node1  → sudo ./setup-control-node.sh"
echo "  node2/3 → copy infra/nomad/client.hcl to /etc/nomad.d/client.hcl"
echo "            sudo systemctl enable --now nomad"

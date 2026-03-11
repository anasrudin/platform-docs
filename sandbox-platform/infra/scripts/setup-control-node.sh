#!/bin/bash
# setup-control-node.sh
# Run on node1 ONLY to install the control-plane backing services.
#
# Installs: PostgreSQL 16, Redis 7, MinIO
# Requires: setup-all-nodes.sh already completed on this node.
#
# Usage:
#   chmod +x setup-control-node.sh
#   sudo ./setup-control-node.sh

set -euo pipefail

echo "=== Platform Runtime — Control Node Setup (node1) ==="
echo ""

# ── PostgreSQL 16 ─────────────────────────────────────────────────────────────
echo "Installing PostgreSQL 16..."
apt-get install -y postgresql-common
/usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
apt-get install -y postgresql-16

systemctl enable postgresql
systemctl start postgresql

# Create platform database and user
sudo -u postgres psql <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'platform') THEN
    CREATE ROLE platform WITH LOGIN PASSWORD 'platform_secret';
  END IF;
END
\$\$;

CREATE DATABASE platform OWNER platform;
GRANT ALL PRIVILEGES ON DATABASE platform TO platform;
SQL

echo "✅ PostgreSQL running. Database 'platform' created."

# ── Redis 7 ───────────────────────────────────────────────────────────────────
echo "Installing Redis 7..."
curl -fsSL https://packages.redis.io/gpg \
    | gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] \
https://packages.redis.io/deb $(lsb_release -cs) main" \
    | tee /etc/apt/sources.list.d/redis.list
apt-get update -y
apt-get install -y redis

# Bind to all interfaces so runtime nodes can reach it (adjust firewall separately)
sed -i 's/^bind 127.0.0.1/bind 0.0.0.0/' /etc/redis/redis.conf

systemctl enable redis-server
systemctl restart redis-server

echo "✅ Redis running on :6379."

# ── MinIO ─────────────────────────────────────────────────────────────────────
echo "Installing MinIO..."
wget -q https://dl.min.io/server/minio/release/linux-amd64/minio \
    -O /usr/local/bin/minio
chmod +x /usr/local/bin/minio

mkdir -p /opt/minio/data

# MinIO systemd service
cat > /etc/systemd/system/minio.service <<'EOF'
[Unit]
Description=MinIO Object Storage
After=network-online.target
Wants=network-online.target

[Service]
User=root
Environment="MINIO_ROOT_USER=minioadmin"
Environment="MINIO_ROOT_PASSWORD=minioadmin"
ExecStart=/usr/local/bin/minio server /opt/minio/data --console-address ":9001"
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable minio
systemctl start minio

echo "✅ MinIO running. Console: http://$(hostname -I | awk '{print $1}'):9001"
echo "   Credentials: minioadmin / minioadmin"

# ── Nomad server config ───────────────────────────────────────────────────────
echo "Installing Nomad server config..."
cp "$(dirname "$0")/../nomad/server.hcl" /etc/nomad.d/server.hcl

# Remove default client config if present
rm -f /etc/nomad.d/nomad.hcl

systemctl enable nomad
systemctl start nomad

echo "✅ Nomad server started."

# ── Initialize MinIO buckets ──────────────────────────────────────────────────
echo "Waiting for MinIO to be ready..."
sleep 5
bash "$(dirname "$0")/../minio/init-buckets.sh"

# ── Summary ───────────────────────────────────────────────────────────────────
NODE_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=== Control Node Setup Complete ==="
echo ""
echo "  PostgreSQL : localhost:5432  (db=platform, user=platform)"
echo "  Redis      : ${NODE_IP}:6379"
echo "  MinIO API  : ${NODE_IP}:9000"
echo "  MinIO UI   : http://${NODE_IP}:9001"
echo "  Nomad UI   : http://${NODE_IP}:4646"
echo ""
echo "Next: run setup-all-nodes.sh + deploy client.hcl on node2 and node3."

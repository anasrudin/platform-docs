#!/bin/bash

# start-nomad-cluster.sh
# Starts a 3-node local Nomad cluster (1 server, 2 clients)
# This fulfills the requested Day 1-2 infrastructure setup.

set -e

echo "Cleaning up old cluster..."
kill $(cat bin/nomad-server.pid 2>/dev/null) 2>/dev/null || true
kill $(cat bin/nomad-client1.pid 2>/dev/null) 2>/dev/null || true
kill $(cat bin/nomad-client2.pid 2>/dev/null) 2>/dev/null || true
rm -rf bin/nomad-*

mkdir -p bin/nomad-server
mkdir -p bin/nomad-client1
mkdir -p bin/nomad-client2

echo "Starting Nomad Server (node1)..."
cat <<EOF > bin/nomad-server.hcl
name      = "node1"
log_level = "INFO"
data_dir  = "$(pwd)/bin/nomad-server"
bind_addr = "127.0.0.1"

advertise {
  http = "127.0.0.1"
  rpc  = "127.0.0.1"
  serf = "127.0.0.1"
}

server {
  enabled          = true
  bootstrap_expect = 1
}

ports {
  http = 4646
  rpc  = 4647
  serf = 4648
}
EOF
nomad agent -config bin/nomad-server.hcl > bin/nomad-server.log 2>&1 &
echo $! > bin/nomad-server.pid

sleep 2

echo "Starting Nomad Client 1 (node2)..."
cat <<EOF > bin/nomad-client1.hcl
name      = "node2"
log_level = "INFO"
data_dir  = "$(pwd)/bin/nomad-client1"
bind_addr = "127.0.0.1"

advertise {
  http = "127.0.0.1"
  rpc  = "127.0.0.1"
  serf = "127.0.0.1"
}

client {
  enabled = true
  servers = ["127.0.0.1:4647"]
  meta {
    "node_class" = "mixed"
  }
}

plugin "raw_exec" {
  config {
    enabled = true
  }
}

ports {
  http = 5646
  rpc  = 5647
  serf = 5648
}
EOF
nomad agent -config bin/nomad-client1.hcl > bin/nomad-client1.log 2>&1 &
echo $! > bin/nomad-client1.pid

echo "Starting Nomad Client 2 (node3)..."
cat <<EOF > bin/nomad-client2.hcl
name      = "node3"
log_level = "INFO"
data_dir  = "$(pwd)/bin/nomad-client2"
bind_addr = "127.0.0.1"

advertise {
  http = "127.0.0.1"
  rpc  = "127.0.0.1"
  serf = "127.0.0.1"
}

client {
  enabled = true
  servers = ["127.0.0.1:4647"]
  meta {
    "node_class" = "mixed"
  }
}

plugin "raw_exec" {
  config {
    enabled = true
  }
}

ports {
  http = 6646
  rpc  = 6647
  serf = 6648
}
EOF
nomad agent -config bin/nomad-client2.hcl > bin/nomad-client2.log 2>&1 &
echo $! > bin/nomad-client2.pid

echo "Waiting for Nomad cluster to form..."
sleep 5

echo "Cluster status:"
nomad node status

echo "✅ 3-Node Nomad cluster is running."

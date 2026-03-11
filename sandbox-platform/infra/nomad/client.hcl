# Nomad Client Config — node2 / node3 (Runtime Nodes)
# Deploy to: /etc/nomad.d/client.hcl
#
# GCP: e2-standard-8 (8 vCPU · 32GB RAM)
# Runs: WASM agent, Firecracker agent, GUI agent

name      = "node2"   # Change to "node3" on the third node
log_level = "INFO"
data_dir  = "/opt/nomad/data"
bind_addr = "0.0.0.0"

advertise {
  # Replace with this node's internal IP
  http = "{{ GetInterfaceIP \"ens4\" }}"
  rpc  = "{{ GetInterfaceIP \"ens4\" }}"
  serf = "{{ GetInterfaceIP \"ens4\" }}"
}

server {
  enabled = false
}

client {
  enabled = true
  # Replace NODE1_IP with node1's internal IP
  servers = ["NODE1_IP:4647"]

  # node_class drives Nomad job placement constraints
  meta {
    "node_class" = "mixed"   # supports wasm + firecracker + gui workloads
  }

  # Resource reservations — leave headroom for the OS
  reserved {
    cpu            = 500   # MHz
    memory         = 512   # MB
    disk           = 1024  # MB
  }
}

# Required for running binaries directly (agents deployed as raw executables)
plugin "raw_exec" {
  config {
    enabled = true
  }
}

ports {
  # Offset from server ports to avoid conflict when co-located
  http = 5646   # node2: 5646 / node3: 6646
  rpc  = 5647   # node2: 5647 / node3: 6647
  serf = 5648   # node2: 5648 / node3: 6648
}

telemetry {
  prometheus_metrics         = true
  publish_allocation_metrics = true
  publish_node_metrics       = true
  disable_hostname           = true
}

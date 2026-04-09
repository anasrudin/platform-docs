# Nomad Server Config — node1 (Control Node)
# Deploy to: /etc/nomad.d/server.hcl
#
# GCP: e2-standard-8 (8 vCPU · 32GB RAM)
# Runs: API Gateway, Control Plane, PostgreSQL, Redis, MinIO

name      = "node1"
log_level = "INFO"
data_dir  = "/opt/nomad/data"
bind_addr = "0.0.0.0"

advertise {
  # Replace with node1's internal IP
  http = "{{ GetInterfaceIP \"ens4\" }}"
  rpc  = "{{ GetInterfaceIP \"ens4\" }}"
  serf = "{{ GetInterfaceIP \"ens4\" }}"
}

server {
  enabled          = true
  bootstrap_expect = 1
}

# No client workloads on the control node
client {
  enabled = false
}

ports {
  http = 4646
  rpc  = 4647
  serf = 4648
}

telemetry {
  prometheus_metrics         = true
  publish_allocation_metrics = true
  publish_node_metrics       = true
  disable_hostname           = true
}

ui {
  enabled = true
}

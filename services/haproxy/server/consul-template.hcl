# consul-template.hcl
# Watches Consul for changes to sandbox agent services and re-renders
# haproxy.cfg, then performs a zero-downtime HAProxy reload.
#
# Run with:
#   consul-template -config=infra/haproxy/consul-template.hcl
#
# Environment variables consumed:
#   CONSUL_HTTP_ADDR   — Consul address (default: 127.0.0.1:8500)
#   CONSUL_HTTP_TOKEN  — ACL token (optional)

consul {
  address = "{{ env "CONSUL_HTTP_ADDR" | or "127.0.0.1:8500" }}"

  retry {
    enabled  = true
    attempts = 12
    backoff  = "250ms"
  }

  auth {
    # token provided via CONSUL_HTTP_TOKEN env var automatically by consul-template
  }
}

# Re-render haproxy.cfg whenever any sandbox agent service changes
template {
  source      = "infra/haproxy/haproxy.cfg.ctmpl"
  destination = "/etc/haproxy/haproxy.cfg"

  # Zero-downtime reload: send new PID list to the existing master process
  command = "haproxy -f /etc/haproxy/haproxy.cfg -sf $(cat /var/run/haproxy.pid) && echo $! > /var/run/haproxy.pid"

  command_timeout = "10s"

  # Only reload when the rendered output actually changes
  perms = "0644"
}

# Health — expose consul-template's own status
log_level = "info"
log_format = "json"

# Deduplicate template renders across multiple consul-template instances
# (useful when running >1 replica of this job)
deduplicate {
  enabled = true
  prefix  = "consul-template/sandbox/haproxy"
}

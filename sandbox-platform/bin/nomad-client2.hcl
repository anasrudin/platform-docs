name      = "node3"
log_level = "INFO"
data_dir  = "/Users/annas/Desktop/code/platform-docs/sandbox-platform/bin/nomad-client2"
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
